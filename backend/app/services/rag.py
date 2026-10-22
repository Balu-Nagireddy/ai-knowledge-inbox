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
from app.services.ingest import (
    process_note_content,
    fetch_url_content,
    process_file_content,
    search_and_fetch_web,
    IngestionError
)
from app.services.chunker import chunk_content
from app.services.embeddings import (
    generate_embeddings,
    generate_query_embedding,
    rank_chunks_by_similarity,
    get_genai_client
)

# Prioritize gemini-3.8-flash first; seamlessly failover if daily 20-request quota is exhausted (429)
MODELS_PRIORITY = [settings.LLM_MODEL,"gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]


async def ingest_content(
    source_type: str,
    content: Optional[str] = None,
    url: Optional[str] = None,
    custom_title: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrate full ingestion workflow for notes, URLs, or uploaded files.
    """
    logger.info(f"Starting ingestion: source_type={source_type}")
    
    if source_type == "note":
        title, clean_text = process_note_content(content or "", custom_title)
        source_url = None
    elif source_type == "url":
        if not url:
            raise IngestionError("URL is required for 'url' source_type.", status_code=400)
        if content and content.strip():
            title = custom_title or url
            clean_text = content.strip()
        else:
            title, clean_text = await fetch_url_content(url, custom_title)
        source_url = url
    elif source_type == "file":
        if not file_bytes or not filename:
            raise IngestionError("File content and filename are required for 'file' source_type.", status_code=400)
        title, clean_text = process_file_content(file_bytes, filename, custom_title)
        source_url = filename
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
    cite sources cleanly with brackets [1], [2], and detect when saved inbox lacks enough information.
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
"Based on the items currently saved in your Knowledge Inbox, there is not enough information to answer this question."
Do not fabricate information.

=== Context Excerpts ===
{context_str}

=== User Question ===
{question}

=== Grounded Response ==="""
    return prompt

async def execute_rag_query(question: str, top_k: int = 4) -> Dict[str, Any]:
    """
    Execute semantic retrieval and LLM answer generation with multi-model failover.
    """
    logger.info(f"Executing RAG query: '{question}' (top_k={top_k})")
    
    all_chunks = get_all_chunks()
    if not all_chunks:
        return {
            "question": question,
            "answer": "Your Knowledge Inbox is currently empty. Add notes, files, or URLs first to ask questions!",
            "sources": [],
            "needs_web_search": True
        }

    # Embed query and rank
    query_emb = generate_query_embedding(question)
    top_chunks = rank_chunks_by_similarity(query_emb, all_chunks, top_k=top_k)

    if not top_chunks:
        return {
            "question": question,
            "answer": "No relevant content was found in your Knowledge Inbox for this query.",
            "sources": [],
            "needs_web_search": True
        }

    client = get_genai_client()
    answer_text = None
    
    if client:
        rag_prompt = build_rag_prompt(question, top_chunks)
        
        last_error = None
        for model_name in MODELS_PRIORITY:
            try:
                logger.info(f"Invoking Gemini model '{model_name}'...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=rag_prompt
                )
                if response and response.text:
                    answer_text = response.text.strip()
                    logger.info(f"Successfully generated answer using '{model_name}'.")
                    break
            except Exception as exc:
                last_error = exc
                logger.warning(f"Model '{model_name}' failed ({exc}). Failing over to next model in priority...")
                await asyncio.sleep(0.5)
                
        if not answer_text:
            logger.error(f"All models exhausted: {last_error}")
            answer_text = "Encountered a temporary issue communicating with the AI service. Please try again."
    else:
        answer_text = (
            "*(Demo mode: GEMINI_API_KEY is not configured or in preview)*\n\n"
            f"Retrieved {len(top_chunks)} relevant knowledge snippet(s) matching your query from your inbox. "
            "Configure a valid GEMINI_API_KEY in `backend/.env` to enable live LLM generation!"
        )

    # Detect if answer indicates insufficient knowledge
    needs_web = False
    lower_ans = (answer_text or "").lower()
    if "not enough information" in lower_ans or "doesn't contain" in lower_ans or "inbox is currently empty" in lower_ans:
        needs_web = True

    return {
        "question": question,
        "answer": answer_text or "Unable to synthesize answer.",
        "sources": top_chunks,
        "needs_web_search": needs_web
    }

async def stream_rag_query(question: str, top_k: int = 4) -> AsyncGenerator[str, None]:
    """
    Generator yielding Server-Sent Events (SSE) for real-time streaming answer delivery with failover.
    """
    all_chunks = get_all_chunks()
    if not all_chunks:
        yield f"event: sources\ndata: {json.dumps([])}\n\n"
        yield f"event: token\ndata: {json.dumps('Your Knowledge Inbox is currently empty. Add notes, files, or URLs first to ask questions!')}\n\n"
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
    stream_success = False

    for model_name in MODELS_PRIORITY:
        try:
            logger.info(f"Streaming with Gemini model '{model_name}'...")
            response_stream = client.models.generate_content_stream(
                model=model_name,
                contents=rag_prompt
            )
            for chunk in response_stream:
                if chunk.text:
                    yield f"event: token\ndata: {json.dumps(chunk.text)}\n\n"
            stream_success = True
            logger.info(f"Streaming completed successfully using '{model_name}'.")
            break
        except Exception as exc:
            logger.warning(f"Streaming with '{model_name}' failed: {exc}. Trying next priority model...")
            await asyncio.sleep(0.5)

    if not stream_success:
        yield f"event: token\ndata: {json.dumps('Encountered a temporary issue communicating with Gemini AI. Please retry.')}\n\n"

    yield "event: done\ndata: [DONE]\n\n"

async def web_search_ingest_and_answer(question: str) -> Dict[str, Any]:
    """
    Interactive web fallback:
    1. Search the web for relevant content
    2. Automatically ingest articles into Knowledge Inbox (chunks + embeds + SQLite)
    3. Run RAG over the newly enriched knowledge base and synthesize the answer
    """
    logger.info(f"Executing web-search & ingest workflow for query: '{question}'")
    articles = await search_and_fetch_web(question, max_results=2)
    
    newly_ingested = []
    for art in articles:
        try:
            saved = await ingest_content(
                source_type="url",
                url=art["url"],
                custom_title=art.get("title"),
                content=art.get("content")
            )
            newly_ingested.append(saved)
        except Exception as exc:
            logger.warning(f"Could not ingest web search article {art.get('url')}: {exc}")

    # Now re-execute query over the updated inbox
    result = await execute_rag_query(question=question, top_k=4)
    result["newly_ingested_count"] = len(newly_ingested)
    return result
