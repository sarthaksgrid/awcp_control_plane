"""
AWCP - RLM Summarizer
=====================
Recursive summarizer for compressing large trace histories.

The DS-1 Week 2 implementation runs independently with deterministic local
logic. A live LLM provider can be plugged in later through the gateway without
changing the summarizer contract.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from src.execution.llm_gateway.gateway import LLMGateway, estimate_tokens


Summary = Dict[str, Any]
GatewaySummarizer = Callable[..., Dict[str, Any]]


GOVERNANCE_KEYWORDS = (
    "error",
    "failed",
    "failure",
    "exception",
    "timeout",
    "retry",
    "denied",
    "deny",
    "policy",
    "approval",
    "token",
    "write",
    "update",
    "delete",
    "rollback",
    "degraded",
    "risk",
    "unsafe",
    "resume",
)

STATE_CHANGE_KEYWORDS = ("write", "update", "delete", "create", "rollback", "restore")
FAILURE_KEYWORDS = ("error", "failed", "failure", "exception", "timeout", "retry")
POLICY_KEYWORDS = ("policy", "denied", "deny", "approval", "token", "risk", "unsafe")


def summarize_trace(
    trace_events: Sequence[Any],
    *,
    metadata: Optional[Dict[str, Any]] = None,
    token_budget: int = 1000,
    chunk_token_budget: int = 350,
    gateway: Optional[Any] = None,
    max_fold_depth: int = 5,
) -> Summary:
    """
    Compress workflow trace events into a governance-preserving summary.

    This function accepts ordinary Python dictionaries so DS-1 can run without
    the Evidence Ledger, Replay Engine, workflow runtime, or provider keys.
    """
    normalized_events = [_normalize_event(event, index) for index, event in enumerate(trace_events)]
    ranked_events = rank_relevance(normalized_events)

    folded = _fold_events(
        ranked_events,
        metadata=metadata or {},
        token_budget=token_budget,
        chunk_token_budget=chunk_token_budget,
        gateway=gateway,
        depth=1,
        max_fold_depth=max_fold_depth,
    )

    summary = _build_structured_summary(
        ranked_events,
        folded_text=folded["summary"],
        metadata=metadata or {},
        fold_depth=folded["fold_depth"],
        token_budget=token_budget,
    )
    return summary


def fold_document(
    document: Any,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    token_budget: int = 1000,
    chunk_token_budget: int = 350,
    gateway: Optional[Any] = None,
    max_fold_depth: int = 5,
) -> Summary:
    """
    Recursively fold a long document or list of trace-like records.

    Strings are split into line-based pseudo-events. Lists are treated as trace
    events and passed through the same governance-preserving path.
    """
    if isinstance(document, list):
        return summarize_trace(
            document,
            metadata=metadata,
            token_budget=token_budget,
            chunk_token_budget=chunk_token_budget,
            gateway=gateway,
            max_fold_depth=max_fold_depth,
        )

    text = _to_text(document)
    events = [{"event": line.strip()} for line in text.splitlines() if line.strip()]
    if not events and text.strip():
        events = [{"event": text.strip()}]

    return summarize_trace(
        events,
        metadata=metadata,
        token_budget=token_budget,
        chunk_token_budget=chunk_token_budget,
        gateway=gateway,
        max_fold_depth=max_fold_depth,
    )


def rank_relevance(artifacts: Sequence[Any], query: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Score context artifacts by governance relevance.

    Failures, policy signals, state-changing actions, and evidence references
    outrank routine read-only or heartbeat-style trace entries.
    """
    query_terms = set((query or "").lower().split())
    ranked: List[Dict[str, Any]] = []

    for index, artifact in enumerate(artifacts):
        event = _normalize_event(artifact, index)
        text = event["text"].lower()
        score = 0

        for keyword in GOVERNANCE_KEYWORDS:
            if keyword in text:
                score += 4

        if _extract_evidence_ref(event):
            score += 5
        if _matches_any(text, STATE_CHANGE_KEYWORDS):
            score += 6
        if _matches_any(text, FAILURE_KEYWORDS):
            score += 6
        if _matches_any(text, POLICY_KEYWORDS):
            score += 6
        if query_terms and any(term in text for term in query_terms):
            score += 3

        score += min(index, 10) / 100
        event["relevance_score"] = round(score, 2)
        ranked.append(event)

    return sorted(ranked, key=lambda item: item["relevance_score"], reverse=True)


def _fold_events(
    events: Sequence[Dict[str, Any]],
    *,
    metadata: Dict[str, Any],
    token_budget: int,
    chunk_token_budget: int,
    gateway: Optional[Any],
    depth: int,
    max_fold_depth: int,
) -> Summary:
    text = _events_to_text(events)
    token_count = estimate_tokens(text)

    if token_count <= token_budget or depth >= max_fold_depth:
        return {
            "summary": _summarize_text(text, metadata, token_budget, gateway),
            "fold_depth": depth,
        }

    chunks = _chunk_events(events, chunk_token_budget)
    chunk_summaries = [
        _summarize_text(_events_to_text(chunk), metadata, chunk_token_budget, gateway)
        for chunk in chunks
    ]
    merged_events = [
        _normalize_event({"event": summary, "fold_level": depth}, index)
        for index, summary in enumerate(chunk_summaries)
    ]

    return _fold_events(
        merged_events,
        metadata=metadata,
        token_budget=token_budget,
        chunk_token_budget=chunk_token_budget,
        gateway=gateway,
        depth=depth + 1,
        max_fold_depth=max_fold_depth,
    )


def _build_structured_summary(
    events: Sequence[Dict[str, Any]],
    *,
    folded_text: str,
    metadata: Dict[str, Any],
    fold_depth: int,
    token_budget: int,
) -> Summary:
    key_events = _format_events(events[:8])
    state_changes = _format_events(
        event for event in events if _matches_any(event["text"].lower(), STATE_CHANGE_KEYWORDS)
    )
    failures = _format_events(
        event for event in events if _matches_any(event["text"].lower(), FAILURE_KEYWORDS)
    )
    policy_signals = _format_events(
        event for event in events if _matches_any(event["text"].lower(), POLICY_KEYWORDS)
    )
    evidence_refs = _unique(
        ref for event in events for ref in [_extract_evidence_ref(event)] if ref
    )
    unresolved_risks = _derive_unresolved_risks(failures, policy_signals)

    summary = {
        "summary": _trim_text(folded_text, token_budget),
        "key_events": key_events,
        "state_changes": state_changes[:6],
        "failures": failures[:6],
        "policy_signals": policy_signals[:6],
        "evidence_refs": evidence_refs[:10],
        "unresolved_risks": unresolved_risks,
        "next_safe_action": _next_safe_action(failures, policy_signals, state_changes),
        "token_count": 0,
        "fold_depth": fold_depth,
        "metadata": metadata,
    }
    summary["token_count"] = estimate_tokens(summary)

    if summary["token_count"] > token_budget:
        summary["summary"] = _trim_text(summary["summary"], max(80, token_budget // 3))
        summary["key_events"] = summary["key_events"][:4]
        summary["state_changes"] = summary["state_changes"][:3]
        summary["failures"] = summary["failures"][:3]
        summary["policy_signals"] = summary["policy_signals"][:3]
        summary["evidence_refs"] = summary["evidence_refs"][:5]
        summary["token_count"] = estimate_tokens(summary)

    while summary["token_count"] > token_budget and len(summary["key_events"]) > 1:
        summary["key_events"].pop()
        summary["token_count"] = estimate_tokens(summary)

    while summary["token_count"] > token_budget and len(summary["evidence_refs"]) > 3:
        summary["evidence_refs"].pop()
        summary["token_count"] = estimate_tokens(summary)

    if summary["token_count"] > token_budget:
        summary["summary"] = _trim_text(summary["summary"], 40)
        summary["next_safe_action"] = _trim_text(summary["next_safe_action"], 20)
        summary["unresolved_risks"] = [_trim_text(risk, 20) for risk in summary["unresolved_risks"][:2]]
        summary["token_count"] = estimate_tokens(summary)

    return summary


def _summarize_text(
    text: str,
    metadata: Dict[str, Any],
    target_tokens: int,
    gateway: Optional[Any],
) -> str:
    summarizer = gateway or LLMGateway()
    if hasattr(summarizer, "summarize"):
        result = summarizer.summarize(text, metadata=metadata, target_tokens=target_tokens)
    else:
        result = summarizer(text, metadata=metadata, target_tokens=target_tokens)

    if isinstance(result, dict):
        return str(result.get("summary") or "")
    return str(result)


def _chunk_events(events: Sequence[Dict[str, Any]], chunk_token_budget: int) -> List[List[Dict[str, Any]]]:
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_tokens = 0

    for event in events:
        event_tokens = estimate_tokens(event["text"])
        if current and current_tokens + event_tokens > chunk_token_budget:
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append(event)
        current_tokens += event_tokens

    if current:
        chunks.append(current)

    return chunks


def _normalize_event(event: Any, index: int) -> Dict[str, Any]:
    if isinstance(event, dict):
        normalized = dict(event)
        text = _event_text(normalized)
    else:
        normalized = {"event": event}
        text = _to_text(event)

    normalized.setdefault("index", index)
    normalized["text"] = text
    return normalized


def _event_text(event: Dict[str, Any]) -> str:
    preferred_keys = (
        "timestamp",
        "workflow_id",
        "branch_id",
        "agent_id",
        "owner",
        "event",
        "action",
        "tool",
        "status",
        "message",
        "error",
        "policy_result",
        "evidence_ref",
        "trace_id",
    )
    parts = []
    for key in preferred_keys:
        if key in event and event[key] is not None:
            parts.append(f"{key}={event[key]}")

    if not parts:
        return _to_text(event)
    return " ".join(parts)


def _events_to_text(events: Sequence[Dict[str, Any]]) -> str:
    return "\n".join(event["text"] for event in events)


def _format_events(events: Iterable[Dict[str, Any]]) -> List[str]:
    formatted = []
    for event in events:
        formatted.append(_compact_event(event))
    return _unique(formatted)


def _compact_event(event: Dict[str, Any]) -> str:
    keys = ("action", "event", "status", "policy_result", "error", "tool", "trace_id")
    parts = []
    for key in keys:
        value = event.get(key)
        if value:
            parts.append(f"{key}={value}")

    if not parts:
        parts.append(event["text"])

    return _trim_text(" ".join(parts), 32)


def _derive_unresolved_risks(failures: List[str], policy_signals: List[str]) -> List[str]:
    risks = []
    if failures:
        risks.append("Failure signals require operator review before autonomous resume.")
    if policy_signals:
        risks.append("Policy or approval signals require verification before state-changing actions.")
    if not risks:
        risks.append("No unresolved governance risk detected in compressed trace.")
    return risks


def _next_safe_action(
    failures: List[str],
    policy_signals: List[str],
    state_changes: List[str],
) -> str:
    if policy_signals:
        return "Pause workflow and request operator approval with the preserved policy evidence."
    if failures and state_changes:
        return "Hold further writes and replay from the last safe checkpoint in validation mode."
    if failures:
        return "Investigate failure signals before resuming autonomous execution."
    return "Continue workflow under the current autonomy mode."


def _extract_evidence_ref(event: Dict[str, Any]) -> Optional[str]:
    for key in ("evidence_ref", "evidence_id", "trace_id", "context_hash"):
        value = event.get(key)
        if value:
            return str(value)
    return None


def _matches_any(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _trim_text(text: str, target_tokens: int) -> str:
    max_chars = max(20, target_tokens * 4)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    unique_values = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        return str(value)
