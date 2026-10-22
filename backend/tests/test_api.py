from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "models" in data

def test_ingest_note_and_query_flow():
    # 1. Ingest a valid note
    note_payload = {
        "source_type": "note",
        "title": "Quantum Computing Basics",
        "content": "Quantum computers use qubits instead of classic bits. Qubits can exist in superposition."
    }
    res_ingest = client.post("/ingest", json=note_payload)
    assert res_ingest.status_code == 201
    ingest_data = res_ingest.json()
    item_id = ingest_data["id"]
    assert ingest_data["title"] == "Quantum Computing Basics"
    assert ingest_data["chunk_count"] >= 1

    # 2. Verify in items list
    res_items = client.get("/items")
    assert res_items.status_code == 200
    items = res_items.json()
    assert any(i["id"] == item_id for i in items)

    # 3. Query the ingested knowledge
    query_payload = {
        "question": "What do quantum computers use instead of classic bits?",
        "top_k": 2
    }
    res_query = client.post("/query", json=query_payload)
    assert res_query.status_code == 200
    query_data = res_query.json()
    assert query_data["question"] == query_payload["question"]
    assert any(s["item_id"] == item_id for s in query_data["sources"])

    # 4. Clean up
    res_del = client.delete(f"/items/{item_id}")
    assert res_del.status_code == 200

def test_ingest_validation_errors():
    # Empty content for note
    bad_note = {"source_type": "note", "content": "   "}
    res = client.post("/ingest", json=bad_note)
    assert res.status_code == 422

    # Malformed URL
    bad_url = {"source_type": "url", "url": "ftp://not-supported"}
    res2 = client.post("/ingest", json=bad_url)
    assert res2.status_code == 422

def test_query_stream_endpoint():
    res = client.post("/query/stream", json={"question": "What is in my inbox?", "top_k": 2})
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

def test_ingest_file_endpoint():
    file_content = b"# DevOps Guide\nContinuous Integration and Continuous Deployment are pillars of modern DevOps."
    files = {"file": ("devops_guide.md", file_content, "text/markdown")}
    res = client.post("/ingest/file", files=files, data={"title": "DevOps Guide MD"})
    assert res.status_code == 201
    data = res.json()
    assert data["source_type"] == "file"
    assert data["title"] == "DevOps Guide MD"
    assert data["chunk_count"] >= 1
    
    # Clean up
    client.delete(f"/items/{data['id']}")

def test_ingest_multiple_files_batch():
    f1 = ("doc1.txt", b"First test document about machine learning pipelines and vector search.", "text/plain")
    f2 = ("doc2.md", b"# Cloud Native\nKubernetes automates deployment, scaling, and operations.", "text/markdown")
    
    files = [("files", f1), ("files", f2)]
    res = client.post("/ingest/files", files=files)
    assert res.status_code == 201
    data = res.json()
    assert data["total_files"] == 2
    assert data["total_chunks"] >= 2
    assert len(data["items"]) == 2

    # Clean up
    for item in data["items"]:
        client.delete(f"/items/{item['id']}")



def test_file_upload_size_limit():
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        "/ingest/file",
        files={"file": ("large.txt", oversized, "text/plain")},
    )
    assert response.status_code == 413
