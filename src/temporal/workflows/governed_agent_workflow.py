"""Temporal workflow for the PB-2 governed action proof slice."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.pb2.schemas import AgentEvent, EvidenceEntry, SandboxRunRequest, WorkflowRecord
    from src.temporal.activities.pb2_activities import (
        pb2_create_approval,
        pb2_run_sandbox,
        pb2_save_workflow,
        pb2_score_event,
        pb2_write_evidence,
    )


@workflow.defn
class GovernedAgentWorkflow:
    """PB-2 Temporal workflow with a durable approval wait.

    Flow:
    1. Score the canonical PB-1 event with the DS stub.
    2. Write policy evidence.
    3. If escalated, create an approval request and wait for a token signal.
    4. Run/fold sandbox artifact output.
    5. Write final evidence and return a replay-friendly summary.
    """

    def __init__(self) -> None:
        self._approval_token: str | None = None
        self._denied = False

    @workflow.signal
    async def approve(self, token: str) -> None:
        """Resume the durable wait after the UI/operator issues a token."""

        self._approval_token = token

    @workflow.signal
    async def deny(self) -> None:
        """Stop the workflow when the operator denies the high-risk action."""

        self._denied = True

    @workflow.run
    async def run(self, event: AgentEvent) -> dict:
        decision = await workflow.execute_activity(
            pb2_score_event,
            event,
            start_to_close_timeout=timedelta(seconds=10),
        )

        status = "waiting_for_approval" if decision["requires_approval"] else decision["decision"]
        autonomy_mode = "recommendation_only" if decision["decision"] == "escalate" else "full"

        await workflow.execute_activity(
            pb2_save_workflow,
            WorkflowRecord(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                agent_id=event.agent_id,
                owner=event.owner,
                status=status,
                autonomy_mode=autonomy_mode,
                risk_tier=event.risk_tier,
                policy_decision=decision["decision"],
                context_hash=event.context_hash,
                idempotency_key=f"temporal:{workflow.info().workflow_id}",
                latest_summary=decision["reason"],
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        await workflow.execute_activity(
            pb2_write_evidence,
            EvidenceEntry(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                actor=event.agent_id,
                action=event.action_class,
                policy_result=decision["decision"],
                context_hash=event.context_hash,
                degradation_state=autonomy_mode,
                replay_trace={"ds_score": decision, "source": "temporal"},
                rollback_pointer=f"{event.workflow_id}:{event.branch_id}:before-{event.action_class}",
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        approval = None
        if decision["requires_approval"]:
            approval = await workflow.execute_activity(
                pb2_create_approval,
                args=[event, decision],
                start_to_close_timeout=timedelta(seconds=10),
            )

            await workflow.wait_condition(
                lambda: self._approval_token is not None or self._denied,
                timeout=timedelta(minutes=10),
            )

            if self._denied:
                await workflow.execute_activity(
                    pb2_save_workflow,
                    WorkflowRecord(
                        workflow_id=event.workflow_id,
                        branch_id=event.branch_id,
                        agent_id=event.agent_id,
                        owner=event.owner,
                        status="blocked_by_operator",
                        autonomy_mode="recommendation_only",
                        risk_tier=event.risk_tier,
                        policy_decision=decision["decision"],
                        context_hash=event.context_hash,
                        idempotency_key=f"temporal:{workflow.info().workflow_id}",
                        latest_summary="Operator denied the narrow approval token.",
                    ),
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return {"status": "denied", "approval": approval, "decision": decision}

            if self._approval_token is None:
                await workflow.execute_activity(
                    pb2_save_workflow,
                    WorkflowRecord(
                        workflow_id=event.workflow_id,
                        branch_id=event.branch_id,
                        agent_id=event.agent_id,
                        owner=event.owner,
                        status="approval_timeout",
                        autonomy_mode="recommendation_only",
                        risk_tier=event.risk_tier,
                        policy_decision=decision["decision"],
                        context_hash=event.context_hash,
                        idempotency_key=f"temporal:{workflow.info().workflow_id}",
                        latest_summary="Approval window expired before the operator issued a token.",
                    ),
                    start_to_close_timeout=timedelta(seconds=10),
                )
                return {"status": "approval_timeout", "approval": approval, "decision": decision}

        await workflow.execute_activity(
            pb2_save_workflow,
            WorkflowRecord(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                agent_id=event.agent_id,
                owner=event.owner,
                status="sandbox_running",
                autonomy_mode="token_gated",
                risk_tier=event.risk_tier,
                policy_decision=decision["decision"],
                context_hash=event.context_hash,
                idempotency_key=f"temporal:{workflow.info().workflow_id}",
                latest_summary="Approval token received. Running sandbox artifact fold.",
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        folded = await workflow.execute_activity(
            pb2_run_sandbox,
            SandboxRunRequest(workflow_id=event.workflow_id, branch_id=event.branch_id),
            start_to_close_timeout=timedelta(seconds=30),
        )

        await workflow.execute_activity(
            pb2_write_evidence,
            EvidenceEntry(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                actor="codeact-sandbox",
                action="sandbox.artifact_fold",
                policy_result="captured",
                context_hash=event.context_hash,
                degradation_state="full",
                replay_trace=folded,
                rollback_pointer=f"{event.workflow_id}:{event.branch_id}:sandbox",
                approval_token_id=approval["id"] if approval else None,
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        await workflow.execute_activity(
            pb2_save_workflow,
            WorkflowRecord(
                workflow_id=event.workflow_id,
                branch_id=event.branch_id,
                agent_id=event.agent_id,
                owner=event.owner,
                status="temporal_completed",
                autonomy_mode="full",
                risk_tier=event.risk_tier,
                policy_decision=decision["decision"],
                context_hash=event.context_hash,
                idempotency_key=f"temporal:{workflow.info().workflow_id}",
                latest_summary="Temporal workflow completed and evidence was captured.",
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )

        return {
            "status": "completed",
            "decision": decision,
            "approval": approval,
            "artifact_fold": folded,
        }
