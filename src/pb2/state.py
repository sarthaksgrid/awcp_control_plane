"""PB-2 application state shared by FastAPI and Temporal worker processes."""

from __future__ import annotations

import json
from datetime import timedelta, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from src.pb2.evidence_store import PB2_DATA_DIR, EvidenceStore
from src.pb2.idempotency import IdempotencyStore
from src.pb2.schemas import ApprovalRequest, WorkflowRecord, utc_now
from src.pb2.token_service import ApprovalTokenService


class PB2State:
    """Central PB-2 state boundary.

    Workflows, approvals, and evidence are persisted to local files so the
    FastAPI server and the Temporal worker can see the same demo state. Later,
    this is the seam to replace with Postgres/Object Store.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or PB2_DATA_DIR
        self._workflows_path = self.data_dir / "workflows.json"
        self._approvals_path = self.data_dir / "approvals.json"
        self.evidence = EvidenceStore(self.data_dir / "evidence.jsonl")
        self.idempotency = IdempotencyStore()
        self.tokens = ApprovalTokenService()
        self._lock = Lock()

    def _read_json(self, path: Path) -> dict[str, Any]:
        """Read one local JSON object file."""

        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8") or "{}")

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Atomically write one local JSON object file."""

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def _read_workflows(self) -> dict[str, WorkflowRecord]:
        """Load all workflow records from disk."""

        return {
            workflow_id: WorkflowRecord.model_validate(payload)
            for workflow_id, payload in self._read_json(self._workflows_path).items()
        }

    def _write_workflows(self, workflows: dict[str, WorkflowRecord]) -> None:
        """Persist workflow records to disk."""

        self._write_json(
            self._workflows_path,
            {key: workflow.model_dump(mode="json") for key, workflow in workflows.items()},
        )

    def _read_approvals(self) -> dict[str, ApprovalRequest]:
        """Load all approval records from disk."""

        return {
            approval_id: ApprovalRequest.model_validate(payload)
            for approval_id, payload in self._read_json(self._approvals_path).items()
        }

    def _write_approvals(self, approvals: dict[str, ApprovalRequest]) -> None:
        """Persist approval records to disk."""

        self._write_json(
            self._approvals_path,
            {key: approval.model_dump(mode="json") for key, approval in approvals.items()},
        )

    def save_workflow(self, workflow: WorkflowRecord) -> WorkflowRecord:
        """Upsert the current workflow surface for the UI."""

        workflow.updated_at = utc_now()
        with self._lock:
            workflows = self._read_workflows()
            workflows[workflow.workflow_id] = workflow
            self._write_workflows(workflows)
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        """Return one workflow record by ID."""

        with self._lock:
            return self._read_workflows().get(workflow_id)

    def list_workflows(self) -> list[WorkflowRecord]:
        """Return workflows newest first."""

        with self._lock:
            workflows = self._read_workflows()
        return sorted(workflows.values(), key=lambda item: item.updated_at, reverse=True)

    def create_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        """Persist a pending approval request."""

        return self.save_approval(request)

    def save_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        """Upsert an approval request."""

        with self._lock:
            approvals = self._read_approvals()
            approvals[request.id] = request
            self._write_approvals(approvals)
        return request

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return one approval request by ID."""

        with self._lock:
            return self._read_approvals().get(approval_id)

    def approval_expiry(self, minutes: int = 10) -> datetime:
        """Calculate the default approval request expiry."""

        return utc_now() + timedelta(minutes=minutes)

    def list_approvals(self) -> list[ApprovalRequest]:
        """Return approval requests newest first."""

        with self._lock:
            approvals = self._read_approvals()
        return sorted(approvals.values(), key=lambda item: item.created_at, reverse=True)

    def reset_demo_state(self) -> None:
        """Clear local PB-2 runtime state for a fresh UI/Temporal demo."""

        with self._lock:
            for path in (self._workflows_path, self._approvals_path):
                if path.exists():
                    path.unlink()
        self.evidence.clear()
        self.idempotency.clear()


state = PB2State()
