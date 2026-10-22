from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.logging_config import setup_logging, logger
from app.database import init_db, get_items, delete_item
from app.schemas import IngestRequest, IngestResponse, ItemResponse, QueryRequest, QueryResponse
from app.services.ingest import IngestionError
from app.services.rag import ingest_content, execute_rag_query, stream_rag_query

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
    description="Production-style minimal RAG backend for ingesting notes/URLs and answering semantic queries.",
    version="1.1.0",
    lifespan=lifespan
)

# CORS Middleware for local frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    except Exception as exc:
        logger.error(f"Ingest endpoint error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to ingest content: {str(exc)}")

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
        raise HTTPException(status_code=500, detail=f"Failed to process query: {str(exc)}")

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
