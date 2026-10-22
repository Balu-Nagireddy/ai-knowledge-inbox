# Architectural Tradeoffs & System Design Analysis

This document provides a detailed technical breakdown of the architectural decisions, design tradeoffs, failure modes at scale, and production roadmap for the **AI Knowledge Inbox**.

---

## 1. Chunking Approach Rationale

### Strategy Implemented
We implemented an **Intentional Recursive Character Splitting with Overlap** algorithm (`backend/app/services/chunker.py`):
- **Chunk Size**: `500` characters (configurable via `CHUNK_SIZE`).
- **Overlap**: `100` characters (configurable via `CHUNK_OVERLAP`).
- **Separators Hierarchy**: `["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]`.

### Rationale & Tradeoffs
| Dimension | Fixed-Size Character Chunking | Recursive Boundary-Aware Chunking (Our Approach) | Semantic / LLM-Based Chunking |
| :--- | :--- | :--- | :--- |
| **Coherence** | Low (cuts words/sentences in half) | **High** (respects paragraphs, lines, and sentences) | Highest (groups by proposition) |
| **Retrieval Quality** | Degraded vector relevance | **Preserves context & boundary transitions** | Highest, but high latency & cost |
| **Compute Overhead** | Negligible | **Low (< 2ms per document)** | Very High (requires LLM passes) |
| **Cross-Chunk Continuity** | Poor without overlap | **Strong** (100-char overlap preserves semantic glue) | Strong |

**Why 500 characters with 100 overlap?**
- Shorter chunks (e.g. 100-200 chars) lack sufficient context for the embedding model to differentiate nuanced meanings.
- Oversized chunks (e.g. 2000+ chars) dilute the vector representation with multiple topics, causing semantic drift during cosine similarity retrieval.
- 500 characters (~75–100 tokens) strikes the sweet spot between granular retrieval specificity and context completeness for notes and web paragraphs.

---

## 2. Vector Store Choice

### Current Architecture: Embedded SQLite + NumPy Cosine Similarity
- **Storage**: SQLite relational database (`knowledge_inbox.db`) with `items` and `chunks` tables.
- **Vectors**: Serialized high-dimensional floating-point arrays (768-dim from `text-embedding-004`).
- **Similarity Engine**: Vectorized matrix cosine similarity using `numpy` (`np.dot` over normalized vector matrix).

### Why This Fits The Requirements
1. **Zero External Infrastructure**: No Docker, no external services (Pinecone, Qdrant, Milvus) required to run locally. An evaluator can clone, run, and evaluate within 2 minutes.
2. **ACID Transactions**: Item metadata and its corresponding vector chunks are committed or rolled back in a single SQLite transaction, preventing orphaned chunks.
3. **Instant Startup**: Zero cold-start latency; no indexing daemon.

### What Breaks at Scale?
At scale (e.g. > 100,000 chunks or > 50 concurrent Q&A queries per second):
1. **Full-Scan Vector Comparison ($O(N)$)**:
   - Comparing a query vector against all chunk embeddings requires scanning every row in memory. While fast for up to 10,000 chunks (< 10ms with NumPy), it degrades linearly as $N$ grows into hundreds of thousands.
2. **Memory Footprint**:
   - Loading all embeddings into RAM on every query or keeping a heavy in-memory matrix consumes several hundred megabytes of RAM under large document sets.
3. **Write Concurrency**:
   - SQLite uses database-level locking during writes (`save_item_with_chunks`). Heavy parallel web ingestion will encounter `database is locked` contention.

---

## 3. What Changes in Production?

To transition this minimal architecture into an enterprise-scale, multi-tenant production system:

```
[ Clients ] 
    │
    ▼
[ Cloudflare / Load Balancer ]
    │
    ├──► [ Ingestion Worker Service ] ──► [ Celery / Redis Queue ] ──► [ Async Scraper & Chunker ]
    │                                                                           │
    │                                                                           ▼
    ├──► [ Query API Service ]                                        [ Managed Vector DB ]
    │         │                                                          (pgvector / Qdrant)
    │         ▼                                                                 ▲
    │    [ Semantic Cache (Redis) ] ──(Cache Miss)──────────────────────────────┤
    │         │
    │         ▼
    └────► [ LLM Gateway (Gemini 2.0 / 1.5 Flash with Fallback & Rate Limiting) ]
```

### 1. Vector Engine Upgrade
- Migrate to **PostgreSQL with `pgvector`** (HNSW or IVFFlat indexing) or dedicated engines like **Qdrant** / **Milvus**.
- Approximate Nearest Neighbors (ANN) indexing brings search complexity from $O(N)$ down to $O(\log N)$ or $O(1)$.

### 2. Asynchronous Ingestion & Task Queues
- URL scraping and external content parsing are I/O-heavy and prone to timeouts or rate limits.
- In production, `/ingest` should return `202 Accepted` with a job ID, offloading the scrape, chunk, and embed operations to a background queue (Celery, ARQ, or AWS SQS).
- Use WebSockets or SSE for realtime status updates in the UI ("Scraping...", "Chunking...", "Indexed").

### 3. Chunking & Hybrid Search
- Implement **Hybrid Search**: Combine dense vector retrieval (semantic) with sparse BM25 keyword search (exact matches for names, code symbols, part numbers).
- Use a **Reranker** (e.g. Cohere Rerank or cross-encoder) on the top 20 candidate chunks to refine the final top 4 context snippets passed to the LLM.

### 4. Guardrails & Observability
- OpenTelemetry distributed tracing across embedding calls and LLM generation.
- Grounding verification / hallucination detection metrics (e.g. Ragas, TruLens).
- Semantic caching with Redis to instantly serve repeated identical or near-identical questions without re-invoking LLM APIs.

---

## 4. Debuggability & Code Quality Highlights

- **Separation of Concerns**:
  - `database.py`: Pure data access and schema definition.
  - `ingest.py`: Content fetching, HTML sanitization, and title extraction.
  - `chunker.py`: Text chunking logic with boundary preservation.
  - `embeddings.py`: Vector operations, client management, and similarity ranking.
  - `rag.py`: Orchestration of context grounding, prompt engineering, and LLM calls.
  - `main.py`: Clean HTTP endpoints, input validation, and exception translation.
- **Strict Input Validation**:
  - Pydantic models validate URL schemes (`http://`, `https://`), minimum lengths, content presence, and integer boundaries (`top_k` between 1 and 10).
- **Graceful Degraded / Demo Mode**:
  - If a user runs the application without a Gemini API key or with an invalid key, the app gracefully falls back to deterministic mock embeddings and informative responses rather than crashing.
