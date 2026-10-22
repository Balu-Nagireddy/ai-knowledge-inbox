from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.logging_config import setup_logging, logger
from app.database import init_db, get_items, delete_item
from app.schemas import (
    IngestRequest,
    IngestResponse,
    BatchIngestResponse,
    ItemResponse,
    QueryRequest,
    QueryResponse,
    WebSearchRequest
)
from app.services.ingest import IngestionError
from app.services.rag import ingest_content, execute_rag_query, stream_rag_query, web_search_ingest_and_answer

# Initialize logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up AI Knowledge Inbox API...")
    init_db()
    logger.info(f"API is operational. LLM: {settings.LLM_MODEL}, Embeddings: {settings.EMBEDDING_MODEL}")
    yield
    # Shutdown actions
    logger.info("Shutting down AI Knowledge Inbox API...")

app = FastAPI(
    title="AI Knowledge Inbox API",
    description="Local-first RAG backend for ingesting notes, URLs, and documents and answering grounded questions.",
    version="1.1.0",
    lifespan=lifespan
)

# CORS Middleware for local frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Exception Handlers for clear error responses
@app.exception_handler(IngestionError)
async def handle_ingestion_error(request, exc: IngestionError):
    logger.warning(f"Ingestion failed: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_type": "IngestionError"}
    )

@app.exception_handler(Exception)
async def handle_unhandled_error(request, exc: Exception):
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing your request.", "error_type": "InternalServerError"}
    )

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint indicating service status and configuration."""
    return {
        "status": "healthy",
        "service": "AI Knowledge Inbox",
        "gemini_api_configured": bool(settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_gemini")),
        "models": {
            "llm": settings.LLM_MODEL,
            "embeddings": settings.EMBEDDING_MODEL
        }
    }

@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest(payload: IngestRequest):
    """
    Ingest a new text note or web URL:
    - Extracts & normalizes content
    - Generates semantic chunks with boundary-aware overlap
    - Calculates vector embeddings
    - Persists item and chunks in SQLite
    """
    logger.info(f"Received ingestion request: type={payload.source_type}")
    try:
        saved_item = await ingest_content(
            source_type=payload.source_type,
            content=payload.content,
            url=payload.url,
            custom_title=payload.title
        )
        return IngestResponse(
            id=saved_item["id"],
            source_type=saved_item["source_type"],
            title=saved_item["title"],
            source_url=saved_item["source_url"],
            chunk_count=saved_item["chunk_count"],
            created_at=saved_item["created_at"]
        )
    except IngestionError:
        raise
@app.post("/ingest/file", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest_file(
    file: UploadFile = File(..., description="Uploaded document (PDF, Word, Markdown, Text)"),
    title: Optional[str] = Form(None, description="Optional custom title")
):
    """
    Ingest an uploaded document file:
    - Extracts text from PDF, Word (.docx), Markdown (.md), or plain text (.txt)
    - Generates chunks and embeddings
    - Persists item and chunks in SQLite
    """
    logger.info(f"Received file upload: {file.filename}")
    try:
        file_bytes = await file.read()
        saved_item = await ingest_content(
            source_type="file",
            file_bytes=file_bytes,
            filename=file.filename,
            custom_title=title
        )
        return IngestResponse(
            id=saved_item["id"],
            source_type=saved_item["source_type"],
            title=saved_item["title"],
            source_url=saved_item["source_url"],
            chunk_count=saved_item["chunk_count"],
            created_at=saved_item["created_at"]
        )
    except IngestionError:
        raise
    except Exception as exc:
        logger.error(f"File ingestion error: {exc}", exc_info=True)
        logger.error("File ingestion failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to ingest file.")

@app.post("/ingest/files", response_model=BatchIngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest_multiple_files(
    files: List[UploadFile] = File(..., description="List of document files to ingest at once")
):
    """
    Ingest multiple uploaded document files in a single batch operation.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    logger.info(f"Received batch file upload with {len(files)} files.")
    saved_items: List[IngestResponse] = []
    total_chunks = 0
    errors: List[str] = []

    for f in files:
        try:
            file_bytes = await f.read()
            saved = await ingest_content(
                source_type="file",
                file_bytes=file_bytes,
                filename=f.filename,
                custom_title=f.filename
            )
            resp = IngestResponse(
                id=saved["id"],
                source_type=saved["source_type"],
                title=saved["title"],
                source_url=saved["source_url"],
                chunk_count=saved["chunk_count"],
                created_at=saved["created_at"]
            )
            saved_items.append(resp)
            total_chunks += saved["chunk_count"]
        except Exception as exc:
            logger.error(f"Failed to ingest batch file '{f.filename}': {exc}")
            errors.append(f"{f.filename}: {str(exc)}")

    if not saved_items and errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    return BatchIngestResponse(
        items=saved_items,
        total_files=len(saved_items),
        total_chunks=total_chunks
    )

@app.get("/items", response_model=List[ItemResponse], tags=["Items"])
async def list_items():
    """
    Retrieve all saved notes and URLs in reverse chronological order.
    """
    logger.info("Listing all saved knowledge items.")
    items = get_items()
    return items

@app.delete("/items/{item_id}", status_code=status.HTTP_200_OK, tags=["Items"])
async def remove_item(item_id: str):
    """
    Delete a knowledge item and all associated vector chunks.
    """
    logger.info(f"Deleting item: {item_id}")
    success = delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted successfully", "id": item_id}

@app.post("/query", response_model=QueryResponse, tags=["RAG"])
async def query(payload: QueryRequest):
    """
    Standard synchronous query endpoint returning synthesized answer and cited sources.
    """
    logger.info(f"Received user query: '{payload.question}'")
    try:
        result = await execute_rag_query(question=payload.question, top_k=payload.top_k or 4)
        return QueryResponse(**result)
    except Exception as exc:
        logger.error(f"Query endpoint error: {exc}", exc_info=True)
        logger.error("Query processing failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process query.")

@app.post("/query/stream", tags=["RAG"])
async def query_stream(payload: QueryRequest):
    """
    Streaming query endpoint delivering tokens in real-time via Server-Sent Events (SSE).
    """
    logger.info(f"Received streaming query: '{payload.question}'")
    return StreamingResponse(
        stream_rag_query(question=payload.question, top_k=payload.top_k or 4),
        media_type="text/event-stream"
    )

@app.post("/query/web-search", response_model=QueryResponse, tags=["RAG"])
async def query_web_search(payload: WebSearchRequest):
    """
    Interactive web fallback:
    Searches web for the question, fetches top articles, ingests them into Knowledge Inbox,
    and returns a newly grounded answer with fresh citations.
    """
    logger.info(f"Triggered web search & ingest for question: '{payload.question}'")
    try:
        result = await web_search_ingest_and_answer(question=payload.question)
        return QueryResponse(**result)
    except Exception as exc:
        logger.error(f"Web search ingest error: {exc}", exc_info=True)
        logger.error("Web-assisted query failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Web-assisted query failed. Check upstream connectivity and try again.")

