# AI Knowledge Inbox 📥🧠

A local-first knowledge capture and question-answering app. Save notes, web pages, and supported documents; split content into overlapping chunks; index the chunks with embeddings; and ask questions against your saved knowledge using a Retrieval-Augmented Generation (RAG) pipeline.

The project combines a **FastAPI** backend, a **React + Vite** frontend, **SQLite** persistence, **NumPy** similarity calculations, and the **Google Gen AI SDK**. It also includes a deterministic local fallback for development when the Gemini API is not configured or an embedding request fails.

> **Project status:** a single-process, local-first application intended for experimentation and small personal knowledge collections. It is not yet a hardened, multi-user production service. See [DESIGN_TRADEOFFS.md](./DESIGN_TRADEOFFS.md) for current limitations, security considerations, and a practical scaling path.

## Contents

- [Assignment fit](#assignment-fit)

- [Features](#features)
- [How it works](#how-it-works)
- [Technology stack](#technology-stack)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Run locally](#run-locally)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Testing](#testing)
- [Known limitations and security notes](#known-limitations-and-security-notes)
- [Design decisions](#design-decisions)

## Features

- **Capture notes:** save plain text with an optional title. If no title is supplied, the first line is used to derive one.
- **Save web pages:** fetch a URL server-side, remove common non-content HTML elements, and extract readable text and a page title.
- **Upload documents:** ingest a single file or multiple files. The parser handles PDF, DOCX, Markdown, text, and selected text-based formats.
- **Chunking with overlap:** split content with a recursive separator strategy that prefers paragraph, line, sentence, and word boundaries.
- **Embedding generation:** use the configured Gemini embedding model; use deterministic feature-hashing vectors when the API is not configured or an embedding call fails.
- **Hybrid retrieval:** rank stored chunks with a combination of cosine similarity and a lightweight lexical-overlap score.
- **Grounded Q&A:** send the top retrieved excerpts to Gemini with instructions to answer from the supplied context and cite sources.
- **Streaming answers:** expose an SSE endpoint so the UI can show answer text as it arrives.
- **Optional web-assisted answers:** search for a small number of public web results, ingest fetched articles into the inbox, then query the enriched collection.
- **Persistent local storage:** store item metadata, raw extracted text, chunk text, and serialized embeddings in SQLite.
- **Inbox management:** list saved items and delete an item with its associated chunks.

## How it works

```text
                         ┌─────────────────────────┐
                         │     React + Vite UI     │
                         └────────────┬────────────┘
                                      │ HTTP / SSE
                                      ▼
                         ┌─────────────────────────┐
                         │      FastAPI API        │
                         └────────────┬────────────┘
                                      │
                     ┌────────────────┼─────────────────┐
                     ▼                ▼                 ▼
              Note / URL / File   Query / RAG      Web-assisted query
                     │                │                 │
                     ▼                ▼                 ▼
              Parse and clean    Embed question    Search + fetch pages
                     │                │                 │
                     ▼                ▼                 ▼
               Chunk content    Rank all chunks    Ingest fetched content
                     │          (dense + lexical)        │
                     ▼                │                 │
                Embed chunks          └────────┬────────┘
                     │                          │
                     ▼                          ▼
               ┌────────────────────────────────────┐
               │ SQLite: items, chunks, embeddings  │
               └───────────────────┬────────────────┘
                                   │
                                   ▼
                         Gemini answer generation
                         (or retrieval-only fallback)
```

### Ingestion flow

1. Validate the incoming note, URL, or upload request.
2. Extract and normalize text. URL extraction removes common boilerplate elements; file extraction depends on the supported format.
3. Split the extracted text using configurable character limits and overlap.
4. Generate embeddings in batches (up to 30 texts per embedding request in the current implementation), or deterministic fallback vectors.
5. Persist the item and its chunks in SQLite.

Repeated URL ingestion is deduplicated by exact stored URL string. This is not canonical URL normalization.

### Query flow

1. Load stored chunks and their embeddings from SQLite.
2. Generate an embedding for the question, with the same provider/fallback selection as ingestion.
3. Score all chunks using cosine similarity and, when query terms overlap with a chunk, a lightweight lexical-overlap component.
4. Return the top `top_k` chunks as sources.
5. If a Gemini client is available, submit the question and retrieved excerpts to the configured LLM model with fallback model attempts. Without a client, return a deterministic retrieval-only demo message rather than an LLM-generated answer.

**Important:** a similarity score is a retrieval ranking signal, not a calibrated probability that a source is correct. Citations and prompt instructions help grounding but do not guarantee factual correctness.

## Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| API | Python, FastAPI, Uvicorn | REST endpoints and streaming responses |
| Validation / settings | Pydantic v2, Pydantic Settings | Request validation and environment configuration |
| Persistence | SQLite, Python `sqlite3` | Item metadata, content, chunk records, and serialized vectors |
| Retrieval | NumPy | Cosine similarity and vector operations |
| Ingestion | HTTPX, BeautifulSoup4 | HTTP fetching and HTML text extraction |
| File parsing | pypdf, python-docx | PDF and DOCX text extraction |
| AI integration | Google Gen AI SDK | Embeddings and answer generation |
| Frontend | React, Vite, React Markdown, Lucide React | Interactive inbox and Q&A interface |
| Tests | pytest, FastAPI TestClient | Service, database, and API tests |

The default model names are read from `backend/.env.example`. Model availability and quotas depend on the Google AI account and may change over time.

## Repository layout

```text
ai-knowledge-inbox/
├── backend/
│   ├── app/
│   │   ├── config.py               # Environment-backed settings
│   │   ├── database.py             # SQLite schema and data-access functions
│   │   ├── logging_config.py       # Application logging
│   │   ├── main.py                 # FastAPI routes and lifecycle
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   └── services/
│   │       ├── chunker.py          # Recursive text splitting
│   │       ├── embeddings.py       # Gemini/fallback embeddings and ranking
│   │       ├── ingest.py           # Notes, URLs, files, and web search helpers
│   │       └── rag.py              # Ingestion and RAG orchestration
│   ├── tests/
│   │   ├── conftest.py             # Test database configuration
│   │   ├── test_api.py             # API integration tests
│   │   ├── test_database.py        # SQLite lifecycle tests
│   │   └── test_services.py        # Chunking, ingestion, and retrieval tests
│   ├── .env.example
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/             # Header, ingestion, inbox, and query UI
│   │   ├── api.js                  # Backend API client
│   │   ├── App.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
├── setup.bat / setup.sh            # Install backend and frontend dependencies
├── run_backend.bat / run_backend.sh # Backend launchers (use backend/.venv)
├── run_frontend.bat / run_frontend.sh # Frontend launchers
├── LICENSE
├── .github/workflows/ci.yml        # Backend tests and frontend build
├── README.md
└── DESIGN_TRADEOFFS.md
```

## Assignment fit

The project covers the assignment's core requirements:

| Requirement | Current implementation |
|---|---|
| Save plain text notes and URLs | `POST /ingest` |
| Store raw content and metadata | SQLite `items` table stores extracted content, type, URL/filename, title, and timestamp |
| Chunk, embed, retrieve top chunks | Recursive chunking, Gemini/fallback vectors, cosine + lexical ranking |
| LLM answer with cited sources | `POST /query` and source snippets; answer grounding is prompt-based, not guaranteed |
| React interface | Note/URL/file capture, inbox list, question UI, citations |
| Required API contract | `POST /ingest`, `GET /items`, `POST /query` are present |
| Tradeoff analysis | [DESIGN_TRADEOFFS.md](./DESIGN_TRADEOFFS.md) |
| Structured logging and validation | Logging setup and Pydantic request schemas are present |

The app goes beyond the minimum with file uploads, batch ingestion, SSE streaming, deletion, and opt-in web-assisted queries. These extras are not required for the assignment and should not compromise the reliability of the core note/URL-to-RAG path.

### Current readiness

**Assignment scope: substantially implemented; validation is in progress.** The core feature set is present, and the current changes add safer CORS defaults, URL destination checks, compatible setup scripts, embedding-dimension handling, and CI. A successful local test/build run or passing GitHub Actions run is still required before claiming the repository is fully verified.

## Requirements

- Python 3.10 or newer (Python 3.12 is a reasonable baseline for this project)
- Node.js compatible with the Vite version pinned by the lockfile; use a current supported Node.js LTS release
- npm
- A Google Gemini API key for live embedding and LLM features (optional for local fallback/demo behavior)
- Internet access for Gemini calls, URL ingestion, and web-assisted queries

## Run locally

### Recommended one-time setup

**Windows (Command Prompt or PowerShell):**

```bat
setup.bat
```

**macOS / Linux (Bash):**

```bash
bash setup.sh
```

The setup scripts create `backend/.venv`, install Python requirements, create `backend/.env` if missing, and install frontend dependencies using `npm ci` when a lockfile exists. The SQLite initialization path was also fixed to avoid recursive initialization when the database file is new. Setup does not require a Gemini key; add one to `backend/.env` to enable live Gemini generation.

Run the backend and frontend in separate terminals from the repository root.

### 1. Backend setup

**Windows PowerShell**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, you can call the environment's interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set your Google AI API key. A key is optional for deterministic local fallback behavior, but live Gemini generation will not be available without a valid key.

Start the API from the `backend/` directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend initializes the SQLite schema at application startup. By default, the database path resolves to `backend/data/knowledge_inbox.db`.

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health endpoint: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 2. Frontend setup

Open a second terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Vite prints the local development URL, normally [http://localhost:5173](http://localhost:5173).

The frontend defaults to `http://127.0.0.1:8000` for its API. To use a different backend, create `frontend/.env.local` with:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Restart Vite after changing frontend environment variables.

### 3. Optional launcher scripts

The launchers have been aligned with the setup scripts and use `backend/.venv`. On Windows, use the `.bat` files from Command Prompt or PowerShell. On macOS/Linux, use the `.sh` files from Bash. The shell scripts are not intended to run under Windows' native Command Prompt; use Git Bash/WSL only if your Python virtual environment is created for that environment.

- Backend: `run_backend.bat` or `bash run_backend.sh`
- Frontend: `run_frontend.bat` or `bash run_frontend.sh`

The two services run in separate terminals. The scripts fail early with a useful message if dependencies are missing.

## Configuration

Settings are loaded from `backend/.env` and can also be supplied as environment variables.

| Variable | Default in repository | Description |
|---|---|---|
| `GEMINI_API_KEY` | Empty in code; placeholder in example | Google AI API key. Leave empty for fallback mode. |
| `LLM_MODEL` | `gemini-3.8-flash` | Preferred answer-generation model; additional fallback model names are configured in `rag.py`. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model used for document and query embeddings. |
| `DATABASE_PATH` | `./data/knowledge_inbox.db` in the example, resolved relative to the process working directory; code default is backend data path | SQLite database file path. Prefer an absolute path in deployment. |
| `CHUNK_SIZE` | `500` | Target maximum character size used by the recursive splitter. |
| `CHUNK_OVERLAP` | `100` | Overlap seed length between chunks. Boundary logic can affect exact output size. |
| `TOP_K` | `4` | Configured default for retrieval. The API schema also defaults `top_k` to 4 and accepts values 1–10. |
| `HOST` | `127.0.0.1` | Host setting in configuration; launcher/manual commands must explicitly use the intended host. |
| `PORT` | `8000` | Port setting in configuration; launcher/manual commands must explicitly use the intended port. |
| `LOG_LEVEL` | `INFO` | Log-level setting. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated list of allowed frontend origins. Set the exact deployed frontend origin when hosting. |

Do not commit `backend/.env`, API keys, or real user documents. Use secret management rather than checked-in environment files for any hosted deployment.

## API reference

FastAPI's interactive schema is available at `/docs`. The routes below are implemented in `backend/app/main.py`.

| Method | Endpoint | Purpose | Successful response |
|---|---|---|---|
| `GET` | `/health` | Report service/model configuration | `200 OK` |
| `POST` | `/ingest` | Save a note or fetch and save a URL | `201 Created` |
| `POST` | `/ingest/file` | Upload one file | `201 Created` |
| `POST` | `/ingest/files` | Upload multiple files; response contains successful files and chunk total | `201 Created` for successful/partial batch results |
| `GET` | `/items` | List items, raw text, chunk count, and creation time | `200 OK` |
| `DELETE` | `/items/{item_id}` | Delete item and related chunks | `200 OK`; `404` if missing |
| `POST` | `/query` | Retrieve sources and return a RAG answer | `200 OK` |
| `POST` | `/query/stream` | Stream source and token events using SSE | `200 OK`, `text/event-stream` |
| `POST` | `/query/web-search` | Search/fetch public pages, ingest results, and query again | `200 OK` |

### Ingest a note

Request:

```http
POST /ingest
Content-Type: application/json
```

```json
{
  "source_type": "note",
  "title": "React Server Components",
  "content": "React Server Components can reduce client-side JavaScript because components can execute on the server."
}
```

`title` is optional. When omitted, the title is derived from the first line of the note.

### Ingest a URL

```json
{
  "source_type": "url",
  "url": "https://fastapi.tiangolo.com/",
  "title": "FastAPI Documentation"
}
```

The backend fetches the URL and extracts readable text. Only `http://` and `https://` prefixes are accepted by the request schema. This prefix validation alone is not a complete SSRF defense; see the security notes below.

### Upload files

For a single file, send multipart form data to `POST /ingest/file` with a `file` field and optional `title` field. For multiple files, send repeated `files` fields to `POST /ingest/files`.

Current parser behavior:
- PDF: extracts text with pypdf; scanned/image-only PDFs may yield no text.
- DOCX: extracts paragraph text with python-docx.
- Text-like extensions: includes `.txt`, `.md`, `.csv`, `.json`, `.py`, `.js`, and `.html`.
- Other formats may be attempted as UTF-8 text, so extension allowlisting and upload-size limits should be added before exposure to untrusted users.

### Ask a question

```http
POST /query
Content-Type: application/json
```

```json
{
  "question": "What do my notes say about React Server Components?",
  "top_k": 4
}
```

The response includes `question`, `answer`, `sources`, and `needs_web_search`. Each source contains the chunk and item identifiers, title/type, optional URL, excerpt content, and a ranking score called `similarity_score`.

### Streaming Q&A

`POST /query/stream` accepts the same request body as `/query` and returns SSE events:

- `sources`: JSON array of retrieved source snippets.
- `token`: JSON-encoded text pieces.
- `done`: terminal event with `[DONE]`.

The browser client reads the response stream and appends tokens as received. The stream endpoint does not currently emit a dedicated structured error event.

### Web-assisted question

`POST /query/web-search` accepts:

```json
{
  "question": "What is new in FastAPI?"
}
```

It attempts to discover and fetch up to two public web pages, ingests fetched text into the same persistent inbox, then runs retrieval and answer generation. This is an opt-in route from the UI, but results depend on third-party search/page behavior and network availability. The source code performs network requests and should not be exposed publicly without SSRF protections, timeouts/rate limits, and abuse controls.

## Testing

Run locally from the repository root:

```bash
cd backend
python -m pytest
```

The test suite covers API health, note ingestion/query/deletion, validation errors, streaming response headers, file and batch ingestion, oversized upload rejection, SQLite lifecycle, note-title handling, chunking, embeddings, ranking, and unsafe URL rejection.

The test no longer hard-codes an embedding dimension. Vector similarity now returns zero for mismatched dimensions, and retrieval does not pad/truncate vectors across embedding spaces. This avoids invalid comparisons but does not automatically re-embed old data: if switching between Gemini and fallback embeddings, delete/rebuild the local index before relying on vector ranking. Lexical ranking can still contribute when vectors are incompatible.

A GitHub Actions workflow in [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) installs backend dependencies, runs pytest without a Gemini key, and builds the frontend. Check the Actions tab for the actual run status. Do not treat the workflow as passing until GitHub reports both jobs successful.

## Known limitations and security notes

- **Single-user/local-first:** there is no authentication, authorization, per-user data isolation, or tenant model.
- **CORS:** allowed origins are now configurable through `CORS_ORIGINS` and default to the two local Vite origins; credentials are disabled. Configure the exact production frontend origin before deployment.
- **URL fetching and SSRF:** scheme checks do not block loopback, private-network, link-local, or cloud metadata targets; redirects can also change destinations. Do not expose URL ingestion or web search to untrusted clients until network-level URL validation and redirect checks are implemented.
- **Uploads:** single files are capped at 10 MiB and batches at 10 files. Files are read with a bounded read, but strict extension/content-type validation, a total batch-byte budget, and parser resource isolation are still recommended.
- **External dependencies:** content fetching, web search, Gemini API quotas, and model availability can fail or change.
- **Fallback is not equivalent to Gemini:** feature hashing provides lexical/subword similarity, not a semantic embedding model; fallback Q&A retrieves content but does not synthesize a grounded natural-language answer.
- **Embedding-space consistency:** vectors created by different models or fallback implementations should not be mixed. When changing embedding models or dimensions, re-embed existing chunks or version the embedding space.
- **Retrieval scalability:** each query loads all chunks from SQLite and ranks them in-process. There is no ANN index, background queue, or semantic cache.
- **SQLite concurrency:** suitable for a small local workload, but concurrent writes and multi-process deployments need careful handling.
- **Document extraction:** image-only PDFs and complex page layouts may need OCR or a more capable extraction pipeline.
- **Operational controls:** production use still needs authentication if exposed beyond a trusted single-user environment, upload/request size limits, rate limiting, metrics/tracing, backups, and a persistent-storage deployment strategy.

## Design decisions

This project intentionally keeps the current architecture simple for local development and review. The principal choices and their tradeoffs are documented in [DESIGN_TRADEOFFS.md](./DESIGN_TRADEOFFS.md).

In short:
- SQLite avoids a separate database service and makes local setup straightforward.
- Character-based recursive chunking is inexpensive and tunable, although it is less language-aware than token- or semantic-based chunking.
- NumPy full-scan ranking is easy to inspect and adequate for small collections, but its cost grows with the number of chunks.
- Gemini provides embedding and generation quality when available, while a deterministic fallback lets the rest of the workflow be exercised without an API key.

---

## License

This repository is licensed under the [MIT License](./LICENSE).
