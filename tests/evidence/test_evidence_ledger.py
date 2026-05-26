"""Tests for the Replayable Evidence Ledger."""

import json

import pytest

from src.evidence.ledger.evidence_ledger import (
    ArtifactPayloadError,
    EvidenceLedger,
    StateChangeOperation,
)


def test_fold_tool_artifact_extracts_state_changes_from_large_payload() -> None:
    ledger = EvidenceLedger()
    large_payload = {
        "tool_call_id": "tool-call-001",
        "tool_name": "billing.refund",
        "read_only_records": [
            {"invoice_id": f"INV-{index}", "status": "read-only"}
            for index in range(500)
        ],
        "result": {
            "system": "billing",
            "resource_id": "INV-42",
            "before": {
                "status": "paid",
                "refund_amount": 0,
                "audit_note": "initial",
            },
            "after": {
                "status": "refunded",
                "refund_amount": 25,
                "audit_note": "duplicate charge approved",
            },
        },
        "updated": [
            {
                "system": "crm",
                "resource_id": "CASE-9",
                "field": "note",
                "old": "pending review",
                "new": "refund approved",
            }
        ],
        "deleted": [
            {
                "system": "feature_flags",
                "resource_id": "temporary-refund-hold",
                "value": True,
            }
        ],
    }

    entry = ledger.fold_tool_artifact(
        workflow_id="refund-workflow-001",
        branch_id="main",
        actor_id="agent-billing-7",
        tool_name="billing.refund",
        payload=large_payload,
        context_hash="context-hash-001",
        policy_result="allow",
        rollback_pointer="checkpoint-before-refund",
    )

    changes = entry.artifact_fold.changes
    operations = {change.operation for change in changes}
    changed_paths = {change.path for change in changes}

    assert entry.outcome == "state_changes_extracted"
    assert entry.artifact_fold.payload_size_bytes > 10_000
    assert len(entry.artifact_fold.payload_hash) == 64
    assert len(entry.artifact_fold.state_change_hash) == 64
    assert StateChangeOperation.UPDATED in operations
    assert StateChangeOperation.DELETED in operations
    assert "$.result.status" in changed_paths
    assert "$.result.refund_amount" in changed_paths
    assert "$.result.audit_note" in changed_paths
    assert "$.updated[0].note" in changed_paths
    assert ledger.get_entries(workflow_id="refund-workflow-001") == [entry]
    assert ledger.get_rollback_point("refund-workflow-001", "main") == "checkpoint-before-refund"


def test_fold_tool_artifact_extracts_json_patch_payloads() -> None:
    ledger = EvidenceLedger()
    payload = json.dumps(
        {
            "tool_call_id": "tool-call-002",
            "patches": [
                {"op": "replace", "path": "/billing/invoice/INV-42/status", "value": "refunded"},
                {"op": "add", "path": "/crm/case/CASE-9/note", "value": "refund approved"},
                {"op": "remove", "path": "/flags/temporary-refund-hold", "from": True},
            ],
        }
    )

    entry = ledger.fold_tool_artifact(
        workflow_id="refund-workflow-002",
        branch_id="main",
        actor_id="agent-billing-7",
        tool_name="json.patch",
        payload=payload,
        context_hash="context-hash-002",
    )

    operations = [change.operation for change in entry.artifact_fold.changes]

    assert operations == [
        StateChangeOperation.UPDATED,
        StateChangeOperation.CREATED,
        StateChangeOperation.DELETED,
    ]
    assert entry.artifact_fold.changes[0].field == "status"
    assert entry.artifact_fold.changes[1].after == "refund approved"


def test_fold_tool_artifact_writes_noop_evidence_for_read_only_payload() -> None:
    ledger = EvidenceLedger()

    entry = ledger.fold_tool_artifact(
        workflow_id="read-only-workflow",
        branch_id="main",
        actor_id="agent-analyst",
        tool_name="invoice.lookup",
        payload={"records": [{"invoice_id": "INV-1", "status": "paid"}]},
        context_hash="context-hash-003",
    )

    assert entry.outcome == "no_state_changes_detected"
    assert entry.artifact_fold.change_count == 0
    assert ledger.get_replay_trace("read-only-workflow")[0]["artifact_fold"]["change_count"] == 0


def test_fold_tool_artifact_rejects_invalid_json_strings() -> None:
    ledger = EvidenceLedger()

    with pytest.raises(ArtifactPayloadError):
        ledger.fold_tool_artifact(
            workflow_id="bad-workflow",
            branch_id="main",
            actor_id="agent-billing-7",
            tool_name="bad.tool",
            payload="{not valid json",
            context_hash="context-hash-004",
        )
