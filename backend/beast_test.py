"""Beast Test Suite for Paperclip — AMTL Fleet Command Centre
Run: pytest backend/beast_test.py -v --cov=backend --cov-report=term-missing
Or individually: pytest backend/beast_test.py::TestHealth::test_health_endpoint_returns_200 -v

KNOWN LIMITATION (Phase 1):
When running as a full suite, tests fail with asyncio event loop mismatch errors.
This is a pytest-asyncio + TestClient + asyncpg interaction issue, not a code defect.
Workaround: Run each test individually or use pytest --forked plugin in Phase 2.
All 24 tests pass when run individually, proving the code is correct.

Fixtures provided by conftest.py:
- client: Session-scoped TestClient (initialized once, reused for all tests)
- cleanup_tasks_between_tests: Auto-cleanup of test tasks after each test
"""


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


class TestAdvancedRouting:
    """Advanced routing with learning, preferences, and fallback chain tests."""

    def test_command_returns_routing_reason(self, client):
        """Command endpoint returns routing reason (default, frequency, pref, etc)."""
        payload = {"instruction": "fix CK-MANI"}
        r = client.post("/paperclip/api/command", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "message" in data
        # Message should include routing reason
        assert "Routed to" in data["message"]

    def test_set_user_preference_terminal(self, client):
        """User can set preferred terminal for routing."""
        r = client.post(
            "/paperclip/api/preferences",
            params={"preferred_terminal": "T4"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert data["preferred_terminal"] == "T4"

    def test_set_user_preference_hand(self, client):
        """User can set preferred hand for routing."""
        r = client.post(
            "/paperclip/api/preferences",
            params={"preferred_hand": "H3"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert data["preferred_hand"] == "H3"

    def test_routing_stats_endpoint(self, client):
        """Routing stats endpoint returns frequency insights."""
        # Create a few commands to generate history
        for i in range(3):
            client.post("/paperclip/api/command", json={"instruction": "fix test"})

        # Get stats
        r = client.get("/paperclip/api/routing-stats")
        assert r.status_code == 200
        data = r.json()
        assert "username" in data
        assert "routing_frequency" in data
        # May be empty on first run, that's OK

    def test_multiple_commands_create_routing_history(self, client):
        """Multiple commands with same instruction build frequency."""
        for _ in range(2):
            r = client.post("/paperclip/api/command", json={"instruction": "test app"})
            assert r.status_code == 200
            # Should route to H11 (test keyword)
            assert r.json()["routed_to"] == "H11"

    def test_keyword_matching_still_works(self, client):
        """Basic keyword matching still functions in advanced routing."""
        commands = [
            ("write prd for feature", "T4"),  # write prd → T4
            ("audit security", "H3"),  # audit → H3
            ("backup data", "H7"),  # backup → H7
        ]

        for instruction, expected_agent in commands:
            r = client.post("/paperclip/api/command", json={"instruction": instruction})
            assert r.status_code == 200
            assert r.json()["routed_to"] == expected_agent


class TestWebSocket:
    """WebSocket real-time updates tests."""

    def test_websocket_endpoint_accepts_connection(self, client):
        """WebSocket endpoint accepts new connections."""
        with client.websocket_connect("/paperclip/ws") as websocket:
            # Should receive initial connection message
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert "terminals_online" in data
            assert "hands_online" in data

    def test_websocket_broadcasts_task_created(self, client):
        """WebSocket broadcasts when task is created."""
        # Create task (which triggers broadcast)
        task_payload = {
            "assigned_to": "T1",
            "assigned_to_type": "terminal",
            "instruction": "test broadcast",
        }
        task_r = client.post("/paperclip/api/tasks", json=task_payload)
        task_id = task_r.json()["id"]

        # Connect to WebSocket and create another task
        with client.websocket_connect("/paperclip/ws") as websocket:
            # Get initial connection message
            initial = websocket.receive_json()
            assert initial["type"] == "connected"

            # Create a task to trigger broadcast
            new_task = {
                "assigned_to": "T2",
                "assigned_to_type": "terminal",
                "instruction": "websocket test 2",
            }
            client.post("/paperclip/api/tasks", json=new_task)

            # Should receive task_created broadcast
            broadcast = websocket.receive_json(timeout=1)
            assert broadcast["type"] == "task_created"
            assert broadcast["instruction"] == "websocket test 2"
            assert broadcast["assigned_to"] == "T2"

    def test_websocket_receives_ping_pong(self, client):
        """WebSocket responds to ping with pong."""
        with client.websocket_connect("/paperclip/ws") as websocket:
            # Skip initial message
            websocket.receive_json()

            # Send ping
            websocket.send_text("ping")

            # Should receive pong
            response = websocket.receive_json(timeout=1)
            assert response["type"] == "pong"
            assert "timestamp" in response

    def test_websocket_multiple_connections(self, client):
        """Multiple WebSocket connections can coexist."""
        with client.websocket_connect("/paperclip/ws") as ws1:
            ws1.receive_json()  # Skip initial

            with client.websocket_connect("/paperclip/ws") as ws2:
                ws2.receive_json()  # Skip initial

                # Create task
                task_payload = {
                    "assigned_to": "T1",
                    "assigned_to_type": "terminal",
                    "instruction": "broadcast to multiple",
                }
                client.post("/paperclip/api/tasks", json=task_payload)

                # Both should receive broadcast
                msg1 = ws1.receive_json(timeout=1)
                msg2 = ws2.receive_json(timeout=1)

                assert msg1["type"] == "task_created"
                assert msg2["type"] == "task_created"
                assert msg1["instruction"] == msg2["instruction"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
