"""Pytest configuration and shared fixtures for Paperclip tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, create_engine
from backend.main import app
from backend.config import DATABASE_URL


# Shared app instance across all tests in session
_app = None
_client = None


@pytest.fixture(scope="session")
def app_instance():
    """Session-scoped app instance — shared across all tests."""
    global _app
    if _app is None:
        _app = app
    return _app


@pytest.fixture(scope="session")
def client(app_instance):
    """Session-scoped TestClient — initialized once, reused for all tests."""
    global _client
    if _client is None:
        _client = TestClient(app_instance)
    return _client


@pytest.fixture(autouse=True)
def cleanup_tasks_between_tests():
    """Auto-cleanup: delete tasks after each test to prevent state pollution."""
    yield
    # After each test, clean up any test tasks
    try:
        sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql://", "postgresql://")
        with create_engine(sync_url, poolclass=None).begin() as conn:
            conn.execute(text("DELETE FROM tasks WHERE id LIKE 'task_%'"))
    except Exception:
        pass  # Silently ignore cleanup errors
