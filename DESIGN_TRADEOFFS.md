# Design Tradeoffs — AI Knowledge Inbox

This document records the **current implementation**, the reasons it is reasonable for a small local-first project, the limitations that follow from those choices, and an incremental path toward a safer production architecture.

The repository is a useful prototype for exploring ingestion and RAG. It is not production-hardened: it has no authentication or tenant isolation, fetches caller-provided URLs, stores embeddings in SQLite, and scans all chunks at query time. CORS has been restricted to configurable origins, URL destination/redirect validation has been added, and incompatible embedding dimensions are no longer padded or truncated. These changes reduce risk but do not eliminate all deployment security concerns.

## 1. Current architecture

```text
[Browser: React + Vite]
          |
          | REST + SSE
          v
[FastAPI application]
   |         |                |
   |         |                +--> Web-assisted query
   |         |                      DuckDuckGo HTML / Wikipedia fallback
   |         |                      fetch article text
   |         |                      ingest into same inbox
   |         |
   |         +--> Query: embed question -> rank chunks -> Gemini answer
   |
   +--> Ingest: parse -> chunk -> embed -> persist
                       |
                       v
              [SQLite: items + chunks]
              [embedding JSON per chunk]
```

The backend currently runs ingestion and querying in the request lifecycle. The frontend calls the backend using `VITE_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.

### Main modules

| Module | Current responsibility |
|---|---|
| `backend/app/main.py` | FastAPI lifespan, CORS, error handlers, API endpoints |
| `backend/app/schemas.py` | Request and response validation |
| `backend/app/database.py` | SQLite schema, transactions, item/chunk reads and deletion |
| `backend/app/services/ingest.py` | Note, URL, and file extraction; web-search scraping |
| `backend/app/services/chunker.py` | Recursive character splitting and overlap |
| `backend/app/services/embeddings.py` | Gemini embeddings, fallback vectors, cosine and lexical scoring |
| `backend/app/services/rag.py` | Ingestion orchestration, prompt construction, Q&A, SSE, web-assisted Q&A |
| `frontend/src/api.js` | HTTP API client and SSE stream parser |
| `frontend/src/components/` | Capture UI, inbox, answer display and source excerpts |

## 2. Content ingestion

The application accepts notes, URLs, individual file uploads, and a batch of uploads. Text is extracted before chunking and embedding; item metadata and related chunks are then written to SQLite.

### URL extraction

The fetcher uses HTTPX with a timeout and manually follows a bounded number of redirects. Each initial and redirect URL is checked for HTTP(S), embedded credentials, standard ports, and DNS/IP destinations that are not globally routable. BeautifulSoup removes common boilerplate elements such as scripts, styles, navigation, headers, footers, forms, SVGs, and sidebars before extracting text.

**Benefits**
- Easy to understand and operate locally.
- No separate crawler or browser runtime is required.
- Readable text extraction works for many conventional content pages.

**Costs and failure modes**
- JavaScript-rendered pages may not contain the actual article in the returned HTML.
- Site-specific layouts, paywalls, anti-bot responses, and malformed HTML affect extraction quality.
- DNS rebinding, multi-homed DNS, deployment routing, and TOCTOU between resolution and connection can still create SSRF risk; application checks alone are not a network boundary.
- Text is extracted without a robust content provenance or freshness model.

**Recommended changes before public exposure**
1. **Implemented:** parse URLs and allow only HTTP(S) schemes, no embedded credentials, standard ports, and globally routable resolved IPs.
2. **Implemented:** revalidate redirect destinations and cap redirect hops.
3. **Still required before public exposure:** enforce network egress rules or a constrained fetch proxy to mitigate DNS rebinding and routing edge cases.
4. **Still required:** response byte limits, per-user rate limits, and request concurrency limits. HTML content-type checks are implemented.
5. **Partially covered:** tests reject localhost, private IPv4, non-HTTP schemes, and embedded credentials. Add tests for redirects, DNS rebinding, IPv6 special ranges, oversized responses, and non-HTML responses.

### File ingestion

The current parser uses pypdf for PDFs and python-docx for DOCX paragraphs. It decodes a set of text-like extensions including Markdown, TXT, CSV, JSON, Python, JavaScript, and HTML; for other extensions, it may also attempt a generic text decode.

**Tradeoff:** this keeps dependencies and setup small, but it is not a strict upload policy. The API now caps each upload at 10 MiB and each batch at 10 files, and uses a bounded read for individual files. It still lacks a total batch-byte budget, per-user quota, strict content-type/signature validation, and parser resource isolation.

**Next step:** define an explicit extension and MIME allowlist, validate signatures where practical, enforce request and per-file byte limits, cap batch count and total extracted characters, and isolate parser workloads if the service is exposed to untrusted uploads. Image-only PDFs need OCR, which is not currently implemented.

### URL deduplication

The database helper reuses an existing item when the incoming URL string exactly matches a stored `source_url`.

This prevents straightforward duplicate submissions, but URLs that differ only by a trailing slash, tracking parameters, case, or redirect destination can still produce separate entries. URL canonicalization must be conservative: remove only known tracking parameters and preserve query parameters that alter content.

## 3. Chunking strategy

### What is implemented

The splitter in `backend/app/services/chunker.py` defaults to:
- `CHUNK_SIZE=500` characters
- `CHUNK_OVERLAP=100` characters
- Separators: paragraph breaks, newlines, sentence punctuation plus spaces, semicolons, spaces, and finally the empty separator

It recursively chooses a separator that is present, builds chunks up to a character threshold, and seeds the next chunk with a tail overlap when possible.

### Tradeoff comparison

| Strategy | Advantages | Disadvantages | Fit for this project |
|---|---|---|---|
| Fixed character windows | Minimal implementation and predictable work | Can cut sentences/words; context can split awkwardly | Useful baseline |
| Recursive boundary-aware characters (current) | Prefers natural separators; low compute cost; easy to tune | Character counts are not token counts; boundary handling can exceed the nominal size in some cases; separator choice can vary with document layout | Good simple default |
| Token-based splitting | Better control of model token budgets | Requires tokenizer dependency and model-specific tuning | Good next iteration if context limits become an issue |
| Semantic/LLM-based splitting | Can keep topics or propositions together | Extra latency, cost, complexity, and failure points | Only when quality evaluations show a clear benefit |

Character-based chunk sizes do not correspond to fixed token counts. The previous README's claim that 500 characters always equals a particular number of tokens should not be relied on across languages and content types.

### Overlap

Overlap can preserve context around boundaries. It also creates duplicate text and redundant retrieval results, increasing embedding costs, storage, and the chance that multiple top results contain almost the same passage.

Tune `CHUNK_SIZE` and `CHUNK_OVERLAP` using a small representative evaluation set. Measure retrieval recall, citation quality, latency, number of chunks, and token usage rather than assuming one setting is universally optimal.

**Implementation note:** `chunk_content` uses `chunk_size or settings.CHUNK_SIZE` and `chunk_overlap or settings.CHUNK_OVERLAP`; passing zero uses the setting rather than zero. The overlap implementation is approximate and should be tested against edge cases such as long unbroken tokens, tiny chunk sizes, and separators that occur infrequently.

## 4. Embeddings and fallback behavior

### Gemini path

The configured embedding model is `gemini-embedding-001` in `backend/.env.example` and `backend/app/config.py`. The implementation batches up to 30 input texts per embedding call.

Embedding behavior is external-service dependent: API availability, quotas, model dimensions, and model names can vary by account and over time.

### Deterministic feature-hashing fallback

When no usable API key is configured, or an embedding request raises an exception, the code generates local feature-hashing vectors with word hashes and character trigrams. Its default dimension is **3,072**, and it normalizes each non-empty vector.

This fallback is useful for development, but it is not a semantic embedding model. It captures token/subword overlap and should not be described as equivalent to Gemini embedding quality. An exception from the Gemini call currently causes the entire requested embedding batch to fall back.

### Critical consistency issue

The existing test had asserted a fixed embedding dimension, which conflicted with the fallback vector's 3,072 dimensions and provider-dependent output dimensions. The test now checks non-empty, internally consistent vector lengths instead and covers mismatched-dimension cosine behavior.

Vectors from different embedding spaces must not be compared. The current code now returns zero cosine similarity for mismatched dimensions and skips dense scoring for incompatible chunk vectors rather than padding/truncating them. This is safer than fabricated compatibility, but old items can still have mixed embedding spaces and may rank using lexical overlap only. Rebuild/re-embed the collection when changing the model or provider.

**Recommended fix**
1. Choose a versioned embedding-space contract with a documented dimension and model identifier.
2. Persist embedding model/version metadata, ideally at the collection or chunk level.
3. If the provider fails during ingestion, either fail that ingestion clearly or explicitly mark the item as fallback-indexed.
4. Never compare across embedding spaces. Separate indexes by model/version or re-embed the entire collection when changing spaces.
5. Update tests to assert the selected model/fallback contract deterministically and mock external API behavior instead of relying on a live API key.
6. Add tests for vector-dimension mismatch and zero vectors.

## 5. Retrieval scoring

The current implementation in `embeddings.py` is **a custom dense-plus-lexical heuristic**, not BM25. A recent fix stops padding/truncating vectors to force dimensions to match; vector cosine is calculated only when dimensions match.

For each chunk it calculates cosine similarity, then extracts distinct query terms after a small stopword list. If query terms overlap the chunk text, it computes a lexical score from query-term coverage and a capped occurrence-frequency boost. If lexical terms overlap, the final score is:

```text
final_score = 0.65 * lexical_score + 0.35 * max(cosine_similarity, 0)
```

If no lexical overlap exists, the score is the cosine similarity. Results are sorted in descending order and the first `top_k` are returned.

**Why this is reasonable now**
- No separate search engine or index is needed.
- The scoring steps are inspectable and fast to prototype.
- Exact names and technical terms can still influence ranking when embeddings are imperfect.

**Limitations**
- It is not BM25: it does not use inverse document frequency, corpus statistics, or a standard BM25 implementation.
- The lexical and dense scores have different scales and are not calibrated.
- The stopword list and tokenization are basic and English-centric.
- Every stored chunk is read from SQLite for each query, and each chunk is scored in Python.
- The returned `similarity_score` may be the hybrid score rather than pure cosine similarity; displaying it as a calibrated percentage match is misleading.

**Next steps**
- Build a small labelled query/chunk evaluation set.
- Compare dense-only, lexical-only, and hybrid search with Recall@k, MRR, and nDCG@k.
- Consider SQLite FTS5 for lexical retrieval and Reciprocal Rank Fusion (RRF) to combine rankings rather than directly combining scores of unlike scales.
- Add a cross-encoder reranker only if offline evaluation demonstrates improved relevance worth its added latency and cost.

## 6. RAG prompt and answer generation

The pipeline constructs a prompt containing retrieved chunks, source titles/URLs, and an instruction to answer only from the supplied context and state when the context is insufficient. The answer-generation path tries the configured model and a list of fallback model identifiers.

**Benefits**
- The response includes the selected source excerpts for inspection.
- Prompt instructions encourage context-grounded answers and source references.
- Model failover can reduce failures when one configured model is unavailable.

**Limitations**
- Prompt instructions are not a security boundary and do not guarantee factual grounding.
- Retrieved web pages and documents are untrusted input and can contain prompt injection.
- Source citations are generated by the model; they should be validated against the actual retrieved source list.
- Similarity does not mean factual support.
- The code detects missing knowledge using string matching over the answer text, which is brittle.
- Model identifiers and availability should be validated against the target Google AI environment; do not assume a fallback model is available just because it appears in a list.

**Recommended improvements**
1. Treat retrieved source content as untrusted data and delimit it clearly in the prompt.
2. Validate citation IDs against the source snippets supplied to the model.
3. Return structured answer/citation data where possible rather than relying solely on text patterns.
4. Add model-call deadlines, bounded retries with exponential backoff and jitter, and explicit handling for quota, authentication, timeout, and malformed responses.
5. Track answer latency, retrieval latency, prompt/output token counts, provider errors, and source count.
6. Evaluate groundedness and retrieval separately using a reproducible question set; do not claim anti-hallucination guarantees.

## 7. Persistence choice: SQLite and JSON vectors

### Current schema

The current SQLite database holds:
- `items`: item ID, source type, source URL/name, title, raw extracted content, and creation timestamp.
- `chunks`: chunk ID, parent item ID, chunk order, chunk content, JSON-serialized embedding, and timestamp.

A foreign key links chunks to items with `ON DELETE CASCADE`. Item and chunk inserts are performed using one connection/transaction path. The schema creates indexes for chunk-to-item lookup and item creation time.

### Benefits
- Zero additional infrastructure for local development.
- Portable database file and straightforward backup for a stopped local instance.
- Transactional item/chunk writes and simple inspectability.
- Low operational overhead for a small single-user data set.

### Costs and boundaries
- The application deserializes all embedding JSON and loads all chunks into memory per query.
- Full-scan ranking cost grows linearly with chunk count. Exact latency depends on the embedding dimensions, hardware, Python overhead, disk/cache state, and collection shape; a fixed threshold such as “10,000 chunks under 10 ms” is not guaranteed.
- SQLite allows concurrent readers but has a single-writer model. Ingestion contention grows with simultaneous writes.
- There is no authentication, tenant field, embedding-version field, document status, or database migration framework in the current schema.
- File-based persistence needs explicit backups and volume management if hosted in a container.

**Recommendation:** keep SQLite while the application is a local prototype. Do not migrate databases based only on an arbitrary row-count threshold. Measure p95/p99 query latency, ingestion throughput, database size, memory use, and write contention with representative workloads.

## 8. API and frontend contract

Implemented routes:

| Method | Route | Behavior |
|---|---|---|
| GET | `/health` | Returns service name, configured model names, and a basic API-key-configured flag |
| POST | `/ingest` | Ingest note or URL |
| POST | `/ingest/file` | Ingest one uploaded file |
| POST | `/ingest/files` | Ingest several files sequentially and report successful items/chunks |
| GET | `/items` | List saved items with raw content and chunk counts |
| DELETE | `/items/{item_id}` | Delete a saved item and related chunks |
| POST | `/query` | Synchronous RAG query |
| POST | `/query/stream` | SSE answer stream |
| POST | `/query/web-search` | Search, fetch, ingest, and query |

### API design tradeoffs

- Ingestion happens synchronously in the HTTP request, so slow page fetches and embedding-provider delays hold a request open.
- The batch file endpoint processes files sequentially and can partially succeed. The current response reports successful file count and total chunks but does not provide a fully typed per-file error list.
- `GET /items` returns raw extracted content, which is convenient for a local UI but may expose sensitive data if a future multi-user API is added without authorization.
- API exception handling in some query/file routes includes exception text in the returned detail. Avoid leaking upstream, file, or internal information in public deployments.
- The streaming API emits `sources`, `token`, and `done` events but does not currently define a separate error event schema.

## 9. Security and operational risks

These items are blockers before exposing the service to the public internet or using it for sensitive knowledge collections.

| Risk | Current behavior | Required mitigation |
|---|---|---|
| No authentication/authorization | API routes are publicly callable if the server is reachable | Add identity, authorization, and ownership checks |
| No tenant isolation | All items share one logical collection | Add tenant/user scoping to every read, query, and mutation |
| CORS | Configurable allowlist defaults to local Vite origins; credentials disabled | Set exact deployed frontend origins and review required methods |
| SSRF | URL and redirect destinations are validated against public IP ranges; redirects are bounded | Add network egress controls/fetch proxy and test DNS rebinding and deployment-specific routing |
| Upload resource exhaustion | 10 MiB per file, max 10 files per batch, bounded per-file reads | Add total batch-byte budget, strict file allowlist, quotas, and parser resource limits |
| Prompt injection | Retrieved content is included in the LLM prompt | Delimit and treat documents as untrusted, separate instructions from data, test adversarial inputs |
| Secrets | API key comes from environment | Keep secrets out of Git/logs; use deployment secrets and rotate exposed keys |
| Logging/privacy | Request/query information is logged | Avoid logging sensitive raw content; define retention and access rules |
| Backup/recovery | A local SQLite file is the source of truth | Define consistent backups, restore drills, and persistent-volume policy |
| Service resilience | Provider calls and scraping are request-path dependencies | Timeouts, bounded retries, rate limits, concurrency limits, and observable failure metrics |

The health endpoint's API-key flag is only a configuration check. It does not prove that the key is valid or that the provider is reachable.

## 10. What changes for production?

Do not introduce every component at once. The right sequence is to fix correctness and security boundaries first, then evolve infrastructure when measurements justify it.

### Phase 1 — Correctness and minimum safety

- Resolve the embedding dimension/model inconsistency and add embedding-space metadata.
- Add tests for URL validation/SSRF, redirect handling, empty/oversized files, batch partial failures, and provider errors.
- Restrict CORS and avoid returning raw internal exception text.
- Enforce upload limits and URL fetch byte/time limits.
- Verify model IDs and configure bounded retries/timeouts.
- Add request IDs and structured error responses.

### Phase 2 — Measurable quality and operability

- Create retrieval evaluation data and track Recall@k, MRR, nDCG@k, answer groundedness, and citation validity.
- Add metrics for request latency, ingestion duration, embedding calls/errors, retrieved chunk count, query latency, SQLite busy errors, and Gemini quota failures.
- Add persistent storage/backup/restore documentation and a reproducible test environment.
- Consider SQLite FTS5 for lexical search; compare rank-fusion approaches empirically.
- Add pagination to item listing and avoid sending all raw document content unless requested.

### Phase 3 — Scale only when workload demands it

A possible later deployment topology is:

```text
[Web UI]
    |
[API / Auth / Rate limits]
    |                    |
    v                    v
[Query service]     [Ingestion API]
    |                    |
    v                    v
[Vector + lexical]  [Durable task queue]
    |                    |
    v                    v
[LLM gateway]       [Isolated workers]
                         |
                  [Object/document storage]
```

Potential choices—not current dependencies—include:
- PostgreSQL with pgvector or a vector engine such as Qdrant for vector search.
- PostgreSQL full-text search or a dedicated search engine for lexical retrieval.
- A durable queue (such as Celery with Redis/RabbitMQ or a managed queue) for long-running ingestion jobs.
- Object storage for uploaded originals where retention requirements justify it.
- An LLM gateway or provider adapter for rate limiting, timeout policy, model routing, and cost tracking.
- OpenTelemetry traces and metrics plus dashboards/alerts.

**Do not claim ANN always changes search from O(N) to O(log N) or O(1).** ANN algorithms trade exactness for retrieval speed, and their performance depends on index type, parameters, data distribution, recall target, and filtering patterns.

For asynchronous ingestion, a job-based interface could return `202 Accepted` with a durable job ID and expose a status endpoint or SSE updates. That is a future API design; the current API performs ingestion synchronously.

## 11. Decision summary

| Decision | Current choice | Why now | Trigger to reconsider |
|---|---|---|---|
| API framework | FastAPI | Simple typed API and built-in OpenAPI | Service boundaries or deployment constraints change |
| Frontend | React + Vite | Lightweight client build and local development | Product requirements require a different deployment/rendering model |
| Persistence | SQLite | One-file, zero-service local setup | Measured write contention, availability, multi-user, or operational requirements |
| Chunking | Recursive characters + overlap | Low-cost baseline, easy to tune | Evaluation shows poor retrieval or token-budget inefficiency |
| Embeddings | Gemini with deterministic local fallback | External semantic quality plus offline development path | Cost, policy, privacy, latency, or provider constraints |
| Retrieval | Full-scan NumPy plus lexical heuristic | Transparent and easy to test on small collections | Query latency or retrieval evaluation degrades |
| Ingestion | Synchronous request handling | Minimum moving parts | Long-running requests, throughput, reliability, or rate limits become problematic |
| Streaming | SSE | Simple incremental response in browsers | Need resumability, durable generation jobs, or bidirectional communication |
| Observability | Application logging | Low setup cost | Multi-instance production operation requires metrics/traces/alerts |

## 12. Bottom line

The current design prioritizes **simple local setup, clear module boundaries, and an inspectable RAG workflow** over scale and security hardening. That is an appropriate prototype tradeoff when its boundaries are explicit.

The most important near-term actions are not to add Kubernetes, Redis, or a vector database immediately. The embedding comparison and fixed-dimension test mismatch have been corrected; CORS is configurable, URL destination checks are in place, upload limits are enforced, and SQLite startup recursion has been fixed. Remaining priorities are network-level SSRF protection, a total batch-byte budget, targeted redirect/abuse tests, and retrieval-quality evaluation. Infrastructure changes should follow demonstrated needs.

## 13. Local setup, licensing, and CI

- `setup.bat` installs backend and frontend dependencies on Windows; `bash setup.sh` does the same on macOS/Linux.
- Launch backend and frontend in separate terminals with the matching `.bat` or `.sh` scripts. The shell scripts use `backend/.venv` and fail early if setup has not been run.
- `.gitignore` excludes `.venv` directories, local databases, and environment files.
- The repository now includes an MIT `LICENSE`.
- GitHub Actions runs the backend test suite without a Gemini key and builds the frontend. A green workflow run is the verification signal; adding the workflow file alone does not prove tests pass.
