import uuid
from typing import Dict, Any, List, Optional
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
    Construct a grounded RAG prompt instructing the LLM to strictly rely on context
    and explicitly cite source titles and URLs.
    """
    formatted_context = []
    for idx, chunk in enumerate(context_chunks, 1):
        source_ref = chunk['source_title']
        if chunk.get('source_url'):
            source_ref += f" ({chunk['source_url']})"
        formatted_context.append(
            f"[Source {idx}: {source_ref}]\n{chunk['content']}"
        )
    
    context_str = "\n\n---\n\n".join(formatted_context)

    prompt = f"""You are a helpful Knowledge Assistant. Answer the user's question using ONLY the provided context snippets from their Knowledge Inbox.

Guidelines:
1. Answer the question accurately, concisely, and directly.
2. Explicitly cite your sources using bracket notation like [Source 1] or mentioning the source title.
3. If the provided context does not contain enough information to answer the question truthfully, state: "Based on your saved knowledge inbox, I don't have enough information to answer this question." Do not make up facts.

Context Snippets:
{context_str}

User Question:
{question}

Answer:"""
    return prompt

async def execute_rag_query(question: str, top_k: int = 4) -> Dict[str, Any]:
    """
    Execute semantic retrieval and LLM answer generation:
    1. Embed query
    2. Retrieve top-k relevant chunks from SQLite via cosine similarity
    3. Generate grounded answer with Gemini LLM
    4. Return answer + cited source snippets
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
        try:
            rag_prompt = build_rag_prompt(question, top_chunks)
            logger.info(f"Invoking Gemini model {settings.LLM_MODEL} for answer generation.")
            response = client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=rag_prompt
            )
            answer_text = response.text.strip() if response.text else "Unable to generate an answer."
        except Exception as exc:
            logger.error(f"Error calling Gemini LLM: {exc}")
            answer_text = (
                f"Encountered an issue communicating with the Gemini LLM ({str(exc)}). "
                "Here are the most relevant excerpts retrieved from your inbox:"
            )
    else:
        # Fallback response for offline/mock mode
        answer_text = (
            "*(Demo mode: GEMINI_API_KEY is not configured or in preview)*\n\n"
            f"Retrieved {len(top_chunks)} relevant knowledge snippet(s) matching your query from your inbox. "
            "Configure a valid GEMINI_API_KEY in backend/.env to enable live LLM generation!"
        )

    return {
        "question": question,
        "answer": answer_text,
        "sources": top_chunks
    }
