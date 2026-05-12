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
from src.orchestration.context_graph.context_manager import ContextManager
from src.orchestration.context_graph.context_hashing import ContextHasher


def run_hash(
    identity: AgentIdentity,
    state: WorkflowState,
    raw_signals: Dict[str, Any],
    prior_evidence: Optional[List[EvidenceEntry]] = None,
) -> str:
    """
    Assemble a governing context slice and return its deterministic DS-3 hash.
    """
    context_manager = ContextManager()

    # DS-1: Assemble and prune
    slice_obj = context_manager.assemble_context(
        identity, state, raw_signals, prior_evidence
    )

    # DS-3: Hash the canonical form
    hash_value = ContextHasher.generate_hash(slice_obj)

    return hash_value


def run_hash_snapshot(
    identity: AgentIdentity,
    state: WorkflowState,
    raw_signals: Dict[str, Any],
    prior_evidence: Optional[List[EvidenceEntry]] = None,
) -> Dict[str, Any]:
    """
    Return both the assembled slice and its hash for replay/debug workflows.
    """
    context_manager = ContextManager()
    slice_obj = context_manager.assemble_context(
        identity, state, raw_signals, prior_evidence
    )
    return {
        "context_hash": ContextHasher.generate_hash(slice_obj),
        "canonical_context": ContextHasher.canonicalize(slice_obj),
    }
