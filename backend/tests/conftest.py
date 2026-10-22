import os
import pytest
from pathlib import Path
from app.config import settings

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    # Use a separate test database
    test_db = Path(__file__).resolve().parent / "test_inbox.db"
    settings.DATABASE_PATH = str(test_db)
    
    # Initialize fresh database
    from app.database import init_db
    init_db()

    yield

    # Clean up test database file
    if test_db.exists():
        try:
            test_db.unlink()
        except Exception:
            pass
