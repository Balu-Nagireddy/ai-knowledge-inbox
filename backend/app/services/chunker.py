import uuid
from typing import List, Dict, Any
from app.config import settings
from app.logging_config import logger

def recursive_split_text(
    text: str,
    max_size: int = 500,
    overlap: int = 100,
    separators: List[str] = None
) -> List[str]:
    """
    Split text into chunks of maximum length `max_size` with `overlap`,
    prioritizing natural semantic boundaries (paragraphs, lines, sentences, spaces).
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

    text = text.strip()
    if not text:
        return []

    if len(text) <= max_size:
        return [text]

    # Find the best separator that actually exists in text
    chosen_separator = ""
    for sep in separators:
        if sep == "" or sep in text:
            chosen_separator = sep
            break

    # Split using chosen separator
    if chosen_separator:
        parts = text.split(chosen_separator)
    else:
        parts = list(text)

    chunks: List[str] = []
    current_chunk = ""

    for part in parts:
        candidate = f"{current_chunk}{chosen_separator}{part}" if current_chunk else part
        
        if len(candidate) <= max_size:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                # Apply overlap from the tail of current_chunk
                if overlap > 0 and len(current_chunk) > overlap:
                    overlap_seed = current_chunk[-overlap:]
                    # Try to break overlap cleanly at whitespace
                    space_idx = overlap_seed.find(" ")
                    if space_idx != -1 and space_idx < len(overlap_seed) - 1:
                        overlap_seed = overlap_seed[space_idx + 1:]
                    current_chunk = f"{overlap_seed} {part}".strip()
                else:
                    current_chunk = part
            else:
                # If a single part is larger than max_size, recurse with finer separators
                remaining_separators = separators[separators.index(chosen_separator) + 1:] if chosen_separator in separators else [""]
                sub_chunks = recursive_split_text(part, max_size, overlap, remaining_separators)
                chunks.extend(sub_chunks[:-1])
                current_chunk = sub_chunks[-1] if sub_chunks else ""

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c]

def chunk_content(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None
) -> List[Dict[str, Any]]:
    """
    Generate chunks with unique IDs and metadata for vector storage.
    """
    size = chunk_size or settings.CHUNK_SIZE
    overlap = chunk_overlap or settings.CHUNK_OVERLAP

    text_chunks = recursive_split_text(text, max_size=size, overlap=overlap)
    
    result = []
    for idx, chunk in enumerate(text_chunks):
        result.append({
            "id": str(uuid.uuid4()),
            "chunk_index": idx,
            "content": chunk,
            "char_count": len(chunk)
        })

    logger.info(f"Chunked text into {len(result)} chunks (size={size}, overlap={overlap})")
    return result
