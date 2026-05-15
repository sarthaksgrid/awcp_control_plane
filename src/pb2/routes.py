"""FastAPI routes for the PB-2 control-plane slice."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.client import Client

from src.pb2.ds_stub import score_agent_event
from src.pb2.sandbox_artifacts import fold_artifact
from src.pb2.schemas import (
    AgentEvent,
    ApprovalAction,
    ApprovalRequest,
    EvidenceEntry,
    SandboxRunRequest,
    WorkflowRecord,
)
from src.pb2.state import state
from src.pb2.temporal_config import PB2_TASK_QUEUE, TEMPORAL_ADDRESS, temporal_workflow_id
from src.temporal.workflows.governed_agent_workflow import GovernedAgentWorkflow

router = APIRouter(prefix="/api/pb2", tags=["PB-2"])


async def _connect_temporal() -> Client:
    """Connect to the local Temporal frontend."""

    return await Client.connect(TEMPORAL_ADDRESS)


async def _signal_temporal_workflow(workflow_id: str, signal_name: str, *args: str) -> str:
    """Best-effort signal to the Temporal workflow that owns this PB-2 run."""

    try:
        client = await _connect_temporal()
        handle = client.get_workflow_handle(temporal_workflow_id(workflow_id))
        # print("-------------------------------",handle)
        await handle.signal(signal_name, *args)
    except Exception as exc:
        return f"not_sent:{exc}"
    return "sent"


@router.get("/dashboard")
async def dashboard() -> dict:
    """Return the operator dashboard data consumed by the React UI."""

    workflows = state.list_workflows()
    approvals = state.list_approvals()
    evidence = state.evidence.list()

    return {
        "kpis": {
            "active_workflows": len(workflows),
            "pending_approvals": len([item for item in approvals if item.status == "pending"]),
            "evidence_entries": len(evidence),
            "degraded_workflows": len([item for item in workflows if item.autonomy_mode != "full"]),
        },
        "workflows": workflows,
        "approvals": approvals,
        "evidence": evidence[:20],
    }


@router.get("/temporal/health")
async def temporal_health() -> dict:
    """Report whether FastAPI can reach Temporal for PB-2 workflows."""

    try:
        await _connect_temporal()
    except Exception as exc:
        return {
            "status": "unavailable",
            "address": TEMPORAL_ADDRESS,
            "task_queue": PB2_TASK_QUEUE,
            "detail": str(exc),
        }

    return {
        "status": "available",
        "address": TEMPORAL_ADDRESS,
        "task_queue": PB2_TASK_QUEUE,
    }


@router.post("/reset")
async def reset_demo_state() -> dict:
    """Clear local PB-2 demo state so the next run shows a fresh approval."""

    state.reset_demo_state()
    return {"message": "PB-2 demo state reset."}


@router.post("/workflows/simulate")
async def simulate_workflow(event: AgentEvent | None = None) -> dict:
    """Run a local PB-2 proof slice without requiring a live Temporal cluster.

    This simulates the handoff after PB-1 intake: DS scoring, policy gate,
    idempotency key creation, approval request creation, and evidence writing.
    """

    event = event or AgentEvent()
    idempotency_key = state.idempotency.key_for(
        event.workflow_id,
        event.branch_id,
        event.action_class,
        event.payload,
    )
    duplicate = state.idempotency.get(idempotency_key)
    if duplicate:
        return {"duplicate": True, "result": duplicate}

    decision = score_agent_event(event)
    status = "waiting_for_approval" if decision.requires_approval else decision.decision
    autonomy_mode = "recommendation_only" if decision.decision == "escalate" else "full"

    workflow = state.save_workflow(
        WorkflowRecord(
            workflow_id=event.workflow_id,
            branch_id=event.branch_id,
            agent_id=event.agent_id,
            owner=event.owner,
            status=status,
            autonomy_mode=autonomy_mode,
            risk_tier=event.risk_tier,
            policy_decision=decision.decision,
            context_hash=event.context_hash,
            idempotency_key=idempotency_key,
            latest_summary=decision.reason,
        )
    )

    state.evidence.append(
        EvidenceEntry(
            workflow_id=event.workflow_id,
            branch_id=event.branch_id,
            actor=event.agent_id,
            action=event.action_class,
            policy_result=decision.decision,
            context_hash=event.context_hash,
            degradation_state=autonomy_mode,
            replay_trace={"ds_score": decision.model_dump(), "payload": event.payload},
            rollback_pointer=f"{event.workflow_id}:{event.branch_id}:before-{event.action_class}",
        )
    )

    approval = None
    if decision.requires_approval:
        approval = state.create_approval(
            ApprovalRequest(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                action_class=event.action_class,
                requested_scope=event.requested_scope,
                risk_tier=event.risk_tier,
                risk_score=decision.risk_score,
                reason=decision.reason,
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
        )

    result = {"workflow": workflow, "approval": approval, "decision": decision}
    state.idempotency.record(idempotency_key, result)
    return {"duplicate": False, "result": result}


@router.post("/workflows/temporal/start")
async def start_temporal_workflow(event: AgentEvent | None = None) -> dict:
    """Start the real PB-2 Temporal workflow when local Temporal is running."""

    event = event or AgentEvent()
    try:
        client = await _connect_temporal()
        handle = await client.start_workflow(
            GovernedAgentWorkflow.run,
            event,
            id=temporal_workflow_id(event.workflow_id),
            task_queue=PB2_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "A PB-2 Temporal workflow with this workflow_id already exists. "
                "Use Reset Demo or pass a new workflow_id."
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Temporal is not reachable. Start Temporal and pb2_worker first. "
                f"Address: {TEMPORAL_ADDRESS}. Error: {exc}"
            ),
        ) from exc

    return {
        "message": "PB-2 Temporal workflow started.",
        "workflow_id": handle.id,
        "task_queue": PB2_TASK_QUEUE,
    }


@router.get("/approvals")
async def approvals() -> list[ApprovalRequest]:
    """List approval requests for the operator queue."""

    return state.list_approvals()


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, action: ApprovalAction) -> ApprovalRequest:
    """Issue a narrow JWT and resume the waiting workflow surface."""

    approval = state.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval is already {approval.status}.")

    approval.token = state.tokens.issue(
        approval_id=approval.id,
        workflow_id=approval.workflow_id,
        branch_id=approval.branch_id,
        action_class=approval.action_class,
        requested_scope=approval.requested_scope,
        rollback_pointer=approval.rollback_pointer,
        operator=action.operator,
    )
    approval.status = "approved"
    approval.operator = action.operator
    state.save_approval(approval)

    temporal_signal_status = await _signal_temporal_workflow(
        approval.workflow_id,
        "approve",
        approval.token,
    )

    workflow = state.get_workflow(approval.workflow_id)
    if workflow:
        workflow.status = "approved_ready_for_sandbox"
        workflow.autonomy_mode = "token_gated"
        workflow.latest_summary = (
            "Operator token issued. Temporal signal status: "
            f"{temporal_signal_status}."
        )
        state.save_workflow(workflow)

    state.evidence.append(
        EvidenceEntry(
            workflow_id=approval.workflow_id,
            branch_id=approval.branch_id,
            actor=action.operator,
            action="approval.issue_token",
            policy_result="approved",
            context_hash=approval.context_hash,
            degradation_state="token_gated",
            replay_trace={
                "approval_id": approval.id,
                "scope": approval.requested_scope,
                "temporal_signal_status": temporal_signal_status,
            },
            rollback_pointer=approval.rollback_pointer,
            approval_token_id=approval.id,
        )
    )
    return approval


@router.post("/approvals/{approval_id}/deny")
async def deny(approval_id: str, action: ApprovalAction) -> ApprovalRequest:
    """Deny a high-risk approval request and keep the workflow blocked."""

    approval = state.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found.")

    approval.status = "denied"
    approval.operator = action.operator
    state.save_approval(approval)
    temporal_signal_status = await _signal_temporal_workflow(approval.workflow_id, "deny")

    workflow = state.get_workflow(approval.workflow_id)
    if workflow:
        workflow.status = "blocked_by_operator"
        workflow.autonomy_mode = "recommendation_only"
        workflow.latest_summary = (
            "Operator denied the narrow token request. Temporal signal status: "
            f"{temporal_signal_status}."
        )
        state.save_workflow(workflow)

    return approval


@router.post("/sandbox/run")
async def run_sandbox(request: SandboxRunRequest) -> dict:
    """Capture a sandbox result and fold its artifact into evidence.

    The execution itself is a local stub until Modal is available. This keeps
    PB-2's trace/artifact capture contract ready for DevOps/PB-1 integration.
    """

    workflow = state.get_workflow(request.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    if workflow.status not in {"approved_ready_for_sandbox", "sandbox_complete"}:
        raise HTTPException(status_code=409, detail="Workflow must be approved before sandbox execution.")

    artifact = request.artifact or {
        "stdout": "sandbox dry-run complete",
        "updated_customer_id": "cus_1042",
        "write_status": "simulated",
    }
    folded = fold_artifact(artifact)
    state.evidence.append(
        EvidenceEntry(
            workflow_id=request.workflow_id,
            branch_id=request.branch_id,
            actor="codeact-sandbox",
            action="sandbox.artifact_fold",
            policy_result="captured",
            context_hash="ctx-after-sandbox",
            degradation_state="token_gated",
            replay_trace=folded,
            rollback_pointer=f"{request.workflow_id}:{request.branch_id}:sandbox",
        )
    )

    workflow.status = "sandbox_complete"
    workflow.autonomy_mode = "full"
    workflow.latest_summary = "Sandbox artifact captured and folded into evidence."
    state.save_workflow(workflow)

    return {"artifact": artifact, "folded": folded}


@router.get("/evidence")
async def evidence(workflow_id: str | None = None) -> list[EvidenceEntry]:
    """List Evidence Ledger entries for replay and UI inspection."""

    return state.evidence.list(workflow_id=workflow_id)
