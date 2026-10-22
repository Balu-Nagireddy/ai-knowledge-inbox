import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.config import settings
from app.logging_config import logger

def get_db_path() -> Path:
    db_path = Path(settings.DATABASE_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initialize database tables and indexes."""
    db_path = get_db_path()
    logger.info(f"Initializing SQLite database at: {db_path}")

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL CHECK(source_type IN ('note', 'url', 'file')),
                source_url TEXT,
                title TEXT NOT NULL,
                raw_content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # 2. Chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );
        """)

        # Indexes for query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_item_id ON chunks(item_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at DESC);")
        
        # Test if 'file' type is accepted by current table schema, migrate if needed
        try:
            cursor.execute("INSERT INTO items (id, source_type, title, raw_content, created_at) VALUES ('__probe__', 'file', 'probe', 'probe', 'probe');")
            cursor.execute("DELETE FROM items WHERE id = '__probe__';")
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("""
                CREATE TABLE items_new (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL CHECK(source_type IN ('note', 'url', 'file')),
                    source_url TEXT,
                    title TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            cursor.execute("INSERT INTO items_new SELECT * FROM items;")
            cursor.execute("DROP TABLE items;")
            cursor.execute("ALTER TABLE items_new RENAME TO items;")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at DESC);")
            cursor.execute("PRAGMA foreign_keys = ON;")
            conn.commit()
            logger.info("Migrated items table schema to support 'file' type.")
    logger.info("Database schema initialized successfully.")

def save_item_with_chunks(
    item_id: str,
    source_type: str,
    title: str,
    raw_content: str,
    source_url: Optional[str],
    chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Store an item and its associated vector chunks transactionally."""
    created_at = datetime.now(timezone.utc).isoformat()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO items (id, source_type, source_url, title, raw_content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (item_id, source_type, source_url, title, raw_content, created_at))
        
        for idx, chunk in enumerate(chunks):
            embedding_json = json.dumps(chunk["embedding"])
            cursor.execute("""
                INSERT INTO chunks (id, item_id, chunk_index, content, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chunk["id"], item_id, idx, chunk["content"], embedding_json, created_at))
            
        conn.commit()

    logger.info(f"Saved item {item_id} with {len(chunks)} chunks.")
    return {
        "id": item_id,
        "source_type": source_type,
        "source_url": source_url,
        "title": title,
        "raw_content": raw_content,
        "chunk_count": len(chunks),
        "created_at": created_at
    }

def get_items() -> List[Dict[str, Any]]:
    """Retrieve all ingested items along with chunk count."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                i.id,
                i.source_type,
                i.source_url,
                i.title,
                i.raw_content,
                i.created_at,
                COUNT(c.id) as chunk_count
            FROM items i
            LEFT JOIN chunks c ON i.id = c.item_id
            GROUP BY i.id
            ORDER BY i.created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single item by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def get_all_chunks() -> List[Dict[str, Any]]:
    """Retrieve all chunks with deserialized embeddings and source item metadata."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                c.id,
                c.item_id,
                c.chunk_index,
                c.content,
                c.embedding,
                i.source_type,
                i.source_url,
                i.title as source_title
            FROM chunks c
            JOIN items i ON c.item_id = i.id
        """)
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "item_id": r["item_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "embedding": json.loads(r["embedding"]),
                "source_type": r["source_type"],
                "source_url": r["source_url"],
                "source_title": r["source_title"]
            })
        return results

def delete_item(item_id: str) -> bool:
    """Delete an item and its associated chunks by item ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0
