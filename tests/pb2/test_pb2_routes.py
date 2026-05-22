"""Tests for the PB-2 Week 1 Temporal foundation API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api import app
from src.pb2.state import PB2State
import src.pb2.routes as pb2_routes


def make_client(tmp_path, monkeypatch):
    """Create a TestClient with isolated PB-2 file state."""

    test_state = PB2State(tmp_path)
    monkeypatch.setattr(pb2_routes, "state", test_state)
    return TestClient(app), test_state


def test_simulate_creates_pending_approval_and_evidence(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    response = client.post("/api/pb2/workflows/simulate", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["result"]["workflow"]["status"] == "waiting_for_approval"
    assert body["result"]["approval"]["status"] == "pending"

    dashboard = client.get("/api/pb2/dashboard").json()
    assert dashboard["kpis"]["active_workflows"] == 1
    assert dashboard["kpis"]["pending_approvals"] == 1
    assert dashboard["kpis"]["evidence_entries"] == 1


def test_approve_issues_token_and_records_temporal_signal(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    async def fake_signal(workflow_id: str, signal_name: str, *args: str) -> str:
        assert workflow_id
        assert signal_name == "approve"
        assert args[0]
        return "sent"

    monkeypatch.setattr(pb2_routes, "_signal_temporal_workflow", fake_signal)

    approval = client.post("/api/pb2/workflows/simulate", json={}).json()["result"]["approval"]
    response = client.post(
        f"/api/pb2/approvals/{approval['id']}/approve",
        json={"operator": "operator.test"},
    )

    assert response.status_code == 200
    approved = response.json()
    assert approved["status"] == "approved"
    assert approved["token"]

    dashboard = client.get("/api/pb2/dashboard").json()
    assert dashboard["kpis"]["pending_approvals"] == 0
    assert dashboard["workflows"][0]["status"] == "approved_ready_for_sandbox"
    assert dashboard["evidence"][0]["replay_trace"]["temporal_signal_status"] == "sent"


def test_sandbox_requires_approval(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    async def fake_signal(workflow_id: str, signal_name: str, *args: str) -> str:
        return "sent"

    monkeypatch.setattr(pb2_routes, "_signal_temporal_workflow", fake_signal)

    result = client.post("/api/pb2/workflows/simulate", json={}).json()["result"]
    workflow_id = result["workflow"]["workflow_id"]
    approval_id = result["approval"]["id"]

    blocked = client.post("/api/pb2/sandbox/run", json={"workflow_id": workflow_id})
    assert blocked.status_code == 409

    client.post(f"/api/pb2/approvals/{approval_id}/approve", json={"operator": "operator.test"})
    allowed = client.post("/api/pb2/sandbox/run", json={"workflow_id": workflow_id})

    assert allowed.status_code == 200
    assert allowed.json()["folded"]["state_changes"]["write_status"] == "simulated"


def test_reset_clears_demo_state(tmp_path, monkeypatch):
    client, state = make_client(tmp_path, monkeypatch)
    client.post("/api/pb2/workflows/simulate", json={})

    response = client.post("/api/pb2/reset", json={})

    assert response.status_code == 200
    assert state.list_workflows() == []
    assert state.list_approvals() == []
    assert state.evidence.list() == []


def test_temporal_health_available_when_connect_succeeds(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    async def fake_connect():
        return object()

    monkeypatch.setattr(pb2_routes, "_connect_temporal", fake_connect)

    response = client.get("/api/pb2/temporal/health")

    assert response.status_code == 200
    assert response.json()["status"] == "available"


def test_temporal_start_is_visible_before_worker_activity(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    class FakeHandle:
        id = "pb2-wf-temporal-visible"

    class FakeTemporalClient:
        async def start_workflow(self, workflow_run, event, *, id: str, task_queue: str):
            assert id == "pb2-wf-temporal-visible"
            assert task_queue
            return FakeHandle()

    async def fake_connect():
        return FakeTemporalClient()

    monkeypatch.setattr(pb2_routes, "_connect_temporal", fake_connect)

    response = client.post(
        "/api/pb2/workflows/temporal/start",
        json={"workflow_id": "wf-temporal-visible"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow"]["status"] == "temporal_queued"

    dashboard = client.get("/api/pb2/dashboard").json()
    assert dashboard["kpis"]["active_workflows"] == 1
    assert dashboard["kpis"]["evidence_entries"] == 1
    assert dashboard["workflows"][0]["workflow_id"] == "wf-temporal-visible"
    assert dashboard["workflows"][0]["status"] == "temporal_queued"
    assert dashboard["evidence"][0]["action"] == "temporal.workflow_start"
