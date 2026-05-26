"""
AWCP — Degradation Trigger Evaluator
=======================================
Scores and combines multi-signal triggers to determine
whether a degradation level change is warranted.

Signals scored:
  - failure_count       — recent failed write attempts
  - stale_context       — boolean from context hash comparison
  - policy_violations   — count in current window
  - latency_p99         — compared to baseline
  - disagreement_score  — inter-agent consistency measure

Returns a DegradationDecision with recommended level.
"""

# Week 2 DS-3: Stale Context Detection
# This module implements the TriggerEvaluator and DegradationDecision

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from src.orchestration.context_graph.context_hashing import (
    StaleContextDetector,
    StaleContextReport,
)


@dataclass(frozen=True)
class DegradationDecision:
    """
    Trigger evaluation output consumed by the degradation engine.
    """

    should_degrade: bool
    recommended_level: int
    triggers: list[str] = field(default_factory=list)
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class TriggerEvaluator:
    """
    Combines degradation signals and exposes Week 2 DS-3 stale-context checks.
    """

    DEFAULT_STALE_CONTEXT_LEVEL = 2

    def __init__(
        self,
        stale_context_detector: Optional[StaleContextDetector] = None,
        stale_context_level: int = DEFAULT_STALE_CONTEXT_LEVEL,
    ):
        self.stale_context_detector = stale_context_detector or StaleContextDetector()
        self.stale_context_level = stale_context_level

    def evaluate_stale_context(
        self,
        current_context: Any,
        evidence_entries: Optional[Iterable[Any]] = None,
    ) -> StaleContextReport:
        """
        Compare current working memory with the verified ledger timeline.
        """
        return self.stale_context_detector.evaluate(current_context, evidence_entries)

    def evaluate(
        self,
        signals: Optional[dict[str, Any]] = None,
        current_context: Any = None,
        evidence_entries: Optional[Iterable[Any]] = None,
    ) -> DegradationDecision:
        """
        Evaluate available trigger signals.

        When current_context is provided, stale-context detection is computed
        from the evidence ledger and merged into the trigger set.
        """
        trigger_signals = dict(signals or {})
        stale_report = None
        if current_context is not None:
            stale_report = self.evaluate_stale_context(current_context, evidence_entries)
            trigger_signals["stale_context"] = stale_report.is_stale
            trigger_signals["stale_context_report"] = stale_report.as_signal()

        triggers: list[str] = []
        recommended_level = 0

        if trigger_signals.get("stale_context"):
            triggers.append("stale_context")
            recommended_level = max(recommended_level, self.stale_context_level)

        failure_count = int(trigger_signals.get("failure_count") or 0)
        if failure_count >= 3:
            triggers.append("failure_budget")
            recommended_level = max(recommended_level, 1)

        policy_violations = int(trigger_signals.get("policy_violations") or 0)
        if policy_violations:
            triggers.append("policy_violations")
            recommended_level = max(recommended_level, 1)

        reason = ", ".join(triggers) if triggers else "no_degradation_triggered"
        evidence = dict(trigger_signals)
        if stale_report is not None:
            evidence["stale_context_report"] = stale_report.as_signal()

        return DegradationDecision(
            should_degrade=bool(triggers),
            recommended_level=recommended_level,
            triggers=triggers,
            reason=reason,
            evidence=evidence,
        )


def evaluate_stale_context(
    current_context: Any,
    evidence_entries: Optional[Iterable[Any]] = None,
) -> StaleContextReport:
    """
    Convenience function for DS-3 callers that only need stale-context status.
    """
    return TriggerEvaluator().evaluate_stale_context(current_context, evidence_entries)
