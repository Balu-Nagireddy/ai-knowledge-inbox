from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.logging_config import setup_logging, logger
from app.database import init_db, get_items, delete_item
from app.schemas import (
    IngestRequest, IngestResponse, BatchIngestResponse, ItemResponse,
    QueryRequest, QueryResponse, WebSearchRequest,
)
from app.services.ingest import IngestionError
from app.services.rag import (
    ingest_content, execute_rag_query, stream_rag_query,
    web_search_ingest_and_answer,
)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up AI Knowledge Inbox API...")
    init_db()
    logger.info("API is operational. LLM: %s, embeddings: %s", settings.LLM_MODEL, settings.EMBEDDING_MODEL)
    yield
    logger.info("Shutting down AI Knowledge Inbox API...")


app = FastAPI(
    title="AI Knowledge Inbox API",
    description="Local-first RAG backend for ingesting notes/URLs and answering knowledge queries.",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(IngestionError)
async def handle_ingestion_error(request, exc: IngestionError):
    logger.warning("Ingestion failed: %s", exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "error_type": "IngestionError"})


@app.exception_handler(Exception)
async def handle_unhandled_error(request, exc: Exception):
    logger.error("Unhandled server error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing your request.", "error_type": "InternalServerError"},
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Knowledge Inbox",
        "gemini_api_configured": bool(settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("your_gemini")),
        "models": {"llm": settings.LLM_MODEL, "embeddings": settings.EMBEDDING_MODEL},
    }


@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest(payload: IngestRequest):
    saved = await ingest_content(source_type=payload.source_type, content=payload.content, url=payload.url, custom_title=payload.title)
    return IngestResponse(
        id=saved["id"], source_type=saved["source_type"], title=saved["title"],
        source_url=saved["source_url"], chunk_count=saved["chunk_count"], created_at=saved["created_at"],
    )


async def _read_limited_upload(file: UploadFile) -> bytes:
    limit = settings.MAX_UPLOAD_BYTES
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"File exceeds the {limit}-byte upload limit.")
    return content


@app.post("/ingest/file", response_model=IngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest_file(file: UploadFile = File(...), title: Optional[str] = Form(None)):
    try:
        file_bytes = await _read_limited_upload(file)
        saved = await ingest_content(
            source_type="file", file_bytes=file_bytes, filename=file.filename or "upload.txt", custom_title=title,
        )
        return IngestResponse(
            id=saved["id"], source_type=saved["source_type"], title=saved["title"],
            source_url=saved["source_url"], chunk_count=saved["chunk_count"], created_at=saved["created_at"],
        )
    except IngestionError:
        raise
    except HTTPException:
        raise
    except Exception:
        logger.exception("File ingestion failed")
        raise HTTPException(status_code=500, detail="File ingestion failed.")


@app.post("/ingest/files", response_model=BatchIngestResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def ingest_multiple_files(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > settings.MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"Batch exceeds the {settings.MAX_BATCH_FILES}-file limit.")

    saved_items: List[IngestResponse] = []
    total_chunks = 0
    errors: List[str] = []
    for file in files:
        try:
            file_bytes = await _read_limited_upload(file)
            saved = await ingest_content(
                source_type="file", file_bytes=file_bytes,
                filename=file.filename or "upload.txt", custom_title=file.filename,
            )
            saved_items.append(IngestResponse(
                id=saved["id"], source_type=saved["source_type"], title=saved["title"],
                source_url=saved["source_url"], chunk_count=saved["chunk_count"], created_at=saved["created_at"],
            ))
            total_chunks += saved["chunk_count"]
        except Exception as exc:
            logger.warning("Batch ingestion failed for %s: %s", file.filename, type(exc).__name__)
            errors.append(f"{file.filename or 'unnamed file'}: ingestion failed")
    if not saved_items and errors:
        raise HTTPException(status_code=422, detail="No files could be ingested.")
    return BatchIngestResponse(items=saved_items, total_files=len(saved_items), total_chunks=total_chunks)


@app.get("/items", response_model=List[ItemResponse], tags=["Items"])
async def list_items():
    return get_items()


@app.delete("/items/{item_id}", status_code=status.HTTP_200_OK, tags=["Items"])
async def remove_item(item_id: str):
    if not delete_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted successfully", "id": item_id}


@app.post("/query", response_model=QueryResponse, tags=["RAG"])
async def query(payload: QueryRequest):
    try:
        return QueryResponse(**(await execute_rag_query(question=payload.question, top_k=payload.top_k or settings.TOP_K)))
    except Exception:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail="Failed to process query.")


@app.post("/query/stream", tags=["RAG"])
async def query_stream(payload: QueryRequest):
    return StreamingResponse(
        stream_rag_query(question=payload.question, top_k=payload.top_k or settings.TOP_K),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/query/web-search", response_model=QueryResponse, tags=["RAG"])
async def query_web_search(payload: WebSearchRequest):
    try:
        return QueryResponse(**(await web_search_ingest_and_answer(question=payload.question)))
    except Exception:
        logger.exception("Web search query failed")
        raise HTTPException(status_code=502, detail="Web search retrieval failed.")
