"""Tests for Week 2 RLM summary persistence into the evidence ledger."""

from src.evidence.ledger.evidence_ledger import EvidenceLedger
from src.evidence.replay.rlm_summarizer import summarize_trace_to_ledger


def test_summarize_trace_to_ledger_records_replay_evidence() -> None:
    ledger = EvidenceLedger()
    trace_events = [
        {
            "workflow_id": "refund-workflow-rlm",
            "agent_id": "agent-policy",
            "action": "policy_check",
            "policy_result": "denied until approval token is present",
            "evidence_ref": "ev-policy-001",
        },
        {
            "workflow_id": "refund-workflow-rlm",
            "agent_id": "agent-writer",
            "action": "write refund update",
            "status": "failed",
            "error": "write failed because approval token was missing",
            "trace_id": "trace-write-001",
        },
    ]

    entry = summarize_trace_to_ledger(
        trace_events,
        ledger=ledger,
        workflow_id="refund-workflow-rlm",
        branch_id="main",
        actor_id="agent-control",
        context_hash="ctx-rlm-summary-001",
        degradation_state={"autonomy_mode": "CONSERVATIVE", "level": 2},
        replay_trace_ref="trace://refund-workflow-rlm/main",
        rollback_pointer="checkpoint-before-refund",
        metadata={"task": "DS-1 Week 2"},
        token_budget=360,
        chunk_token_budget=60,
    )

    replay_trace = ledger.get_replay_trace("refund-workflow-rlm")

    assert entry.action == "replay_trace_summary"
    assert entry.outcome == "rlm_summary_written"
    assert entry.context_hash == "ctx-rlm-summary-001"
    assert entry.degradation_state == {"autonomy_mode": "CONSERVATIVE", "level": 2}
    assert entry.replay_trace_ref == "trace://refund-workflow-rlm/main"
    assert entry.rollback_pointer == "checkpoint-before-refund"
    assert entry.metadata["summary_type"] == "rlm_trace_summary"
    assert entry.metadata["summary"]["token_count"] <= 360
    assert "ev-policy-001" in entry.metadata["evidence_refs"]
    assert "trace-write-001" in entry.metadata["evidence_refs"]
    assert replay_trace[0]["metadata"]["summary_type"] == "rlm_trace_summary"
