import pytest
from app.services.ingest import process_note_content, IngestionError, _validate_public_http_url
from app.services.chunker import chunk_content, recursive_split_text
from app.services.embeddings import (
    generate_embeddings,
    compute_cosine_similarity,
    rank_chunks_by_similarity
)

def test_process_note_content():
    # Note with custom title
    title, text = process_note_content("This is my note body.", custom_title="My Custom Title")
    assert title == "My Custom Title"
    assert text == "This is my note body."

    # Note with inferred title from first line
    title2, text2 = process_note_content("# Architecture Overview\nThis is paragraph one.\nThis is paragraph two.")
    assert title2 == "Architecture Overview"
    assert "This is paragraph two." in text2

    # Blank note throws IngestionError
    with pytest.raises(IngestionError):
        process_note_content("   \n\t  ")

def test_recursive_split_text():
    sample_text = (
        "FastAPI is a modern, fast web framework for building APIs with Python. "
        "It is based on standard Python type hints. "
        "It has high performance on par with NodeJS and Go. "
        "Automatic interactive documentation is provided by Swagger UI and ReDoc."
    )
    # Chunk with small max_size to enforce splitting
    chunks = recursive_split_text(sample_text, max_size=100, overlap=20)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 120  # Allows slight boundary wiggle for word break

def test_chunk_content_metadata():
    text = "Hello world! This is a test chunking message for knowledge inbox."
    chunks = chunk_content(text, chunk_size=200, chunk_overlap=30)
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"] == text
    assert chunks[0]["char_count"] == len(text)
    assert "id" in chunks[0]

def test_embeddings_and_cosine_similarity():
    texts = [
        "Python FastAPI web application",
        "Deep learning and artificial intelligence",
        "Cooking traditional Italian pasta"
    ]
    embeddings = generate_embeddings(texts)
    assert len(embeddings) == 3
    assert len(embeddings[0]) > 0
    assert all(len(vector) == len(embeddings[0]) for vector in embeddings)

    # Cosine similarity between identical vectors should be ~1.0
    sim_self = compute_cosine_similarity(embeddings[0], embeddings[0])
    assert pytest.approx(sim_self, abs=1e-4) == 1.0

    # Mismatched dimensions must not be treated as comparable vectors.
    assert compute_cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    # Ranking test
    chunks = [
        {"id": "1", "item_id": "i1", "content": texts[0], "embedding": embeddings[0], "source_title": "FastAPI"},
        {"id": "2", "item_id": "i2", "content": texts[1], "embedding": embeddings[1], "source_title": "AI"},
        {"id": "3", "item_id": "i3", "content": texts[2], "embedding": embeddings[2], "source_title": "Cooking"}
    ]
    ranked = rank_chunks_by_similarity(embeddings[0], chunks, top_k=2)
    assert len(ranked) == 2
    assert ranked[0]["chunk_id"] == "1"
    assert ranked[0]["similarity_score"] == 1.0


def test_url_validation_rejects_private_and_non_http_targets():
    with pytest.raises(IngestionError):
        _validate_public_http_url("http://127.0.0.1/admin")
    with pytest.raises(IngestionError):
        _validate_public_http_url("http://192.168.1.10/")
    with pytest.raises(IngestionError):
        _validate_public_http_url("file:///etc/passwd")
    with pytest.raises(IngestionError):
        _validate_public_http_url("https://user:pass@example.com/")
