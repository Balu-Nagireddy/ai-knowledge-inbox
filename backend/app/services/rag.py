import json
import time
import uuid
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from app.config import settings
from app.logging_config import logger
from app.database import (
    save_item_with_chunks,
    get_all_chunks,
    get_items
)
from app.services.ingest import process_note_content, fetch_url_content, IngestionError
from app.services.chunker import chunk_content
from app.services.embeddings import (
    generate_embeddings,
    generate_query_embedding,
    rank_chunks_by_similarity,
    get_genai_client
)

async def ingest_content(
    source_type: str,
    content: Optional[str] = None,
    url: Optional[str] = None,
    custom_title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrate full ingestion workflow:
    1. Extract & clean content based on source_type (note or url)
    2. Chunk content recursively with semantic boundary preservation and overlap
    3. Generate vector embeddings for all chunks (Gemini text-embedding-004)
    4. Transactionally persist item and chunks in SQLite
    """
    logger.info(f"Starting ingestion: source_type={source_type}")
    
    if source_type == "note":
        title, clean_text = process_note_content(content or "", custom_title)
        source_url = None
    elif source_type == "url":
        if not url:
            raise IngestionError("URL is required for 'url' source_type.", status_code=400)
        title, clean_text = await fetch_url_content(url, custom_title)
        source_url = url
    else:
        raise IngestionError(f"Unsupported source_type '{source_type}'.", status_code=400)

    # Chunking
    chunks = chunk_content(clean_text)
    if not chunks:
        raise IngestionError("Unable to extract valid text chunks from content.", status_code=422)

    # Embeddings
    chunk_texts = [c["content"] for c in chunks]
    embeddings = generate_embeddings(chunk_texts)

    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb

    item_id = str(uuid.uuid4())
    saved_item = save_item_with_chunks(
        item_id=item_id,
        source_type=source_type,
        title=title,
        raw_content=clean_text,
        source_url=source_url,
        chunks=chunks
    )

    logger.info(f"Ingestion complete for item {item_id} ('{title}') with {len(chunks)} chunks.")
    return saved_item

def build_rag_prompt(question: str, context_chunks: List[Dict[str, Any]]) -> str:
    """
    Construct a grounded RAG prompt instructing the LLM to format answers nicely with markdown,
    cite sources cleanly with brackets [1], [2], and avoid hallucinations.
    """
    formatted_context = []
    for idx, chunk in enumerate(context_chunks, 1):
        source_ref = chunk['source_title']
        if chunk.get('source_url'):
            source_ref += f" ({chunk['source_url']})"
        formatted_context.append(
            f"[[{idx}]] Source: {source_ref}\nExcerpt:\n{chunk['content']}"
        )
    
    context_str = "\n\n---\n\n".join(formatted_context)

    prompt = f"""You are an advanced AI Knowledge Assistant.
Answer the user's question accurately, concisely, and thoroughly based ONLY on the context excerpts provided below from their Knowledge Inbox.

Instructions:
1. Format your response cleanly using Markdown (use bolding, bullet points, headers, or concise paragraphs as appropriate).
2. Ground your claims by citing the corresponding source numbers in brackets (e.g. [[1]], [[2]]) when stating specific facts.
3. If the context excerpts do not contain sufficient information to answer the question truthfully, state:
"Based on the items currently saved in your Knowledge Inbox, there is not enough information to answer this question." Do not fabricate information.

=== Context Excerpts ===
{context_str}

=== User Question ===
{question}

=== Grounded Response ==="""
    return prompt

async def execute_rag_query(question: str, top_k: int = 4) -> Dict[str, Any]:
    """
    Execute semantic retrieval and LLM answer generation with retry resilience.
    """
    logger.info(f"Executing RAG query: '{question}' (top_k={top_k})")
    
    all_chunks = get_all_chunks()
    if not all_chunks:
        return {
            "question": question,
            "answer": "Your Knowledge Inbox is currently empty. Add notes or URLs first to ask questions!",
            "sources": []
        }

    # Embed query and rank
    query_emb = generate_query_embedding(question)
    top_chunks = rank_chunks_by_similarity(query_emb, all_chunks, top_k=top_k)

    if not top_chunks:
        return {
            "question": question,
            "answer": "No relevant content was found in your Knowledge Inbox for this query.",
            "sources": []
        }

    client = get_genai_client()
    
    if client:
        rag_prompt = build_rag_prompt(question, top_chunks)
        answer_text = None
        max_retries = 3

        for attempt in range(max_retries):
            try:
                logger.info(f"Invoking Gemini model {settings.LLM_MODEL} (attempt {attempt+1}/{max_retries})...")
                response = client.models.generate_content(
                    model=settings.LLM_MODEL,
                    contents=rag_prompt
                )
                if response and response.text:
                    answer_text = response.text.strip()
                    break
            except Exception as exc:
                logger.warning(f"Gemini LLM call attempt {attempt+1} failed: {exc}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    logger.error(f"All {max_retries} attempts to call Gemini LLM failed.")
                    answer_text = (
                        f"Unable to reach the Gemini LLM after retrying ({str(exc)}). "
                        "Below are the most relevant excerpts retrieved from your inbox."
                    )
    else:
        answer_text = (
            "*(Demo mode: GEMINI_API_KEY is not configured or in preview)*\n\n"
            f"Retrieved {len(top_chunks)} relevant knowledge snippet(s) matching your query from your inbox. "
            "Configure a valid GEMINI_API_KEY in `backend/.env` to enable live LLM generation!"
        )

    return {
        "question": question,
        "answer": answer_text or "Unable to synthesize answer.",
        "sources": top_chunks
    }

async def stream_rag_query(question: str, top_k: int = 4) -> AsyncGenerator[str, None]:
    """
    Generator yielding Server-Sent Events (SSE) for real-time streaming answer delivery.
    """
    all_chunks = get_all_chunks()
    if not all_chunks:
        yield f"event: sources\ndata: {json.dumps([])}\n\n"
        yield f"event: token\ndata: {json.dumps('Your Knowledge Inbox is currently empty. Add notes or URLs first to ask questions!')}\n\n"
        yield "event: done\ndata: [DONE]\n\n"
        return

    query_emb = generate_query_embedding(question)
    top_chunks = rank_chunks_by_similarity(query_emb, all_chunks, top_k=top_k)

    # First emit retrieved sources
    yield f"event: sources\ndata: {json.dumps(top_chunks)}\n\n"

    client = get_genai_client()
    if not client:
        fallback_msg = (
            "*(Demo mode: GEMINI_API_KEY is not configured)*\n\n"
            f"Retrieved {len(top_chunks)} relevant knowledge snippet(s) matching your query from your inbox. "
            "Configure a valid GEMINI_API_KEY in `backend/.env` to enable live LLM generation!"
        )
        for word in fallback_msg.split(" "):
            yield f"event: token\ndata: {json.dumps(word + ' ')}\n\n"
            await asyncio.sleep(0.04)
        yield "event: done\ndata: [DONE]\n\n"
        return

    rag_prompt = build_rag_prompt(question, top_chunks)
    try:
        response_stream = client.models.generate_content_stream(
            model=settings.LLM_MODEL,
            contents=rag_prompt
        )
        for chunk in response_stream:
            if chunk.text:
                yield f"event: token\ndata: {json.dumps(chunk.text)}\n\n"
    except Exception as exc:
        logger.error(f"Streaming error from Gemini: {exc}")
        yield f"event: token\ndata: {json.dumps(f'Error during streaming: {str(exc)}')}\n\n"

    yield "event: done\ndata: [DONE]\n\n"
