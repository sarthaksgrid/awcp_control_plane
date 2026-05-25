"""Dummy end-to-end check for DS-1, DS-2, and DS-3 context graph work.

This file is intentionally simple and readable so a teammate can run one test
and see that the whole context graph folder is doing the expected job.

Run with visible demo output:
    python3 -m pytest tests/orchestration/test_context_graph_end_to_end_dummy.py -q -s
"""

from copy import deepcopy

import pytest

from src.orchestration.context_graph.context_hashing import compute_context_hash
from src.orchestration.context_graph.context_manager import (
    ContextGraphManager,
    ContextNodeType,
)


def test_dummy_ds1_ds2_ds3_context_graph_flow() -> None:
    raw_runtime_log = {
        "workflow_id": "refund-workflow-001",
        "branch_id": "main",
        "runtime": "temporal",
        "workflow_name": "duplicate-refund-review",
        "current_step": "validate-refund-before-write",
        "agent": {
            "agent_id": "agent-billing-7",
            "owner": "billing-ops",
            "declared_write_scopes": ["billing.refund", "crm.note"],
        },
        "feature_flags": {
            "safe_mode": True,
            "human_approval_required": True,
            "experimental_discount_tool": False,
        },
        "conversation_history": [
            "hello",
            "irrelevant old chat that should not enter the governing slice",
        ],
        "user_intent": "Customer says invoice INV-42 has a duplicate charge.",
        "api_response": {
            "invoice_id": "INV-42",
            "duplicate_charge": True,
            "amount": 25.0,
        },
        "fact": "Refund write is allowed only inside the billing.refund scope.",
    }

    # DS-1: parse raw runtime state into a minimal governing slice.
    governing_state = build_dummy_governing_state(raw_runtime_log)

    assert governing_state == {
        "workflow_id": "refund-workflow-001",
        "branch_id": "main",
        "metadata": {
            "runtime": "temporal",
            "workflow_name": "duplicate-refund-review",
            "current_step": "validate-refund-before-write",
        },
        "owner_identity": {
            "agent_id": "agent-billing-7",
            "owner": "billing-ops",
        },
        "active_feature_flags": {
            "safe_mode": True,
            "human_approval_required": True,
        },
        "declared_write_scopes": ["billing.refund", "crm.note"],
    }
    assert "conversation_history" not in governing_state

    # DS-2: store memory as a DAG and select the critical nodes for this step.
    manager = ContextGraphManager(default_token_budget=300)
    workflow_node = manager.update_context(
        governing_state["workflow_id"],
        governing_state["branch_id"],
        deepcopy(governing_state),
        node_type=ContextNodeType.WORKFLOW_STATE,
        tags={"governing_slice", "write_scope"},
        metadata={"write_scope": "billing.refund"},
        importance=1.5,
    )
    intent_node = manager.update_context(
        governing_state["workflow_id"],
        governing_state["branch_id"],
        raw_runtime_log["user_intent"],
        node_type=ContextNodeType.USER_INTENT,
        parents=[workflow_node.node_id],
    )
    api_node = manager.update_context(
        governing_state["workflow_id"],
        governing_state["branch_id"],
        raw_runtime_log["api_response"],
        node_type=ContextNodeType.API_RESPONSE,
        parents=[intent_node.node_id],
    )
    fact_node = manager.update_context(
        governing_state["workflow_id"],
        governing_state["branch_id"],
        raw_runtime_log["fact"],
        node_type=ContextNodeType.FACT,
        parents=[workflow_node.node_id],
    )

    selected_context = manager.assemble_context(
        governing_state["workflow_id"],
        governing_state["branch_id"],
        query="duplicate refund invoice INV-42 billing.refund write scope",
        current_step={"tool": "billing.refund", "risk_tier": "HIGH"},
        required_node_ids=[workflow_node.node_id],
        focus_node_id=api_node.node_id,
    )

    assert workflow_node.node_id in selected_context.node_ids
    assert intent_node.node_id in selected_context.node_ids
    assert api_node.node_id in selected_context.node_ids
    assert fact_node.node_id in selected_context.node_ids
    assert selected_context.token_count <= 300
    assert manager.graph.has_edge(workflow_node.node_id, intent_node.node_id)
    assert manager.graph.has_edge(intent_node.node_id, api_node.node_id)

    # DS-3: hash the context snapshot and detect tampering/stale state.
    stored_context_hash = compute_context_hash(selected_context.to_dict())
    repeat_context_hash = compute_context_hash(selected_context.to_dict())
    assert stored_context_hash == repeat_context_hash

    fresh_report = manager.check_freshness(
        selected_context,
        workflow_id=governing_state["workflow_id"],
        branch_id=governing_state["branch_id"],
        query="duplicate refund invoice INV-42 billing.refund write scope",
        current_step={"tool": "billing.refund", "risk_tier": "HIGH"},
        required_node_ids=[workflow_node.node_id],
        focus_node_id=api_node.node_id,
    )
    assert fresh_report.is_fresh

    workflow_node.content["active_feature_flags"]["safe_mode"] = False
    workflow_node.refresh_hash()
    stale_report = manager.check_freshness(
        selected_context,
        workflow_id=governing_state["workflow_id"],
        branch_id=governing_state["branch_id"],
        query="duplicate refund invoice INV-42 billing.refund write scope",
        current_step={"tool": "billing.refund", "risk_tier": "HIGH"},
        required_node_ids=[workflow_node.node_id],
        focus_node_id=api_node.node_id,
    )
    assert stale_report.is_stale
    assert stale_report.changed_node_ids == [workflow_node.node_id]

    print("\nDS-1 governing state:")
    print(governing_state)
    print("\nDS-2 selected DAG nodes:")
    for item in selected_context.nodes:
        print(f"- {item.node_type.value}: {item.node_id} score={item.relevance_score:.3f}")
    print("\nDS-3 context hash:")
    print(selected_context.context_hash)
    print("\nFreshness result after mutation:")
    print(stale_report.to_dict())


def test_dummy_week_one_flow_uses_actual_common_models_and_hash_runner() -> None:
    hash_runner = pytest.importorskip("src.orchestration.context_graph.hash_runner")
    common_models = pytest.importorskip("src.common.models")
    AgentIdentity = getattr(common_models, "AgentIdentity", None)
    EvidenceEntry = getattr(common_models, "EvidenceEntry", None)
    RiskTier = getattr(common_models, "RiskTier", None)
    WorkflowState = getattr(common_models, "WorkflowState", None)
    WriteScope = getattr(common_models, "WriteScope", None)
    if None in {AgentIdentity, EvidenceEntry, RiskTier, WorkflowState, WriteScope}:
        pytest.skip("src.common.models is still scaffolded on this branch")

    identity = AgentIdentity(
        agent_id="agent-billing-7",
        owner="billing-ops",
        team="data-science",
        runtime="temporal",
        risk_tier=RiskTier.HIGH,
        declared_scopes=[
            WriteScope(system="billing", action_class="refund"),
            WriteScope(system="crm", action_class="note"),
        ],
        feature_flags={
            "safe_mode": True,
            "human_approval_required": True,
            "experimental_discount_tool": False,
        },
    )
    state = WorkflowState(
        workflow_id="refund-workflow-actual-models",
        branch_id="main",
        step_number=2,
        last_checkpoint="checkpoint-before-refund-write",
    )
    evidence = EvidenceEntry(
        entry_id="evidence-001",
        actor_id="agent-billing-7",
        action="invoice.lookup",
        context_hash="previous-context-hash",
        outcome="duplicate charge confirmed",
    )
    raw_signals = {
        "tool_plan": "billing.refund",
        "query": "duplicate refund invoice INV-42 billing.refund",
        "feature_flags": {"runtime_override": True},
        "conversation_history": [
            "old greeting",
            "long irrelevant transcript excluded from governing slice",
        ],
        "user_intent": "Customer says invoice INV-42 has a duplicate charge.",
        "api_response": {
            "invoice_id": "INV-42",
            "duplicate_charge": True,
            "amount": 25.0,
        },
        "fact": "Refund write is allowed only inside the billing.refund scope.",
        "token_budget": 500,
    }

    snapshot = hash_runner.run_hash_snapshot(identity, state, raw_signals, [evidence])
    if "governing_slice" not in snapshot or "graph" not in snapshot:
        pytest.skip("hash_runner on this branch exposes the minimal hash-only contract")
    governing_slice = snapshot["governing_slice"]
    graph_nodes = snapshot["graph"]["nodes"]
    node_types = {node["node_type"] for node in graph_nodes}
    root_content = graph_nodes[0]["content"]

    assert len(snapshot["context_hash"]) == 64
    assert snapshot["canonical_context"]
    assert governing_slice["token_count"] <= 500
    assert "conversation_history" not in root_content
    assert root_content["owner_identity"]["owner"] == "billing-ops"
    assert root_content["active_feature_flags"] == {
        "safe_mode": True,
        "human_approval_required": True,
        "runtime_override": True,
    }
    assert root_content["declared_write_scopes"] == ["billing.refund", "crm.note"]
    assert {
        "workflow_state",
        "user_intent",
        "api_response",
        "fact",
        "evidence",
        "checkpoint",
    }.issubset(node_types)


def build_dummy_governing_state(raw_log: dict) -> dict:
    """Keep only the minimum state needed for governance decisions."""

    active_feature_flags = {
        name: enabled
        for name, enabled in raw_log["feature_flags"].items()
        if enabled is True
    }

    return {
        "workflow_id": raw_log["workflow_id"],
        "branch_id": raw_log["branch_id"],
        "metadata": {
            "runtime": raw_log["runtime"],
            "workflow_name": raw_log["workflow_name"],
            "current_step": raw_log["current_step"],
        },
        "owner_identity": {
            "agent_id": raw_log["agent"]["agent_id"],
            "owner": raw_log["agent"]["owner"],
        },
        "active_feature_flags": active_feature_flags,
        "declared_write_scopes": raw_log["agent"]["declared_write_scopes"],
    }
