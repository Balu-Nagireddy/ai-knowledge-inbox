# AI Knowledge Inbox 📥 🧠

A production-style minimal web application that lets users save plain text notes and web URLs, indexes them with semantic vector embeddings, and answers user questions grounded in their saved content using a Retrieval-Augmented Generation (RAG) pipeline powered by Google Gemini.

---

## 🚀 Key Features

1. **Dual Ingestion Engine**:
   - **Plain Notes**: Fast text ingestion with automatic title deduction from header or first line.
   - **Server-Side URL Fetcher**: Scrapes remote web pages, strips boilerplate (scripts, styles, headers, nav, footers), extracts clean readable body content, and resolves titles.
2. **Intentional Boundary-Aware Chunking**:
   - Recursive character chunking respecting paragraph breaks, sentence boundaries (`. `, `! `, `? `), and word boundaries with a configurable 100-character overlap.
3. **Semantic Vector Search**:
   - High-dimensional vector embeddings using Google Gemini `text-embedding-004`.
   - SQLite persistent storage with fast vectorized cosine similarity ranking via NumPy.
4. **Grounded RAG Q&A Pipeline**:
   - Context-grounded prompting with anti-hallucination guardrails.
   - Synthesizes accurate responses with explicit source citations and similarity scores.
5. **Modern, Responsive Frontend**:
   - Built with React, Vite, and Lucide icons.
   - Glassmorphic interface with status indicators, tabbed ingestion, inbox management, and interactive query cards.
6. **Graceful Demo Mode**:
   - If `GEMINI_API_KEY` is not provided, the application runs in a deterministic fallback mode without crashing.

---

## 🏗️ Architecture & Building Blocks

```
AI_Knowledge_Inbox/
├── backend/
│   ├── app/
│   │   ├── config.py             # Pydantic Settings & environment variables
│   │   ├── database.py           # SQLite connection, schema & transactional repository
│   │   ├── logging_config.py     # Structured logging configuration
│   │   ├── models.py / schemas.py# Pydantic v2 schemas for request/response validation
│   │   ├── services/
│   │   │   ├── ingest.py         # URL fetcher, HTML sanitizer & note parser
│   │   │   ├── chunker.py        # Recursive semantic chunker with overlap
│   │   │   ├── embeddings.py     # Gemini embeddings & NumPy cosine similarity engine
│   │   │   └── rag.py            # RAG orchestration & prompt generation
│   │   └── main.py               # FastAPI application, CORS & REST endpoints
│   ├── tests/                    # Comprehensive Pytest suite (database, services, API)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api.js                # Clean API client wrapper
│   │   ├── components/
│   │   │   ├── Header.jsx        # App header & status indicators
│   │   │   ├── IngestBox.jsx     # Tabbed note & URL ingestion form
│   │   │   ├── KnowledgeInbox.jsx# Saved items feed with badges & actions
│   │   │   └── AskKnowledge.jsx  # Semantic search & cited answer viewer
│   │   ├── App.jsx               # Application state orchestration
│   │   └── index.css             # Design tokens & glassmorphic styles
│   ├── package.json
│   └── vite.config.js
├── README.md                     # Setup instructions & project documentation
└── DESIGN_TRADEOFFS.md           # In-depth architectural tradeoffs & scaling analysis
```

---

## 🛠️ Tech Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLite3, NumPy, BeautifulSoup4, HTTPX, Google GenAI SDK.
- **Frontend**: React 19, Vite, Lucide React, Modern CSS (Glassmorphism, Flex/Grid).
- **AI / LLM**: Google Gemini (`gemini-2.0-flash` or `gemini-1.5-flash`), `text-embedding-004`.

---

## 🏁 Getting Started (Local Setup)

### Prerequisites
- **Python 3.10+** (Tested on Python 3.12)
- **Node.js 18+** (Tested on Node v24)
- **Google Gemini API Key** (Get one free at [Google AI Studio](https://aistudio.google.com/))

---

### Step 1: Backend Setup

1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   - **Windows**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure your environment variables:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Open `.env` and add your `GEMINI_API_KEY`:
     ```env
     GEMINI_API_KEY=your_actual_gemini_api_key_here
     LLM_MODEL=gemini-2.0-flash
     EMBEDDING_MODEL=text-embedding-004
     ```

5. Run unit and integration tests:
   ```bash
   pytest
   ```
   *(All 8 tests should pass)*

6. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *The backend will be live at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.*

---

### Step 2: Frontend Setup

1. Open a second terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open `http://localhost:5173` in your browser.

---

## 📡 API Reference

### 1. Ingest Content
`POST /ingest`
- **Request Body (Note)**:
  ```json
  {
    "source_type": "note",
    "title": "React Server Components",
    "content": "RSCs execute solely on the server and do not increase client bundle size."
  }
  ```
- **Request Body (URL)**:
  ```json
  {
    "source_type": "url",
    "url": "https://fastapi.tiangolo.com/"
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "id": "c1f7b82e-9d2a-4f51-bfa6-1e5b4f849e77",
    "source_type": "note",
    "title": "React Server Components",
    "source_url": null,
    "chunk_count": 1,
    "created_at": "2026-10-22T06:15:00.000000+00:00"
  }
  ```

### 2. List Saved Items
`GET /items`
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "c1f7b82e-9d2a-4f51-bfa6-1e5b4f849e77",
      "source_type": "note",
      "source_url": null,
      "title": "React Server Components",
      "raw_content": "RSCs execute solely on the server...",
      "chunk_count": 1,
      "created_at": "2026-10-22T06:15:00.000000+00:00"
    }
  ]
  ```

### 3. Ask Semantic Query (RAG)
`POST /query`
- **Request Body**:
  ```json
  {
    "question": "What are the bundle size advantages of React Server Components?",
    "top_k": 4
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "question": "What are the bundle size advantages of React Server Components?",
    "answer": "React Server Components execute entirely on the server and therefore do not add any JavaScript to the client-side bundle [Source 1].",
    "sources": [
      {
        "chunk_id": "8fa3c09b-...",
        "item_id": "c1f7b82e-...",
        "source_title": "React Server Components",
        "source_type": "note",
        "source_url": null,
        "content": "RSCs execute solely on the server and do not increase client bundle size.",
        "similarity_score": 0.8921
      }
    ]
  }
  ```

### 4. System Health Check
`GET /health`
- **Response** (`200 OK`):
  ```json
  {
    "status": "healthy",
    "service": "AI Knowledge Inbox",
    "gemini_api_configured": true,
    "models": {
      "llm": "gemini-2.0-flash",
      "embeddings": "text-embedding-004"
    }
  }
  ```

---

## ⚖️ Tradeoffs & System Design

For a comprehensive analysis of:
- **Chunking Strategy Rationale**
- **Vector Store Selection**
- **What Breaks at Scale**
- **Production Architecture & Queue Roadmap**

👉 **Read the full [DESIGN_TRADEOFFS.md](file:///c:/Users/s5cd3/Assignment/AI_Knowledge_Inbox/DESIGN_TRADEOFFS.md)**.
