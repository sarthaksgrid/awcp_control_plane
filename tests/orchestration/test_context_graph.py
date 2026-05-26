"""Tests for the Context Graph Manager and DS-3 context hashing."""

## DS-3 Context Hashing Tests 

# Week 1 DS-3 : Cryptographic Context Hashing tests
# Tests for ContextHasher and  hash_runner processes 

import re
from datetime import datetime

from src.common.models import (
    AgentIdentity,
    AutonomyMode,
    EvidenceEntry,
    GoverningSliceSchema,
    RiskTier,
    WorkflowState,
    WriteScope,
)
from src.orchestration.context_graph.context_hashing import (
    ContextHasher,
    StaleContextDetector,
)


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
        "current_tool_plan": "issue   refund",
        "recent_history": [{"event": "customer    eligible", "attempt": 1}],
        "active_evidence": [evidence],
        "token_count": 200,
        "metadata": {"source": "runtime", "priority": "P1"},
    }
    data.update(overrides)
    return GoverningSliceSchema(**data)


def test_context_hash_is_sha256_hex_digest():
    context_hash = ContextHasher.generate_hash(build_slice())

    assert re.fullmatch(r"[0-9a-f]{64}", context_hash)


def test_same_context_generates_same_hash():
    slice_obj = build_slice()

    assert ContextHasher.generate_hash(slice_obj) == ContextHasher.generate_hash(slice_obj)


def test_changed_governance_state_changes_hash():
    original_hash = ContextHasher.generate_hash(build_slice())
    changed_hash = ContextHasher.generate_hash(
        build_slice(
            state=WorkflowState(
                workflow_id="wf_001",
                branch_id="branch_a",
                step_number=2,
                autonomy_mode=AutonomyMode.FULL,
                degradation_level=0,
                start_time=datetime(2026, 5, 12, 10, 30, 0),
                last_checkpoint="checkpoint:t+00:00",
            )
        )
    )

    assert changed_hash != original_hash


def test_reordered_mapping_keys_generate_same_hash():
    first = {
        "identity": {"agent_id": "agent_1", "owner": "team_x"},
        "state": {"workflow_id": "wf_001", "step_number": 1},
    }
    second = {
        "state": {"step_number": 1, "workflow_id": "wf_001"},
        "identity": {"owner": "team_x", "agent_id": "agent_1"},
    }

    assert ContextHasher.generate_hash(first) == ContextHasher.generate_hash(second)


def test_whitespace_noise_is_normalized_before_hashing():
    noisy = {
        "identity": {"agent_id": "agent_1", "owner": "team_x"},
        "state": {"workflow_id": "wf_001", "step_number": 1},
        "recent_history": [{"message": "refund     eligibility\nconfirmed"}],
    }
    normalized = {
        "identity": {"agent_id": "agent_1", "owner": "team_x"},
        "state": {"workflow_id": "wf_001", "step_number": 1},
        "recent_history": [{"message": "refund eligibility confirmed"}],
    }

    assert ContextHasher.generate_hash(noisy) == ContextHasher.generate_hash(normalized)


def test_token_count_is_excluded_as_derived_metadata():
    first = build_slice(token_count=200)
    second = build_slice(token_count=500)

    assert ContextHasher.generate_hash(first) == ContextHasher.generate_hash(second)


def test_stale_context_detection_compares_current_snapshot_to_stored_hash():
    slice_obj = build_slice()
    stored_hash = ContextHasher.generate_hash(slice_obj)
    changed_slice = build_slice(current_tool_plan="queue manual review")

    assert ContextHasher.compare_hashes(stored_hash, stored_hash)
    assert ContextHasher.is_stale(changed_slice, stored_hash)


def test_hash_runner_returns_hash_and_canonical_context_snapshot():
    from src.orchestration.context_graph.hash_runner import run_hash_snapshot

    slice_obj = build_slice()
    snapshot = run_hash_snapshot(
        slice_obj.identity,
        slice_obj.state,
        {
            "tool_plan": slice_obj.current_tool_plan,
            "history": slice_obj.recent_history,
            "metadata": slice_obj.metadata,
        },
        slice_obj.active_evidence,
    )

    assert re.fullmatch(r"[0-9a-f]{64}", snapshot["context_hash"])
    assert snapshot["canonical_context"]["identity"]["agent_id"] == "agent_1"
    assert "token_count" not in snapshot["canonical_context"]


# Week 2 DS-3 : Stale Context Detection tests
# Tests for StaleContextDetection process

def test_stale_context_detector_flags_memory_conflict_with_latest_ledger_state():
    slice_obj = build_slice(
        metadata={
            "working_memory": {
                "customer": {
                    "refund_eligible": True,
                }
            }
        }
    )
    current_hash = ContextHasher.generate_hash(slice_obj)
    ledger_entries = [
        {
            "entry_id": "ev_001",
            "timestamp": datetime(2026, 5, 12, 10, 31, 0),
            "outcome": "allowed",
            "context_hash": current_hash,
            "state_changes": {
                "customer": {
                    "refund_eligible": True,
                }
            },
        },
        {
            "entry_id": "ev_002",
            "timestamp": datetime(2026, 5, 12, 10, 32, 0),
            "outcome": "allowed",
            "context_hash": current_hash,
            "state_changes": {
                "customer": {
                    "refund_eligible": False,
                }
            },
        },
    ]

    report = StaleContextDetector().evaluate(slice_obj, ledger_entries)

    assert report.is_stale
    assert report.reasons == ["working_memory_conflicts_with_ledger"]
    assert report.conflicts[0].key == "customer.refund_eligible"
    assert report.conflicts[0].working_memory_value is True
    assert report.conflicts[0].ledger_value is False
    assert report.conflicts[0].ledger_entry_id == "ev_002"


def test_stale_context_detector_uses_chronologically_verified_ledger_entries():
    slice_obj = build_slice(
        metadata={
            "working_memory": {
                "customer": {
                    "refund_eligible": True,
                }
            }
        }
    )
    current_hash = ContextHasher.generate_hash(slice_obj)
    ledger_entries = [
        {
            "entry_id": "ev_verified",
            "timestamp": datetime(2026, 5, 12, 10, 31, 0),
            "outcome": "allowed",
            "context_hash": current_hash,
            "state_changes": {
                "customer": {
                    "refund_eligible": True,
                }
            },
        },
        {
            "entry_id": "ev_failed",
            "timestamp": datetime(2026, 5, 12, 10, 32, 0),
            "outcome": "failed",
            "context_hash": "failed-write-hash",
            "state_changes": {
                "customer": {
                    "refund_eligible": False,
                }
            },
        },
    ]

    report = StaleContextDetector().evaluate(slice_obj, ledger_entries)

    assert not report.is_stale
    assert report.latest_entry_id == "ev_verified"
    assert report.conflicts == []


def test_stale_context_detector_reads_artifact_fold_changes_from_ledger_entries():
    slice_obj = build_slice(
        metadata={
            "working_memory": {
                "customer": {
                    "refund_eligible": True,
                }
            }
        }
    )
    current_hash = ContextHasher.generate_hash(slice_obj)
    ledger_entries = [
        {
            "entry_id": "ev_artifact_fold",
            "timestamp": datetime(2026, 5, 12, 10, 32, 0),
            "outcome": "state_changes_extracted",
            "context_hash": current_hash,
            "artifact_fold": {
                "changes": [
                    {
                        "path": "customer.refund_eligible",
                        "after": False,
                    }
                ]
            },
        }
    ]

    report = StaleContextDetector().evaluate(slice_obj, ledger_entries)

    assert report.is_stale
    assert report.conflicts[0].key == "customer.refund_eligible"
    assert report.conflicts[0].ledger_value is False
    assert report.latest_entry_id == "ev_artifact_fold"
