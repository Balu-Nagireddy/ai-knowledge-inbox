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

def _generate_mock_embedding(text: str, dim: int = 3072) -> List[float]:
    """
    Generate a deterministic feature-hashing term-frequency vector (3072 dimensions).
    Accurately maps word and subword overlaps between queries and saved documents
    even during API rate limits or offline mode.
    """
    import re, math
    vec = [0.0] * dim
    words = re.findall(r'\b[a-zA-Z0-9_-]{2,}\b', text.lower())
    if not words:
        return vec
    for w in words:
        # Word hashing
        h = int(hashlib.md5(w.encode('utf-8')).hexdigest(), 16) % dim
        vec[h] += 1.0
        # Subword 3-grams for fuzzy matching
        if len(w) >= 4:
            for i in range(len(w) - 2):
                ngram = w[i:i+3]
                nh = int(hashlib.md5(ngram.encode('utf-8')).hexdigest(), 16) % dim
                vec[nh] += 0.3
    # L2 normalize to unit length
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 5) for v in vec]
    return vec

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using Google Gemini gemini-embedding-001.
    Falls back to feature-hashing vector embeddings if API encounters rate limits.
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
        
        # Batch requests up to 30 texts per call
        batch_size = 30
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
        logger.error(f"Error calling Gemini Embeddings API: {exc}. Falling back to deterministic feature-hashing embeddings.")
        return [_generate_mock_embedding(t) for t in texts]


def generate_query_embedding(query: str) -> List[float]:
    """Generate an embedding for a single query text."""
    embeddings = generate_embeddings([query])
    return embeddings[0]

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    # Vectors from different embedding spaces must not be compared.
    if len(vec_a) != len(vec_b):
        return 0.0
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
    top_k: int = 4,
    query_text: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Rank chunks using a lightweight hybrid heuristic combining cosine similarity
    with lexical keyword overlap. This is not a BM25 implementation.
    """
    if not chunks:
        return []

    import re
    stopwords = {'what', 'are', 'the', 'for', 'and', 'with', 'from', 'in', 'of', 'to', 'how', 'does', 'can', 'you', 'is', 'a', 'an'}
    q_words = set()
    if query_text:
        tokens = re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', query_text.lower())
        q_words = set(tokens) - stopwords

    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    q_dim = len(query_vec) if query_norm > 0 else 0

    scored_chunks = []
    for chunk in chunks:
        # 1. Vector cosine similarity
        sim = 0.0
        if query_norm > 0 and chunk.get("embedding"):
            raw_emb = chunk["embedding"]
            # Different dimensions usually indicate different embedding spaces.
            # Do not pad/truncate: that creates mathematically valid but meaningless scores.
            if len(raw_emb) == q_dim:
                chunk_vec = np.array(raw_emb, dtype=np.float32)
                chunk_norm = np.linalg.norm(chunk_vec)
                if chunk_norm > 0:
                    sim = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))

        # 2. Lexical keyword overlap score
        lexical_score = 0.0
        if q_words:
            c_text_lower = chunk["content"].lower()
            c_words = set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', c_text_lower))
            overlap = q_words.intersection(c_words)
            if overlap:
                overlap_ratio = len(overlap) / len(q_words)
                term_freq = sum(c_text_lower.count(w) for w in overlap)
                freq_boost = min(term_freq * 0.05, 0.4)
                lexical_score = overlap_ratio * 0.6 + freq_boost

        # 3. Hybrid fusion
        if q_words and lexical_score > 0:
            final_score = (0.65 * lexical_score) + (0.35 * max(sim, 0.0))
        else:
            final_score = sim

        scored_chunks.append({
            "chunk_id": chunk["id"],
            "item_id": chunk["item_id"],
            "source_title": chunk.get("source_title", "Unknown"),
            "source_type": chunk.get("source_type", "note"),
            "source_url": chunk.get("source_url"),
            "content": chunk["content"],
            "similarity_score": round(final_score, 4)
        })

    # Sort descending by similarity score
    scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_chunks[:top_k]

