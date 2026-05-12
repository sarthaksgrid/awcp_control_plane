"""
AWCP — Context Graph Manager
================================
Maintains a DAG of context artifacts, hashes, and checkpoints
across a governed workflow.

Responsibilities:
  - Build the initial governing context slice (4K–16K tokens)
  - Track context hashes for staleness detection
  - Manage token budgets and relevance scoring
  - Store and retrieve cross-agent shared state
  - Maintain replay checkpoints for recovery
  - Fold RLM-compressed summaries back into the graph

Provides:
  - assemble_context()       — build governing slice for a branch
  - update_context()         — add new artifacts / evidence
  - check_freshness()        — compare current vs. stored hash
  - get_checkpoint()         — retrieve latest safe resume point
  - fold_summary()           — merge RLM output into the graph
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

import networkx as nx

from src.orchestration.context_graph.context_hashing import (
    HashComparison,
    compare_context_hashes,
    compute_context_hash,
    hash_node_payload,
)


class ContextGraphError(RuntimeError):
    """Base error raised by the context graph prototype."""


class ContextGraphCycleError(ContextGraphError):
    """Raised when an edge would break the DAG invariant."""


class ContextNodeNotFoundError(ContextGraphError, KeyError):
    """Raised when a referenced context node is missing."""


class ContextNodeType(str, Enum):
    """Context artifact categories used by the governance memory DAG."""

    WORKFLOW_STATE = "workflow_state"
    FACT = "fact"
    API_RESPONSE = "api_response"
    USER_INTENT = "user_intent"
    AGENT_MEMORY = "agent_memory"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    POLICY_DECISION = "policy_decision"
    APPROVAL = "approval"
    DEGRADATION = "degradation"
    EVIDENCE = "evidence"
    HANDOFF = "handoff"
    SUMMARY = "summary"
    CHECKPOINT = "checkpoint"


class LongTermMemoryBackend(Protocol):
    """Small adapter surface for Letta-like persistent memory stores."""

    def store(self, node: Mapping[str, Any]) -> Any:
        ...


class ContextBus(Protocol):
    """Small adapter surface for Multica-like shared context buses."""

    def publish(self, event_type: str, payload: Mapping[str, Any]) -> Any:
        ...


@dataclass
class RelevanceScore:
    """Relevance score plus explainable score components."""

    total: float
    lexical: float = 0.0
    type_weight: float = 0.0
    safety: float = 0.0
    proximity: float = 0.0
    importance: float = 0.0
    recency: float = 0.0
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 6),
            "lexical": round(self.lexical, 6),
            "type_weight": round(self.type_weight, 6),
            "safety": round(self.safety, 6),
            "proximity": round(self.proximity, 6),
            "importance": round(self.importance, 6),
            "recency": round(self.recency, 6),
            "required": self.required,
        }


@dataclass
class ContextNode:
    """A typed memory artifact in a workflow context DAG."""

    node_id: str
    workflow_id: str
    branch_id: str | None
    node_type: ContextNodeType
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    source: str | None = None
    actor: str | None = None
    summary: Any | None = None
    importance: float = 1.0
    safe_resume: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    token_estimate: int = 0
    content_hash: str = ""

    def __post_init__(self) -> None:
        self.node_type = coerce_node_type(self.node_type)
        self.tags = {str(tag) for tag in self.tags}
        self.token_estimate = self.token_estimate or estimate_tokens(self.render_search_text())
        self.refresh_hash()

    def refresh_hash(self) -> None:
        self.content_hash = hash_node_payload(
            node_type=self.node_type.value,
            content=self.content,
            metadata=self.metadata,
            tags=sorted(self.tags),
            source=self.source,
            actor=self.actor,
        )
        self.updated_at = datetime.now(timezone.utc)

    def render_search_text(self) -> str:
        return " ".join(
            part
            for part in (
                self.node_type.value,
                stringify_context(self.content),
                stringify_context(self.metadata),
                stringify_context(self.summary),
                " ".join(sorted(self.tags)),
                self.source or "",
                self.actor or "",
            )
            if part
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "tags": sorted(self.tags),
            "source": self.source,
            "actor": self.actor,
            "summary": self.summary,
            "importance": self.importance,
            "safe_resume": self.safe_resume,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "token_estimate": self.token_estimate,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ContextSliceItem:
    """A selected context node rendered for a governing slice."""

    node_id: str
    node_type: ContextNodeType
    content: Any
    metadata: dict[str, Any]
    tags: list[str]
    token_estimate: int
    relevance_score: float
    relevance_components: dict[str, Any]
    content_hash: str
    summary_used: bool = False
    truncated: bool = False
    safe_resume: bool = False
    source: str | None = None
    actor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "tags": self.tags,
            "token_estimate": self.token_estimate,
            "relevance_score": round(self.relevance_score, 6),
            "relevance_components": self.relevance_components,
            "content_hash": self.content_hash,
            "summary_used": self.summary_used,
            "truncated": self.truncated,
            "safe_resume": self.safe_resume,
            "source": self.source,
            "actor": self.actor,
        }


@dataclass(frozen=True)
class GoverningSlice:
    """Budgeted context packet used for policy, approval, handoff, or replay."""

    workflow_id: str
    branch_id: str | None
    current_step: Any
    token_budget: int
    token_count: int
    nodes: list[ContextSliceItem]
    omitted_node_ids: list[str]
    required_node_ids: list[str]
    context_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def node_ids(self) -> list[str]:
        return [node.node_id for node in self.nodes]

    @property
    def node_hashes(self) -> dict[str, str]:
        return {node.node_id: node.content_hash for node in self.nodes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "current_step": self.current_step,
            "token_budget": self.token_budget,
            "token_count": self.token_count,
            "nodes": [node.to_dict() for node in self.nodes],
            "omitted_node_ids": self.omitted_node_ids,
            "required_node_ids": self.required_node_ids,
            "context_hash": self.context_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class FreshnessReport:
    """Context hash comparison with optional node-level drift details."""

    comparison: HashComparison
    changed_node_ids: list[str] = field(default_factory=list)
    missing_node_ids: list[str] = field(default_factory=list)
    new_node_ids: list[str] = field(default_factory=list)

    @property
    def stored_hash(self) -> str:
        return self.comparison.stored_hash

    @property
    def current_hash(self) -> str:
        return self.comparison.current_hash

    @property
    def is_fresh(self) -> bool:
        return self.comparison.is_fresh

    @property
    def is_stale(self) -> bool:
        return self.comparison.is_stale             

    def to_dict(self) -> dict[str, Any]:
        payload = self.comparison.to_dict()
        payload["changed_node_ids"] = self.changed_node_ids
        payload["missing_node_ids"] = self.missing_node_ids
        payload["new_node_ids"] = self.new_node_ids
        return payload


@dataclass(frozen=True)
class ScoredContextNode:
    node: ContextNode
    score: RelevanceScore


class ContextGraphManager:
    """In-memory prototype of the AWCP Context Graph Manager.

    The manager keeps one directed acyclic graph of workflow memory artifacts.
    It is intentionally adapter-ready: a Letta-like memory backend and a
    Multica-like context bus can be supplied, but the core prototype stays
    deterministic and testable without either service.
    """

    TYPE_WEIGHTS: dict[ContextNodeType, float] = {
        ContextNodeType.WORKFLOW_STATE: 1.0,
        ContextNodeType.USER_INTENT: 0.95,
        ContextNodeType.POLICY_DECISION: 0.92,
        ContextNodeType.CHECKPOINT: 0.9,
        ContextNodeType.APPROVAL: 0.86,
        ContextNodeType.DEGRADATION: 0.84,
        ContextNodeType.EVIDENCE: 0.78,
        ContextNodeType.HANDOFF: 0.76,
        ContextNodeType.API_RESPONSE: 0.72,
        ContextNodeType.TOOL_RESULT: 0.68,
        ContextNodeType.TOOL_CALL: 0.62,
        ContextNodeType.FACT: 0.58,
        ContextNodeType.SUMMARY: 0.56,
        ContextNodeType.AGENT_MEMORY: 0.48,
    }
    SAFETY_TERMS = {
        "approval",
        "checkpoint",
        "degradation",
        "error",
        "evidence",
        "failure",
        "policy",
        "risk",
        "safe_resume",
        "scope",
        "write",
        "write_scope",
    }

    def __init__(
        self,
        *,
        default_token_budget: int = 16_000,
        max_token_budget: int = 16_000,
        min_token_budget: int = 4_000,
        memory_backend: LongTermMemoryBackend | None = None,
        context_bus: ContextBus | None = None,
    ) -> None:
        self.default_token_budget = default_token_budget
        self.max_token_budget = max_token_budget
        self.min_token_budget = min_token_budget
        self.memory_backend = memory_backend
        self.context_bus = context_bus
        self.graph: nx.DiGraph = nx.DiGraph()
        self._sequence = 0
        self._insertion_order: dict[str, int] = {}

    def update_context(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        artifact: Any | None = None,
        *,
        content: Any | None = None,
        node_type: ContextNodeType | str = ContextNodeType.FACT,
        node_id: str | None = None,
        parents: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        tags: Iterable[str] | None = None,
        source: str | None = None,
        actor: str | None = None,
        summary: Any | None = None,
        importance: float = 1.0,
        safe_resume: bool = False,
    ) -> ContextNode:
        """Add a context artifact as a DAG node and return it."""

        node_type = coerce_node_type(node_type)
        node_id = node_id or self._next_node_id(workflow_id, branch_id, node_type)
        if node_id in self.graph:
            raise ContextGraphError(f"context node already exists: {node_id}")

        parent_ids = list(parents or [])
        self._ensure_nodes_exist(parent_ids)

        node_content = content if content is not None else artifact
        node = ContextNode(
            node_id=node_id,
            workflow_id=workflow_id,
            branch_id=branch_id,
            node_type=node_type,
            content={} if node_content is None else node_content,
            metadata=dict(metadata or {}),
            tags=set(tags or []),
            source=source,
            actor=actor,
            summary=summary,
            importance=max(0.0, importance),
            safe_resume=safe_resume,
        )

        self.graph.add_node(node_id, data=node)
        self._sequence += 1
        self._insertion_order[node_id] = self._sequence
        try:
            for parent_id in parent_ids:
                self.graph.add_edge(
                    parent_id,
                    node_id,
                    relation="depends_on",
                    created_at=datetime.now(timezone.utc),
                )
            self._assert_acyclic()
        except Exception:
            self.graph.remove_node(node_id)
            self._insertion_order.pop(node_id, None)
            raise

        self._store_in_long_term_memory(node)
        self._publish("context.node_added", {"node": node.to_dict(), "parents": parent_ids})
        return node

    def link_context(
        self,
        parent_id: str,
        child_id: str,
        *,
        relation: str = "depends_on",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Connect two existing nodes while preserving the DAG invariant."""

        self._ensure_nodes_exist([parent_id, child_id])
        edge_payload = {
            "relation": relation,
            "metadata": dict(metadata or {}),
            "created_at": datetime.now(timezone.utc),
        }
        self.graph.add_edge(parent_id, child_id, **edge_payload)
        try:
            self._assert_acyclic()
        except ContextGraphCycleError:
            self.graph.remove_edge(parent_id, child_id)
            raise

    def assemble_context(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        *,
        current_step: Any | None = None,
        query: str | None = None,
        token_budget: int | None = None,
        required_node_ids: Iterable[str] | None = None,
        include_types: Iterable[ContextNodeType | str] | None = None,
        focus_node_id: str | None = None,
        include_lineage: bool = True,
        limit: int | None = None,
    ) -> GoverningSlice:
        """Build a relevance-ranked, token-budgeted governing context slice."""

        budget = self._normalize_token_budget(token_budget)
        required_ids = list(dict.fromkeys(required_node_ids or []))
        self._ensure_nodes_exist(required_ids)

        scored_nodes = self.find_relevant_nodes(
            workflow_id,
            branch_id,
            current_step=current_step,
            query=query,
            focus_node_id=focus_node_id,
            include_types=include_types,
            required_node_ids=required_ids,
            limit=limit,
        )
        score_by_id = {item.node.node_id: item.score for item in scored_nodes}

        ordered_ids: list[str] = []
        for node_id in required_ids:
            if include_lineage:
                for lineage_id in self._ordered_lineage(node_id, max_hops=2):
                    append_unique(ordered_ids, lineage_id)
            append_unique(ordered_ids, node_id)

        for scored in scored_nodes:
            if include_lineage:
                for lineage_id in self._ordered_lineage(scored.node.node_id, max_hops=2):
                    append_unique(ordered_ids, lineage_id)
            append_unique(ordered_ids, scored.node.node_id)

        selected: list[ContextSliceItem] = []
        selected_ids: set[str] = set()
        remaining = budget
        for node_id in ordered_ids:
            if node_id in selected_ids:
                continue
            node = self.get_node(node_id)
            score = score_by_id.get(
                node_id,
                RelevanceScore(
                    total=0.4,
                    type_weight=self.TYPE_WEIGHTS.get(node.node_type, 0.5),
                    required=node_id in required_ids,
                ),
            )
            item = self._render_slice_item(
                node,
                score,
                remaining_tokens=remaining,
                force=node_id in required_ids,
            )
            if item is None:
                continue
            selected.append(item)
            selected_ids.add(node_id)
            remaining -= item.token_estimate
            if remaining <= 0:
                break

        omitted_node_ids = [
            scored.node.node_id
            for scored in scored_nodes
            if scored.node.node_id not in selected_ids
        ]
        token_count = sum(item.token_estimate for item in selected)
        context_hash = compute_context_hash(
            {
                "branch_id": branch_id,
                "current_step": current_step,
                "nodes": [
                    {
                        "content": item.content,
                        "content_hash": item.content_hash,
                        "node_id": item.node_id,
                        "node_type": item.node_type.value,
                        "summary_used": item.summary_used,
                        "truncated": item.truncated,
                    }
                    for item in selected
                ],
                "token_count": token_count,
                "workflow_id": workflow_id,
            }
        )
        return GoverningSlice(
            workflow_id=workflow_id,
            branch_id=branch_id,
            current_step=current_step,
            token_budget=budget,
            token_count=token_count,
            nodes=selected,
            omitted_node_ids=omitted_node_ids,
            required_node_ids=required_ids,
            context_hash=context_hash,
            created_at=datetime.now(timezone.utc),
        )

    def find_relevant_nodes(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        *,
        current_step: Any | None = None,
        query: str | None = None,
        focus_node_id: str | None = None,
        include_types: Iterable[ContextNodeType | str] | None = None,
        exclude_node_ids: Iterable[str] | None = None,
        required_node_ids: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> list[ScoredContextNode]:
        """Return candidate nodes ranked by relevance to the current step."""

        if focus_node_id is not None:
            self._ensure_nodes_exist([focus_node_id])

        allowed_types = (
            {coerce_node_type(node_type) for node_type in include_types}
            if include_types is not None
            else None
        )
        excluded = set(exclude_node_ids or [])
        required = set(required_node_ids or [])
        query_terms = normalize_terms(" ".join([query or "", stringify_context(current_step)]))
        candidates = [
            node
            for node in self.get_branch_nodes(workflow_id, branch_id)
            if node.node_id not in excluded
            and (allowed_types is None or node.node_type in allowed_types)
        ]

        scored = [
            ScoredContextNode(
                node=node,
                score=self._score_node(
                    node,
                    query_terms=query_terms,
                    focus_node_id=focus_node_id,
                    required=node.node_id in required,
                ),
            )
            for node in candidates
        ]
        scored.sort(
            key=lambda item: (
                item.score.required,
                item.score.total,
                self._insertion_order.get(item.node.node_id, 0),
            ),
            reverse=True,
        )
        return scored[:limit] if limit else scored

    def check_freshness(
        self,
        stored_hash: str | GoverningSlice,
        *,
        current_hash: str | GoverningSlice | None = None,
        stored_node_hashes: Mapping[str, str] | None = None,
        workflow_id: str | None = None,
        branch_id: str | None = None,
        current_step: Any | None = None,
        query: str | None = None,
        token_budget: int | None = None,
        required_node_ids: Iterable[str] | None = None,
        include_types: Iterable[ContextNodeType | str] | None = None,
        focus_node_id: str | None = None,
    ) -> FreshnessReport:
        """Compare a stored context hash with current graph state."""

        stored_hash_value, stored_nodes = extract_slice_hash(stored_hash)
        if stored_node_hashes is not None:
            stored_nodes = dict(stored_node_hashes)

        current_nodes: dict[str, str] = {}
        if current_hash is None:
            if workflow_id is None:
                raise ContextGraphError("workflow_id is required when current_hash is not provided")
            current_slice = self.assemble_context(
                workflow_id,
                branch_id,
                current_step=current_step,
                query=query,
                token_budget=token_budget,
                required_node_ids=required_node_ids,
                include_types=include_types,
                focus_node_id=focus_node_id,
            )
            current_hash_value = current_slice.context_hash
            current_nodes = current_slice.node_hashes
        else:
            current_hash_value, current_nodes = extract_slice_hash(current_hash)

        changed: list[str] = []
        missing: list[str] = []
        new: list[str] = []
        if stored_nodes:
            current_keys = set(current_nodes)
            stored_keys = set(stored_nodes)
            changed = sorted(
                node_id
                for node_id in stored_keys & current_keys
                if stored_nodes[node_id] != current_nodes[node_id]
            )
            missing = sorted(stored_keys - current_keys)
            new = sorted(current_keys - stored_keys)

        comparison = compare_context_hashes(
            stored_hash_value,
            current_hash_value,
            details={
                "changed_node_count": len(changed),
                "missing_node_count": len(missing),
                "new_node_count": len(new),
            },
        )
        return FreshnessReport(
            comparison=comparison,
            changed_node_ids=changed,
            missing_node_ids=missing,
            new_node_ids=new,
        )

    def create_checkpoint(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        state: Any | None = None,
        *,
        checkpoint_id: str | None = None,
        parents: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        actor: str | None = None,
        safe_resume: bool = True,
    ) -> ContextNode:
        """Create a verified safe-resume checkpoint node."""

        checkpoint_metadata = dict(metadata or {})
        if checkpoint_id is not None:
            checkpoint_metadata["checkpoint_id"] = checkpoint_id
        checkpoint_metadata["safe_resume"] = safe_resume
        return self.update_context(
            workflow_id,
            branch_id,
            content={} if state is None else state,
            node_type=ContextNodeType.CHECKPOINT,
            parents=parents,
            metadata=checkpoint_metadata,
            tags={"checkpoint", "safe_resume"} if safe_resume else {"checkpoint"},
            actor=actor,
            safe_resume=safe_resume,
            importance=1.25,
        )

    def get_checkpoint(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        *,
        before_node_id: str | None = None,
        safe_only: bool = True,
    ) -> ContextNode | None:
        """Return the latest checkpoint, optionally before a failed node."""

        if before_node_id is not None:
            self._ensure_nodes_exist([before_node_id])
            before_order = self._insertion_order.get(before_node_id, math.inf)
            ancestor_ids = nx.ancestors(self.graph, before_node_id)
        else:
            before_order = math.inf
            ancestor_ids = set()

        candidates: list[ContextNode] = []
        for node in self.get_branch_nodes(workflow_id, branch_id):
            is_checkpoint = (
                node.node_type is ContextNodeType.CHECKPOINT
                or node.safe_resume
                or "checkpoint" in node.tags
            )
            if not is_checkpoint:
                continue
            if safe_only and not node.safe_resume:
                continue
            if before_node_id is not None:
                node_order = self._insertion_order.get(node.node_id, 0)
                if node.node_id not in ancestor_ids and node_order >= before_order:
                    continue
            candidates.append(node)

        candidates.sort(key=lambda node: self._insertion_order.get(node.node_id, 0), reverse=True)
        return candidates[0] if candidates else None

    def fold_summary(
        self,
        workflow_id: str,
        branch_id: str | None,
        summary: Any,
        *,
        source_node_ids: Iterable[str],
        metadata: Mapping[str, Any] | None = None,
        tags: Iterable[str] | None = None,
        actor: str | None = None,
    ) -> ContextNode:
        """Fold an RLM-compressed summary back into the context graph."""

        source_ids = list(dict.fromkeys(source_node_ids))
        self._ensure_nodes_exist(source_ids)
        summary_metadata = dict(metadata or {})
        summary_metadata.update(
            {
                "compressed_from": source_ids,
                "compressed_from_count": len(source_ids),
                "folding_strategy": summary_metadata.get("folding_strategy", "rlm"),
            }
        )
        summary_tags = {"summary", "rlm_fold", *(tags or [])}
        return self.update_context(
            workflow_id,
            branch_id,
            content={"summary": summary, "source_node_ids": source_ids},
            node_type=ContextNodeType.SUMMARY,
            parents=source_ids,
            metadata=summary_metadata,
            tags=summary_tags,
            actor=actor,
            importance=0.85,
        )

    def get_node(self, node_id: str) -> ContextNode:
        self._ensure_nodes_exist([node_id])
        return self.graph.nodes[node_id]["data"]

    def get_branch_nodes(
        self,
        workflow_id: str,
        branch_id: str | None = None,
        *,
        include_workflow_global: bool = True,
    ) -> list[ContextNode]:
        """Return nodes for a workflow branch in insertion order."""

        nodes: list[ContextNode] = []
        for node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]["data"]
            if node.workflow_id != workflow_id:
                continue
            if branch_id is not None:
                if node.branch_id != branch_id and not (include_workflow_global and node.branch_id is None):
                    continue
            nodes.append(node)
        nodes.sort(key=lambda node: self._insertion_order.get(node.node_id, 0))
        return nodes

    def lineage(self, node_id: str, *, direction: str = "ancestors") -> list[ContextNode]:
        """Return ancestor or descendant context for a node in topological order."""

        self._ensure_nodes_exist([node_id])
        if direction == "ancestors":
            node_ids = nx.ancestors(self.graph, node_id)
        elif direction == "descendants":
            node_ids = nx.descendants(self.graph, node_id)
        else:
            raise ValueError("direction must be 'ancestors' or 'descendants'")
        ordered = [node for node in nx.topological_sort(self.graph) if node in node_ids]
        return [self.get_node(item) for item in ordered]

    def export_graph(self, workflow_id: str | None = None) -> dict[str, Any]:
        """Export graph data for evidence packets, debugging, or UI inspection."""

        nodes = [
            self.graph.nodes[node_id]["data"]
            for node_id in self.graph.nodes
            if workflow_id is None or self.graph.nodes[node_id]["data"].workflow_id == workflow_id
        ]
        node_ids = {node.node_id for node in nodes}
        edges = [
            {
                "parent": parent,
                "child": child,
                "relation": data.get("relation", "depends_on"),
                "metadata": data.get("metadata", {}),
                "created_at": data.get("created_at").isoformat()
                if isinstance(data.get("created_at"), datetime)
                else data.get("created_at"),
            }
            for parent, child, data in self.graph.edges(data=True)
            if parent in node_ids and child in node_ids
        ]
        return {"nodes": [node.to_dict() for node in nodes], "edges": edges}

    def _score_node(
        self,
        node: ContextNode,
        *,
        query_terms: set[str],
        focus_node_id: str | None,
        required: bool,
    ) -> RelevanceScore:
        node_terms = normalize_terms(node.render_search_text())
        lexical = len(query_terms & node_terms) / max(1, len(query_terms)) if query_terms else 0.0
        type_weight = self.TYPE_WEIGHTS.get(node.node_type, 0.5)
        safety = self._safety_score(node, node_terms)
        proximity = self._proximity_score(node.node_id, focus_node_id)
        importance = min(node.importance / 2.0, 1.0)
        recency = self._recency_score(node.node_id)

        total = (
            0.34 * lexical
            + 0.18 * type_weight
            + 0.16 * safety
            + 0.14 * proximity
            + 0.12 * importance
            + 0.06 * recency
        )
        if required:
            total += 1.0
        return RelevanceScore(
            total=total,
            lexical=lexical,
            type_weight=type_weight,
            safety=safety,
            proximity=proximity,
            importance=importance,
            recency=recency,
            required=required,
        )

    def _safety_score(self, node: ContextNode, node_terms: set[str]) -> float:
        score = 0.0
        if node.safe_resume:
            score += 0.45
        if node.node_type in {
            ContextNodeType.WORKFLOW_STATE,
            ContextNodeType.POLICY_DECISION,
            ContextNodeType.CHECKPOINT,
            ContextNodeType.APPROVAL,
            ContextNodeType.DEGRADATION,
        }:
            score += 0.25
        if self.SAFETY_TERMS & node_terms:
            score += 0.2
        if any(key in node.metadata for key in ("risk_tier", "write_scope", "policy_result", "rollback_pointer")):
            score += 0.1
        return min(score, 1.0)

    def _proximity_score(self, node_id: str, focus_node_id: str | None) -> float:
        if focus_node_id is None:
            return 0.0
        if node_id == focus_node_id:
            return 1.0
        distances: list[int] = []
        for start, end in ((node_id, focus_node_id), (focus_node_id, node_id)):
            if nx.has_path(self.graph, start, end):
                distances.append(nx.shortest_path_length(self.graph, start, end))
        if not distances:
            return 0.0
        return max(0.0, 1.0 - min(distances) / 6.0)

    def _recency_score(self, node_id: str) -> float:
        if not self._insertion_order:
            return 0.0
        return self._insertion_order.get(node_id, 0) / max(self._insertion_order.values())

    def _render_slice_item(
        self,
        node: ContextNode,
        score: RelevanceScore,
        *,
        remaining_tokens: int,
        force: bool = False,
    ) -> ContextSliceItem | None:
        if remaining_tokens <= 0:
            return None

        content = node.content
        token_estimate = node.token_estimate
        summary_used = False
        truncated = False

        if token_estimate > remaining_tokens and node.summary is not None:
            summary_tokens = estimate_tokens(stringify_context(node.summary))
            if summary_tokens <= remaining_tokens or force:
                content = node.summary
                token_estimate = min(summary_tokens, remaining_tokens)
                summary_used = True

        if token_estimate > remaining_tokens:
            if not force and remaining_tokens < 32:
                return None
            content = truncate_to_token_budget(content, remaining_tokens)
            token_estimate = estimate_tokens(stringify_context(content))
            truncated = True

        if token_estimate <= 0:
            token_estimate = 1

        metadata = dict(node.metadata)
        if summary_used:
            metadata["summary_used"] = True
        if truncated:
            metadata["truncated"] = True

        return ContextSliceItem(
            node_id=node.node_id,
            node_type=node.node_type,
            content=content,
            metadata=metadata,
            tags=sorted(node.tags),
            token_estimate=token_estimate,
            relevance_score=score.total,
            relevance_components=score.to_dict(),
            content_hash=node.content_hash,
            summary_used=summary_used,
            truncated=truncated,
            safe_resume=node.safe_resume,
            source=node.source,
            actor=node.actor,
        )

    def _ordered_lineage(self, node_id: str, *, max_hops: int = 2) -> list[str]:
        self._ensure_nodes_exist([node_id])
        lineage_ids: set[str] = set()
        frontier = {node_id}
        for _ in range(max_hops):
            parents: set[str] = set()
            for item in frontier:
                parents.update(self.graph.predecessors(item))
            lineage_ids.update(parents)
            frontier = parents
            if not frontier:
                break
        return [item for item in nx.topological_sort(self.graph) if item in lineage_ids]

    def _normalize_token_budget(self, token_budget: int | None) -> int:
        requested = token_budget or self.default_token_budget
        if requested <= 0:
            raise ValueError("token_budget must be positive")
        return min(requested, self.max_token_budget)

    def _next_node_id(
        self,
        workflow_id: str,
        branch_id: str | None,
        node_type: ContextNodeType,
    ) -> str:
        self._sequence += 1
        stem = "-".join(
            part
            for part in (
                sanitize_id(workflow_id),
                sanitize_id(branch_id or "global"),
                sanitize_id(node_type.value),
                f"{self._sequence:06d}",
            )
            if part
        )
        self._sequence -= 1
        return stem

    def _ensure_nodes_exist(self, node_ids: Iterable[str]) -> None:
        for node_id in node_ids:
            if node_id not in self.graph:
                raise ContextNodeNotFoundError(f"context node not found: {node_id}")

    def _assert_acyclic(self) -> None:
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ContextGraphCycleError("context graph must remain a directed acyclic graph")

    def _store_in_long_term_memory(self, node: ContextNode) -> None:
        if self.memory_backend is None:
            return
        self.memory_backend.store(node.to_dict())

    def _publish(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self.context_bus is None:
            return
        self.context_bus.publish(event_type, payload)


def coerce_node_type(node_type: ContextNodeType | str) -> ContextNodeType:
    if isinstance(node_type, ContextNodeType):
        return node_type
    try:
        return ContextNodeType(str(node_type))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ContextNodeType)
        raise ValueError(f"unknown context node type {node_type!r}; expected one of: {allowed}") from exc


def estimate_tokens(text: Any) -> int:
    """Rough token estimate for budget enforcement without a tokenizer service."""

    rendered = stringify_context(text)
    if not rendered:
        return 1
    wordish = len(re.findall(r"\w+|[^\w\s]", rendered))
    charish = math.ceil(len(rendered) / 4)
    return max(1, max(wordish, charish))


def stringify_context(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def normalize_terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-zA-Z0-9_./:-]+", text.lower())
        if len(term) > 1
    }


def truncate_to_token_budget(value: Any, token_budget: int) -> str:
    if token_budget <= 0:
        return ""
    text = stringify_context(value)
    max_chars = max(1, token_budget * 4)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 15)].rstrip() + " [truncated]"


def sanitize_id(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value.strip()).strip("-")
    return sanitized[:80] or "context"


def append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def extract_slice_hash(value: str | GoverningSlice) -> tuple[str, dict[str, str]]:
    if isinstance(value, GoverningSlice):
        return value.context_hash, value.node_hashes
    return str(value), {}
