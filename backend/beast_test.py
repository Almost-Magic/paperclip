"""Beast Test Suite for Paperclip — AMTL Fleet Command Centre
Run: pytest backend/beast_test.py -v --cov=backend --cov-report=term-missing
"""

import pytest
import httpx
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.models.database import SessionLocal, init_db, seed_terminals_and_hands


@pytest.fixture
async def async_setup():
    """Setup database and seed data before tests."""
    await init_db()
    await seed_terminals_and_hands()


@pytest.fixture
def client():
    """FastAPI TestClient."""
    return TestClient(app)


class TestHealth:
    """Health endpoint tests."""

    def test_health_endpoint_returns_200(self, client):
        """Health endpoint returns 200 OK."""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "operational"
        assert data["service"] == "paperclip"

    def test_health_subpath_endpoint(self, client):
        """Health endpoint at subpath /paperclip/health."""
        r = client.get("/paperclip/health")
        assert r.status_code == 200
        assert r.json()["status"] == "operational"

    def test_health_includes_database_status(self, client):
        """Health response includes database status."""
        r = client.get("/health")
        data = r.json()
        assert "database" in data
        assert data["database"] == "ok"

    def test_health_includes_terminal_count(self, client):
        """Health response includes terminal count."""
        r = client.get("/health")
        data = r.json()
        assert "terminals_online" in data
        assert isinstance(data["terminals_online"], int)


class TestTerminals:
    """Terminal listing and status tests."""

    def test_list_terminals_returns_7(self, client):
        """GET /api/terminals returns list of 7 terminals."""
        r = client.get("/paperclip/api/terminals")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 7
        assert data[0]["id"] == "T1"
        assert data[0]["name"] == "T1 Guru"

    def test_terminal_has_required_fields(self, client):
        """Terminal object has all required fields."""
        r = client.get("/paperclip/api/terminals")
        data = r.json()
        t = data[0]
        assert "id" in t
        assert "name" in t
        assert "role" in t
        assert "llm" in t
        assert "status" in t
        assert "created_at" in t

    def test_all_terminal_ids_present(self, client):
        """All 7 terminals T1-T7 are in the list."""
        r = client.get("/paperclip/api/terminals")
        data = r.json()
        ids = [t["id"] for t in data]
        assert "T1" in ids
        assert "T7" in ids
        assert len(ids) == 7


class TestHands:
    """Hand listing and status tests."""

    def test_list_hands_returns_11(self, client):
        """GET /api/hands returns list of 11 hands."""
        r = client.get("/paperclip/api/hands")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 11
        assert data[0]["id"] == "H1"
        assert data[0]["name"] == "H1 Fleet Coordinator"

    def test_hand_has_required_fields(self, client):
        """Hand object has all required fields."""
        r = client.get("/paperclip/api/hands")
        data = r.json()
        h = data[0]
        assert "id" in h
        assert "name" in h
        assert "role" in h
        assert "llm" in h
        assert "status" in h
        assert "created_at" in h

    def test_all_hand_ids_present(self, client):
        """All 11 hands H1-H11 are in the list."""
        r = client.get("/paperclip/api/hands")
        data = r.json()
        ids = [h["id"] for h in data]
        assert "H1" in ids
        assert "H11" in ids
        assert len(ids) == 11


class TestTasks:
    """Task creation and listing tests."""

    def test_create_task_returns_201(self, client):
        """POST /api/tasks returns 201 Created."""
        payload = {
            "instruction": "Test the system",
            "assigned_to": "H11",
            "assigned_to_type": "hand",
        }
        r = client.post("/paperclip/api/tasks", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["instruction"] == "Test the system"
        assert data["assigned_to"] == "H11"
        assert data["status"] == "pending"

    def test_create_task_validates_instruction(self, client):
        """POST /api/tasks requires non-empty instruction."""
        payload = {
            "instruction": "",
            "assigned_to": "T1",
        }
        r = client.post("/paperclip/api/tasks", json=payload)
        assert r.status_code == 422

    def test_list_tasks_returns_empty_initially(self, client):
        """GET /api/tasks returns empty list initially."""
        r = client.get("/paperclip/api/tasks")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_create_then_list_shows_task(self, client):
        """Created task appears in list."""
        # Create task
        payload = {
            "instruction": "Fix CK-MANI",
            "assigned_to": "T1",
            "assigned_to_type": "terminal",
        }
        create_r = client.post("/paperclip/api/tasks", json=payload)
        task_id = create_r.json()["id"]

        # List tasks
        list_r = client.get("/paperclip/api/tasks")
        tasks = list_r.json()
        task_ids = [t["id"] for t in tasks]
        assert task_id in task_ids

    def test_get_task_detail(self, client):
        """GET /api/tasks/{id} returns task detail."""
        # Create task
        payload = {
            "instruction": "Fix CK-MANI",
            "assigned_to": "T1",
            "assigned_to_type": "terminal",
        }
        create_r = client.post("/paperclip/api/tasks", json=payload)
        task_id = create_r.json()["id"]

        # Get detail
        detail_r = client.get(f"/paperclip/api/tasks/{task_id}")
        assert detail_r.status_code == 200
        data = detail_r.json()
        assert data["id"] == task_id
        assert data["instruction"] == "Fix CK-MANI"

    def test_get_missing_task_returns_404(self, client):
        """GET /api/tasks/missing returns 404."""
        r = client.get("/paperclip/api/tasks/task_nonexistent")
        assert r.status_code == 404


class TestRouting:
    """Command routing tests."""

    def test_command_fix_routes_to_t1(self, client):
        """Command 'fix X' routes to T1 Guru."""
        payload = {"instruction": "fix CK-MANI"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["routed_to"] == "T1"
        assert data["routed_to_type"] == "terminal"

    def test_command_test_routes_to_h11(self, client):
        """Command 'test X' routes to H11."""
        payload = {"instruction": "test Baldrick"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["routed_to"] == "H11"
        assert data["routed_to_type"] == "hand"

    def test_command_write_prd_routes_to_t4(self, client):
        """Command 'write prd for X' routes to T4 Codex."""
        payload = {"instruction": "write prd for new feature"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["routed_to"] == "T4"

    def test_command_audit_routes_to_h3(self, client):
        """Command 'audit X' routes to H3 Security."""
        payload = {"instruction": "audit security"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["routed_to"] == "H3"

    def test_command_unknown_routes_to_t1(self, client):
        """Unknown command routes to T1 (default)."""
        payload = {"instruction": "do something random"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["routed_to"] == "T1"

    def test_command_creates_task(self, client):
        """Command endpoint creates a task."""
        payload = {"instruction": "fix Baldrick"}
        r = client.post("/paperclip/api/command", json=payload)
        data = r.json()
        task_id = data["task_id"]

        # Verify task exists
        task_r = client.get(f"/paperclip/api/tasks/{task_id}")
        assert task_r.status_code == 200
        assert task_r.json()["instruction"] == "fix Baldrick"


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_command_workflow(self, client):
        """Full workflow: command → routing → task creation → listing."""
        # Send command
        cmd_r = client.post(
            "/paperclip/api/command",
            json={"instruction": "test CK-MANI"},
        )
        assert cmd_r.status_code == 200
        task_id = cmd_r.json()["task_id"]

        # Verify in task list
        list_r = client.get("/paperclip/api/tasks")
        tasks = list_r.json()
        task_ids = [t["id"] for t in tasks]
        assert task_id in task_ids

    def test_multiple_tasks_from_different_commands(self, client):
        """Multiple commands create multiple tasks."""
        commands = [
            {"instruction": "fix Baldrick"},
            {"instruction": "test CK-MANI"},
            {"instruction": "research APIs"},
        ]

        task_ids = []
        for cmd in commands:
            r = client.post("/paperclip/api/command", json=cmd)
            assert r.status_code == 200
            task_ids.append(r.json()["task_id"])

        # Verify all in list
        list_r = client.get("/paperclip/api/tasks")
        tasks = list_r.json()
        existing_ids = [t["id"] for t in tasks]
        for tid in task_ids:
            assert tid in existing_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
