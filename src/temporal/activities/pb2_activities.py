"""PB-2 Temporal activities for governed agent execution.

These activities are intentionally thin wrappers around the PB-2 services. The
workflow stays deterministic, while activities perform I/O-like work: DS scoring,
evidence writes, approval request creation, and sandbox artifact folding.
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from src.pb2.ds_stub import score_agent_event
from src.pb2.sandbox_artifacts import fold_artifact
from src.pb2.schemas import AgentEvent, ApprovalRequest, EvidenceEntry, SandboxRunRequest, WorkflowRecord
from src.pb2.state import state


@activity.defn
async def pb2_score_event(event: AgentEvent) -> dict:
    """Call the future DS scorer and return a serializable policy decision."""

    return score_agent_event(event).model_dump()


@activity.defn
async def pb2_write_evidence(entry: dict[str, Any]) -> dict:
    """Append a workflow event to the Evidence Ledger."""

    evidence_entry = EvidenceEntry.model_validate(entry)
    return state.evidence.append(evidence_entry).model_dump(mode="json")


@activity.defn
async def pb2_create_approval(event: AgentEvent, decision: dict) -> dict:
    """Create a pending approval request for a high-risk action."""

    approval = ApprovalRequest(
        workflow_id=event.workflow_id,
        branch_id=event.branch_id,
        action_class=event.action_class,
        requested_scope=event.requested_scope,
        risk_tier=event.risk_tier,
        risk_score=decision["risk_score"],
        reason=decision["reason"],
        rollback_pointer=f"{event.workflow_id}:{event.branch_id}:before-{event.action_class}",
        proposed_tool_plan=[
            "Verify declared write scope",
            "Wait for narrow approval token",
            "Run CodeAct in ephemeral sandbox",
            "Fold sandbox artifacts into Evidence Ledger",
        ],
        context_hash=event.context_hash,
        expires_at=state.approval_expiry(),
    )
    return state.create_approval(approval).model_dump(mode="json")


@activity.defn
async def pb2_save_workflow(record: dict[str, Any]) -> dict:
    """Update the current workflow state shown to the operator UI."""

    workflow_record = WorkflowRecord.model_validate(record)
    return state.save_workflow(workflow_record).model_dump(mode="json")


@activity.defn
async def pb2_run_sandbox(request: dict[str, Any]) -> dict:
    """Fold sandbox output into a compact artifact trace.

    DevOps/PB-1 can replace this local stub with Modal execution later.
    """

    sandbox_request = SandboxRunRequest.model_validate(request)
    artifact = sandbox_request.artifact or {
        "stdout": "temporal sandbox dry-run complete",
        "updated_customer_id": "cus_1042",
        "write_status": "simulated",
    }
    return fold_artifact(artifact)
