"""Tests for the Context Graph Manager."""

import pytest

from src.orchestration.context_graph.context_manager import (
    ContextGraphCycleError,
    ContextGraphManager,
    ContextNodeType,
)
from src.orchestration.context_graph.context_hashing import compute_context_hash


def test_dummy_context_graph_happy_path_smoke() -> None:
    manager = ContextGraphManager(default_token_budget=300)

    workflow_state = manager.update_context(
        "demo-workflow",
        "main",
        {
            "owner": "data-science",
            "declared_write_scopes": ["billing.refund"],
            "feature_flags": {"safe_mode": True},
        },
        node_type=ContextNodeType.WORKFLOW_STATE,
        tags={"governing", "write_scope"},
    )
    user_intent = manager.update_context(
        "demo-workflow",
        "main",
        "User wants a refund for duplicate billing charge INV-42.",
        node_type=ContextNodeType.USER_INTENT,
        parents=[workflow_state.node_id],
    )
    api_response = manager.update_context(
        "demo-workflow",
        "main",
        {"invoice_id": "INV-42", "duplicate_charge": True, "amount": 25.0},
        node_type=ContextNodeType.API_RESPONSE,
        parents=[user_intent.node_id],
    )
    checkpoint = manager.create_checkpoint(
        "demo-workflow",
        "main",
        {"step": "validated-refund-context"},
        parents=[api_response.node_id],
    )

    governing_slice = manager.assemble_context(
        "demo-workflow",
        "main",
        query="refund duplicate billing INV-42",
        current_step={"tool": "billing.refund"},
        required_node_ids=[workflow_state.node_id],
        focus_node_id=api_response.node_id,
    )

    assert workflow_state.node_id in governing_slice.node_ids
    assert user_intent.node_id in governing_slice.node_ids
    assert api_response.node_id in governing_slice.node_ids
    assert governing_slice.context_hash
    assert governing_slice.token_count <= 300
    assert manager.get_checkpoint("demo-workflow", "main") == checkpoint


def test_context_graph_rejects_cycles() -> None:
    manager = ContextGraphManager()
    root = manager.update_context(
        "wf-1",
        "branch-a",
        {"owner": "ops", "declared_write_scopes": ["billing.refund"]},
        node_type=ContextNodeType.WORKFLOW_STATE,
    )
    child = manager.update_context(
        "wf-1",
        "branch-a",
        "Refund workflow intent",
        node_type=ContextNodeType.USER_INTENT,
        parents=[root.node_id],
    )

    with pytest.raises(ContextGraphCycleError):
        manager.link_context(child.node_id, root.node_id)


def test_assemble_context_ranks_relevant_nodes_and_respects_budget() -> None:
    manager = ContextGraphManager(default_token_budget=120, max_token_budget=120)
    root = manager.update_context(
        "refund-branch-882",
        "main",
        {
            "owner": "billing-ops",
            "feature_flags": {"safer_profiles": False},
            "declared_write_scopes": ["billing.refund", "crm.note"],
        },
        node_type=ContextNodeType.WORKFLOW_STATE,
        tags={"governing", "write_scope"},
        metadata={"write_scope": "billing.refund"},
        importance=1.5,
    )
    intent = manager.update_context(
        "refund-branch-882",
        "main",
        "Customer asks to reverse a duplicate billing charge on invoice INV-123.",
        node_type=ContextNodeType.USER_INTENT,
        parents=[root.node_id],
    )
    api_response = manager.update_context(
        "refund-branch-882",
        "main",
        {"invoice_id": "INV-123", "duplicate_charge": True, "amount": 40.0},
        node_type=ContextNodeType.API_RESPONSE,
        parents=[intent.node_id],
    )
    irrelevant = manager.update_context(
        "refund-branch-882",
        "main",
        "Unrelated deployment trace " * 80,
        node_type=ContextNodeType.AGENT_MEMORY,
        parents=[root.node_id],
    )

    governing_slice = manager.assemble_context(
        "refund-branch-882",
        "main",
        query="duplicate billing refund INV-123 write scope",
        current_step={"tool": "billing.refund", "risk_tier": "HIGH"},
        token_budget=120,
        required_node_ids=[root.node_id],
        focus_node_id=api_response.node_id,
    )

    assert governing_slice.token_count <= 120
    assert root.node_id in governing_slice.node_ids
    assert intent.node_id in governing_slice.node_ids
    assert api_response.node_id in governing_slice.node_ids
    assert irrelevant.node_id not in governing_slice.node_ids
    assert irrelevant.node_id in governing_slice.omitted_node_ids


def test_check_freshness_detects_changed_node_hashes() -> None:
    manager = ContextGraphManager(default_token_budget=200, max_token_budget=200)
    root = manager.update_context(
        "wf-2",
        "main",
        {"owner": "ops", "feature_flags": {"safer_profile": False}},
        node_type=ContextNodeType.WORKFLOW_STATE,
    )
    stored_slice = manager.assemble_context(
        "wf-2",
        "main",
        query="owner feature flags",
        required_node_ids=[root.node_id],
    )

    fresh = manager.check_freshness(
        stored_slice,
        workflow_id="wf-2",
        branch_id="main",
        query="owner feature flags",
        required_node_ids=[root.node_id],
    )
    assert fresh.is_fresh

    root.content["feature_flags"]["safer_profile"] = True
    root.refresh_hash()
    stale = manager.check_freshness(
        stored_slice,
        workflow_id="wf-2",
        branch_id="main",
        query="owner feature flags",
        required_node_ids=[root.node_id],
    )

    assert stale.is_stale
    assert stale.changed_node_ids == [root.node_id]


def test_get_checkpoint_returns_latest_safe_resume_before_failure() -> None:
    manager = ContextGraphManager()
    root = manager.update_context(
        "wf-3",
        "main",
        {"workflow": "refund"},
        node_type=ContextNodeType.WORKFLOW_STATE,
    )
    first_checkpoint = manager.create_checkpoint(
        "wf-3",
        "main",
        {"step": "intake"},
        checkpoint_id="cp-1",
        parents=[root.node_id],
    )
    tool_result = manager.update_context(
        "wf-3",
        "main",
        {"validated": True},
        node_type=ContextNodeType.TOOL_RESULT,
        parents=[first_checkpoint.node_id],
    )
    second_checkpoint = manager.create_checkpoint(
        "wf-3",
        "main",
        {"step": "pre-write"},
        checkpoint_id="cp-2",
        parents=[tool_result.node_id],
    )
    failure = manager.update_context(
        "wf-3",
        "main",
        {"error": "write rejected"},
        node_type=ContextNodeType.EVIDENCE,
        parents=[second_checkpoint.node_id],
    )

    checkpoint = manager.get_checkpoint("wf-3", "main", before_node_id=failure.node_id)

    assert checkpoint == second_checkpoint


def test_fold_summary_adds_rlm_summary_with_source_lineage() -> None:
    manager = ContextGraphManager()
    intent = manager.update_context(
        "wf-4",
        "main",
        "User wants approval context for a refund.",
        node_type=ContextNodeType.USER_INTENT,
    )
    api_response = manager.update_context(
        "wf-4",
        "main",
        {"invoice": "INV-9", "balance": 0},
        node_type=ContextNodeType.API_RESPONSE,
        parents=[intent.node_id],
    )

    summary = manager.fold_summary(
        "wf-4",
        "main",
        "Refund is safe to review because invoice balance is zero.",
        source_node_ids=[intent.node_id, api_response.node_id],
        actor="rlm-summarizer",
    )

    assert summary.node_type is ContextNodeType.SUMMARY
    assert summary.metadata["compressed_from"] == [intent.node_id, api_response.node_id]
    assert "rlm_fold" in summary.tags
    assert api_response in manager.lineage(summary.node_id)


def test_optional_memory_and_bus_adapters_receive_context_events() -> None:
    class Memory:
        def __init__(self) -> None:
            self.nodes = []

        def store(self, node):
            self.nodes.append(node)

    class Bus:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event_type, payload):
            self.events.append((event_type, payload))

    memory = Memory()
    bus = Bus()
    manager = ContextGraphManager(memory_backend=memory, context_bus=bus)
    node = manager.update_context("wf-5", "main", "shared context", node_type="fact")

    assert memory.nodes[0]["node_id"] == node.node_id
    assert bus.events[0][0] == "context.node_added"


def test_context_hash_is_canonical_for_equivalent_snapshots() -> None:
    left = compute_context_hash({"b": [2, 1], "a": {"x": True}})
    right = compute_context_hash({"a": {"x": True}, "b": [2, 1]})

    assert left == right
