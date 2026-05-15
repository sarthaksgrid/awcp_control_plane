"""Dummy Data Science hooks for PB-2 integration testing.

Future DS code should replace these functions with real failure-budget,
stale-context, and risk-tier models. PB-2 calls this module at the same points
where those services will be invoked.
"""

from __future__ import annotations

from src.pb2.schemas import AgentEvent, PolicyDecision


def score_agent_event(event: AgentEvent) -> PolicyDecision:
    """Return a deterministic safety decision for a governed agent action."""

    risk_scores = {
        "low": 0.2,
        "medium": 0.45,
        "high": 0.78,
        "critical": 0.94,
    }
    risk_score = risk_scores[event.risk_tier]

    if event.requested_scope not in event.declared_write_scopes:
        return PolicyDecision(
            decision="deny",
            risk_score=0.99,
            reason="Requested write scope is outside the agent's declared boundary.",
            next_safe_action="route_to_quarantine_review",
        )

    if event.risk_tier in {"high", "critical"}:
        return PolicyDecision(
            decision="escalate",
            risk_score=risk_score,
            reason="High-risk state-changing action requires a narrow operator token.",
            requires_approval=True,
            next_safe_action="wait_for_operator_approval",
        )

    return PolicyDecision(
        decision="allow",
        risk_score=risk_score,
        reason="Action is inside declared scope and below approval threshold.",
        next_safe_action="continue",
    )
