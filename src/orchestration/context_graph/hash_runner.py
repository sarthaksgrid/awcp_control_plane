"""
AWCP — Hash Runner
====================
Convenience functions that combine the DS-1 (Context Assembly)
and DS-3 (Context Hashing) pipelines into single calls.

Used by downstream systems (Evidence Ledger, Degradation Engine)
that need both the assembled slice and its tamper-proof fingerprint.
"""

from typing import Any, Dict, List, Optional

from src.common.models import AgentIdentity, WorkflowState, EvidenceEntry
from src.orchestration.context_graph.context_manager import ContextGraphManager
from src.orchestration.context_graph.context_hashing import canonicalize_snapshot


def run_hash(
    identity: AgentIdentity,
    state: WorkflowState,
    raw_signals: Dict[str, Any],
    prior_evidence: Optional[List[EvidenceEntry]] = None,
) -> str:
    """
    Assemble a governing context slice and return its deterministic DS-3 hash.
    """
    context_manager = ContextGraphManager()

    # DS-1: Assemble and prune
    slice_obj = context_manager.assemble_context(
        state.workflow_id,
        state.branch_id,
        current_step=raw_signals,
    )

    # DS-3: The GoverningSlice already computes its context_hash during assembly
    return slice_obj.context_hash


def run_hash_snapshot(
    identity: AgentIdentity,
    state: WorkflowState,
    raw_signals: Dict[str, Any],
    prior_evidence: Optional[List[EvidenceEntry]] = None,
) -> Dict[str, Any]:
    """
    Return both the assembled slice and its hash for replay/debug workflows.
    """
    context_manager = ContextGraphManager()
    slice_obj = context_manager.assemble_context(
        state.workflow_id,
        state.branch_id,
        current_step=raw_signals,
    )
    return {
        "context_hash": slice_obj.context_hash,
        "canonical_context": canonicalize_snapshot(slice_obj.to_dict()),
    }
