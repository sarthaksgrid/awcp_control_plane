import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.common.models import (
    GoverningSlice, 
    AgentIdentity, 
    WorkflowState, 
    EvidenceEntry
)

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Maintains a DAG of context artifacts, hashes, and checkpoints
    across a governed workflow.
    """

    def __init__(self, token_limit: int = 16000):
        self.token_limit = token_limit

    def assemble_context(
        self, 
        identity: AgentIdentity, 
        state: WorkflowState,
        raw_signals: Dict[str, Any],
        prior_evidence: List[EvidenceEntry] = None
    ) -> GoverningSlice:
        """
        Turn 1: Build the governing slice from runtime metadata and registry identity.
        Ensures the context stays within the 4K-16K token target.
        """
        logger.info(f"Assembling context for workflow {state.workflow_id}, agent {identity.agent_id}")
        
        # 1. Start with core identity and state
        slice_obj = GoverningSlice(
            identity=identity,
            state=state,
            current_tool_plan=raw_signals.get("tool_plan"),
            recent_history=raw_signals.get("history", []),
            active_evidence=prior_evidence or [],
            metadata=raw_signals.get("metadata", {})
        )

        # 2. Calculate initial token count (simplified estimate: 1 word ~ 1.3 tokens)
        current_tokens = self._estimate_tokens(slice_obj)
        slice_obj.token_count = current_tokens

        # 3. Prune if over limit
        if current_tokens > self.token_limit:
            self._prune_context(slice_obj)
            slice_obj.token_count = self._estimate_tokens(slice_obj)
            logger.warning(f"Context pruned: {current_tokens} -> {slice_obj.token_count} tokens")

        return slice_obj

    def _estimate_tokens(self, obj: GoverningSlice) -> int:
        """
        Simplified token estimation logic. 
        In a production system, use tiktoken or similar.
        """
        content = json.dumps(obj.model_dump(), default=str)
        # Rough heuristic: char count / 4
        return len(content) // 4

    def _prune_context(self, slice_obj: GoverningSlice):
        """
        Prioritized pruning:
        1. Metadata (except core ids)
        2. Deep history (keep last 3 turns)
        3. Prior evidence (keep last 2)
        """
        # Prune metadata fluff
        keys_to_keep = {"id", "type", "timestamp"}
        slice_obj.metadata = {k: v for k, v in slice_obj.metadata.items() if k in keys_to_keep}

        # Prune history to last 3 entries
        if len(slice_obj.recent_history) > 3:
            slice_obj.recent_history = slice_obj.recent_history[-3:]

        # Prune evidence to last 2 entries
        if len(slice_obj.active_evidence) > 2:
            slice_obj.active_evidence = slice_obj.active_evidence[-2:]

    def update_context(self, slice_obj: GoverningSlice, new_artifact: Dict[str, Any]):
        """Update the context graph with new evidence or tool results."""
        slice_obj.recent_history.append(new_artifact)
        slice_obj.token_count = self._estimate_tokens(slice_obj)
        
        if slice_obj.token_count > self.token_limit:
            self._prune_context(slice_obj)

    def check_freshness(self, current_hash: str, stored_hash: str) -> bool:
        """Compare current vs. stored hash for staleness detection."""
        return current_hash == stored_hash
