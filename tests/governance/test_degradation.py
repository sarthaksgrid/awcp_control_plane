"""Tests for the Degradation Policy Engine and trigger evaluation."""

# Week 2 DS-3: Stale-Context Detection
# Tests for TriggerEvaluator and DegradationDecision

from datetime import datetime

from src.governance.degradation.trigger_evaluator import TriggerEvaluator
from src.common.models import (
    AgentIdentity,
    AutonomyMode,
    EvidenceEntry,
    GoverningSliceSchema,
    RiskTier,
    WorkflowState,
    WriteScope,
)
from src.orchestration.context_graph.context_hashing import ContextHasher


def build_slice(**overrides):
    identity = AgentIdentity(
        agent_id="agent_1",
        owner="team_x",
        team="refunds",
        runtime="langchain",
        risk_tier=RiskTier.MEDIUM,
        declared_scopes=[
            WriteScope(system="billing", action_class="refund.adjustment")
        ],
        feature_flags={"safe_profile": True, "trace_sampling": "standard"},
    )
    state = WorkflowState(
        workflow_id="wf_001",
        branch_id="branch_a",
        step_number=1,
        autonomy_mode=AutonomyMode.FULL,
        degradation_level=0,
        start_time=datetime(2026, 5, 12, 10, 30, 0),
        last_checkpoint="checkpoint:t+00:00",
    )
    evidence = EvidenceEntry(
        entry_id="ev_001",
        timestamp=datetime(2026, 5, 12, 10, 31, 0),
        actor_id="agent_1",
        action="billing.adjustment",
        context_hash="ctx_previous",
        outcome="allowed",
        policy_ref="policy.write_scope",
    )
    data = {
        "identity": identity,
        "state": state,
        "current_tool_plan": "issue refund",
        "recent_history": [{"event": "customer eligible", "attempt": 1}],
        "active_evidence": [evidence],
        "token_count": 200,
        "metadata": {"source": "runtime", "priority": "P1"},
    }
    data.update(overrides)
    return GoverningSliceSchema(**data)


def test_trigger_evaluator_degrades_on_stale_context_from_ledger_conflict():
    slice_obj = build_slice(
        metadata={
            "working_memory": {
                "customer": {
                    "refund_eligible": True,
                }
            }
        }
    )
    ledger_entries = [
        {
            "entry_id": "ev_refund_changed",
            "timestamp": datetime(2026, 5, 12, 10, 32, 0),
            "outcome": "allowed",
            "context_hash": ContextHasher.generate_hash(slice_obj),
            "state_changes": {
                "customer": {
                    "refund_eligible": False,
                }
            },
        }
    ]

    decision = TriggerEvaluator().evaluate(
        current_context=slice_obj,
        evidence_entries=ledger_entries,
    )

    assert decision.should_degrade
    assert decision.recommended_level == 2
    assert decision.triggers == ["stale_context"]
    assert decision.evidence["stale_context_report"]["conflicts"][0]["key"] == (
        "customer.refund_eligible"
    )
