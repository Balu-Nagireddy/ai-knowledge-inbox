import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from google import genai
from app.config import settings
from app.logging_config import logger

_client: Optional[genai.Client] = None

def get_genai_client() -> Optional[genai.Client]:
    """Retrieve or initialize the GenAI client if GEMINI_API_KEY is configured."""
    global _client
    api_key = settings.GEMINI_API_KEY.strip()
    if not api_key or api_key.startswith("your_gemini_api_key"):
        return None
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client

def _generate_mock_embedding(text: str, dim: int = 768) -> List[float]:
    """
    Generate a deterministic pseudo-random normalized embedding vector based on text hash.
    Used for local testing when GEMINI_API_KEY is not yet supplied.
    """
    hasher = hashlib.sha256(text.encode("utf-8")).digest()
    # Seed numpy RandomState with bytes from hash
    seed = int.from_bytes(hasher[:4], "big")
    rng = np.random.RandomState(seed)
    vector = rng.randn(dim).astype(np.float32)
    # Normalize to unit length
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using Google Gemini text-embedding-004.
    Falls back to mock embeddings if no API key is configured.
    """
    if not texts:
        return []

    client = get_genai_client()
    if not client:
        logger.warning("GEMINI_API_KEY not configured or placeholder detected. Using deterministic fallback embeddings for local preview.")
        return [_generate_mock_embedding(t) for t in texts]

    try:
        logger.info(f"Generating Gemini embeddings for {len(texts)} texts with model {settings.EMBEDDING_MODEL}")
        embeddings: List[List[float]] = []
        
        # Batch requests up to 50 texts per call
        batch_size = 50
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=batch
            )
            for emb in response.embeddings:
                embeddings.append(emb.values)

        return embeddings
    except Exception as exc:
        logger.error(f"Error calling Gemini Embeddings API: {exc}. Falling back to deterministic embeddings.")
        return [_generate_mock_embedding(t) for t in texts]

def generate_query_embedding(query: str) -> List[float]:
    """Generate an embedding for a single query text."""
    embeddings = generate_embeddings([query])
    return embeddings[0]

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def rank_chunks_by_similarity(
    query_embedding: List[float],
    chunks: List[Dict[str, Any]],
    top_k: int = 4
) -> List[Dict[str, Any]]:
    """
    Rank chunks by cosine similarity to query_embedding and return the top_k.
    """
    if not chunks:
        return []

    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    scored_chunks = []
    for chunk in chunks:
        chunk_vec = np.array(chunk["embedding"], dtype=np.float32)
        chunk_norm = np.linalg.norm(chunk_vec)
        if chunk_norm == 0:
            sim = 0.0
        else:
            sim = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
        
        scored_chunks.append({
            "chunk_id": chunk["id"],
            "item_id": chunk["item_id"],
            "source_title": chunk.get("source_title", "Unknown"),
            "source_type": chunk.get("source_type", "note"),
            "source_url": chunk.get("source_url"),
            "content": chunk["content"],
            "similarity_score": round(sim, 4)
        })

    # Sort descending by similarity score
    scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_chunks[:top_k]
