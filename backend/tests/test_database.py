import pytest
import uuid
from app.database import init_db, save_item_with_chunks, get_items, get_item_by_id, get_all_chunks, delete_item

def test_database_lifecycle():
    init_db()
    
    item_id = str(uuid.uuid4())
    chunks = [
        {"id": str(uuid.uuid4()), "content": "Chunk 1: First test content", "embedding": [0.1, 0.2, 0.3]},
        {"id": str(uuid.uuid4()), "content": "Chunk 2: Second test content", "embedding": [0.4, 0.5, 0.6]}
    ]
    
    # Save
    saved = save_item_with_chunks(
        item_id=item_id,
        source_type="note",
        title="Test Note",
        raw_content="First test content. Second test content.",
        source_url=None,
        chunks=chunks
    )
    assert saved["id"] == item_id
    assert saved["chunk_count"] == 2
    
    # Retrieve all
    items = get_items()
    assert any(i["id"] == item_id for i in items)
    
    # Retrieve single
    item = get_item_by_id(item_id)
    assert item is not None
    assert item["title"] == "Test Note"
    
    # Retrieve chunks
    all_chunks = get_all_chunks()
    item_chunks = [c for c in all_chunks if c["item_id"] == item_id]
    assert len(item_chunks) == 2
    assert item_chunks[0]["embedding"] == [0.1, 0.2, 0.3]
    
    # Delete
    deleted = delete_item(item_id)
    assert deleted is True
    assert get_item_by_id(item_id) is None
