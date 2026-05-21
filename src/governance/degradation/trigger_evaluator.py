"""
AWCP — Degradation Trigger Evaluator
=======================================
Scores and combines multi-signal triggers to determine
whether a degradation level change is warranted.

DS-1 Week 3 implementation: Failure Budget Modeling.

Five signal types are evaluated:
  - failure_count       — recent failed write attempts in the current window
  - stale_context       — boolean from context hash comparison (DS-3)
  - policy_violations   — count of OPA policy denials in current window
  - latency_p99         — observed p99 latency compared to baseline
  - disagreement_score  — inter-agent consistency measure (0.0–1.0)

Central defaults apply to all workflows. Individual workflows can
override any threshold or weight through an override ladder.

Returns a DegradationDecision with:
  - recommended autonomy level
  - composite risk score
  - per-signal breakdown
  - whether the failure budget is breached

References:
  - Agent-Workforce-Control-Plane-Magazine.html §02 Scenario A (Graceful
    Degradation), §04 Context Engineering, §08 Degradation Policy Engine
  - README.md → DS-1 Week 3
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence

from src.common.models import AutonomyMode


# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

class DegradationLevel(int, Enum):
    """Maps to the 5-step degradation ladder in the magazine."""

    NONE = 0          # Full autonomy
    TRACE_SPIKE = 1   # Increase trace sampling depth
    TIGHTEN = 2       # Tighten retry and concurrency limits
    SAFER_PROFILE = 3 # Switch to safer model / profile
    RECOMMEND_ONLY = 4  # Recommendation-only mode
    HARD_STOP = 5     # Hard stop — operator escalation


AUTONOMY_MAP: dict[DegradationLevel, AutonomyMode] = {
    DegradationLevel.NONE: AutonomyMode.FULL,
    DegradationLevel.TRACE_SPIKE: AutonomyMode.FULL,
    DegradationLevel.TIGHTEN: AutonomyMode.CONSERVATIVE,
    DegradationLevel.SAFER_PROFILE: AutonomyMode.CONSERVATIVE,
    DegradationLevel.RECOMMEND_ONLY: AutonomyMode.RECOMMENDATION_ONLY,
    DegradationLevel.HARD_STOP: AutonomyMode.HARD_STOP,
}


# ---------------------------------------------------------------------------
# Central default thresholds (overridable per workflow)
# ---------------------------------------------------------------------------

@dataclass
class FailureBudgetThresholds:
    """Central default thresholds for the five trigger signals.

    Each threshold defines the point at which that signal is considered
    'breached'.  The ``weights`` dictionary controls how much each signal
    contributes to the composite risk score (must sum to 1.0).

    Workflow-specific overrides replace individual fields while leaving
    the rest at their central defaults.
    """

    # --- absolute breach thresholds ---
    max_failure_count: int = 3
    max_policy_violations: int = 2
    latency_baseline_ms: float = 800.0
    latency_breach_ratio: float = 2.0
    disagreement_threshold: float = 0.6

    # --- sliding window ---
    window_seconds: int = 300          # 5-minute evaluation window

    # --- signal weights (must sum to 1.0) ---
    weight_failure: float = 0.30
    weight_stale_context: float = 0.20
    weight_policy_violations: float = 0.20
    weight_latency: float = 0.15
    weight_disagreement: float = 0.15

    # --- degradation ladder cutpoints ---
    level_1_threshold: float = 0.25    # → TRACE_SPIKE
    level_2_threshold: float = 0.40    # → TIGHTEN
    level_3_threshold: float = 0.55    # → SAFER_PROFILE
    level_4_threshold: float = 0.75    # → RECOMMEND_ONLY
    level_5_threshold: float = 0.90    # → HARD_STOP

    def validate(self) -> None:
        """Raise if weights don't sum close to 1.0."""
        total = (
            self.weight_failure
            + self.weight_stale_context
            + self.weight_policy_violations
            + self.weight_latency
            + self.weight_disagreement
        )
        if not math.isclose(total, 1.0, abs_tol=0.01):
            raise ValueError(
                f"Signal weights must sum to 1.0 (got {total:.4f})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_failure_count": self.max_failure_count,
            "max_policy_violations": self.max_policy_violations,
            "latency_baseline_ms": self.latency_baseline_ms,
            "latency_breach_ratio": self.latency_breach_ratio,
            "disagreement_threshold": self.disagreement_threshold,
            "window_seconds": self.window_seconds,
            "weight_failure": self.weight_failure,
            "weight_stale_context": self.weight_stale_context,
            "weight_policy_violations": self.weight_policy_violations,
            "weight_latency": self.weight_latency,
            "weight_disagreement": self.weight_disagreement,
            "level_1_threshold": self.level_1_threshold,
            "level_2_threshold": self.level_2_threshold,
            "level_3_threshold": self.level_3_threshold,
            "level_4_threshold": self.level_4_threshold,
            "level_5_threshold": self.level_5_threshold,
        }


# Central defaults — shared by every workflow that has no override.
CENTRAL_DEFAULTS = FailureBudgetThresholds()


# ---------------------------------------------------------------------------
# Signal input
# ---------------------------------------------------------------------------

@dataclass
class TriggerSignals:
    """Raw signal snapshot collected at evaluation time.

    Each field maps to one of the five trigger types.  If a signal is
    unavailable, its value should be left at the safe default so the
    evaluator can still produce a composite score.
    """

    failure_count: int = 0
    stale_context: bool = False
    policy_violations: int = 0
    latency_p99_ms: float = 0.0
    disagreement_score: float = 0.0

    # Optional audit metadata
    workflow_id: str = ""
    branch_id: str = ""
    evaluation_window_seconds: int = 300
    collected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_count": self.failure_count,
            "stale_context": self.stale_context,
            "policy_violations": self.policy_violations,
            "latency_p99_ms": self.latency_p99_ms,
            "disagreement_score": self.disagreement_score,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "evaluation_window_seconds": self.evaluation_window_seconds,
            "collected_at": self.collected_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Per-signal score breakdown
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalScore:
    """Individual signal contribution to the composite risk score."""

    name: str
    raw_value: Any
    normalized: float     # 0.0 – 1.0
    weight: float
    weighted: float       # normalized * weight
    breached: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw_value": self.raw_value,
            "normalized": round(self.normalized, 6),
            "weight": round(self.weight, 6),
            "weighted": round(self.weighted, 6),
            "breached": self.breached,
        }


# ---------------------------------------------------------------------------
# Degradation decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DegradationDecision:
    """The output of the trigger evaluator.

    Downstream consumers (Degradation Engine, Workflow Engine, UI) read
    this to decide whether to change the workflow's autonomy mode.
    """

    workflow_id: str
    branch_id: str
    composite_score: float            # 0.0 – 1.0
    recommended_level: DegradationLevel
    recommended_autonomy: AutonomyMode
    current_level: DegradationLevel
    level_changed: bool
    budget_breached: bool
    signals: list[SignalScore]
    thresholds_used: FailureBudgetThresholds
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def signal_breakdown(self) -> dict[str, dict[str, Any]]:
        return {signal.name: signal.to_dict() for signal in self.signals}

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "composite_score": round(self.composite_score, 6),
            "recommended_level": self.recommended_level.value,
            "recommended_autonomy": self.recommended_autonomy.value,
            "current_level": self.current_level.value,
            "level_changed": self.level_changed,
            "budget_breached": self.budget_breached,
            "signals": [signal.to_dict() for signal in self.signals],
            "thresholds_used": self.thresholds_used.to_dict(),
            "evaluated_at": self.evaluated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Override ladder registry
# ---------------------------------------------------------------------------

class OverrideLadder:
    """Manages workflow-specific threshold overrides.

    The override ladder lets individual workflows customize any subset of
    the central default thresholds. Unset fields fall back to the central
    defaults.  This implements the "central defaults with workflow-specific
    override ladders" requirement from the magazine and README.
    """

    def __init__(self) -> None:
        self._overrides: dict[str, dict[str, Any]] = {}

    def set_override(
        self,
        workflow_id: str,
        **overrides: Any,
    ) -> None:
        """Register threshold overrides for a specific workflow."""
        self._overrides[workflow_id] = {
            **self._overrides.get(workflow_id, {}),
            **overrides,
        }

    def remove_override(self, workflow_id: str) -> None:
        """Remove all overrides for a workflow."""
        self._overrides.pop(workflow_id, None)

    def get_thresholds(self, workflow_id: str) -> FailureBudgetThresholds:
        """Return merged thresholds: central defaults + workflow overrides."""
        overrides = self._overrides.get(workflow_id, {})
        if not overrides:
            return CENTRAL_DEFAULTS

        merged_values = {**CENTRAL_DEFAULTS.to_dict(), **overrides}
        thresholds = FailureBudgetThresholds(**{
            key: value
            for key, value in merged_values.items()
            if hasattr(CENTRAL_DEFAULTS, key)
        })
        thresholds.validate()
        return thresholds

    def has_override(self, workflow_id: str) -> bool:
        return workflow_id in self._overrides

    def list_overrides(self) -> dict[str, dict[str, Any]]:
        return dict(self._overrides)


# ---------------------------------------------------------------------------
# Trigger Evaluator — the main entry point
# ---------------------------------------------------------------------------

class TriggerEvaluator:
    """Evaluates multi-signal triggers and recommends degradation level.

    This is the DS-1 Week 3 core implementation.  It scores five signal
    types, applies configurable weights, checks against threshold
    ladders, and produces a ``DegradationDecision``.

    Usage::

        evaluator = TriggerEvaluator()
        # Optional: set workflow-specific overrides
        evaluator.override_ladder.set_override(
            "wf-001", max_failure_count=5, weight_failure=0.40
        )
        decision = evaluator.evaluate(signals, current_level=DegradationLevel.NONE)
    """

    def __init__(
        self,
        override_ladder: Optional[OverrideLadder] = None,
    ) -> None:
        self.override_ladder = override_ladder or OverrideLadder()

    def evaluate(
        self,
        signals: TriggerSignals,
        *,
        current_level: DegradationLevel = DegradationLevel.NONE,
    ) -> DegradationDecision:
        """Score all five signals and recommend a degradation level.

        Parameters
        ----------
        signals:
            A snapshot of the five trigger signals for one workflow branch.
        current_level:
            The branch's current degradation level.  The evaluator will
            never recommend going *down* — that requires an explicit
            operator reset via the Degradation Engine.
        """
        thresholds = self.override_ladder.get_thresholds(signals.workflow_id)

        scored = self._score_all_signals(signals, thresholds)
        composite = sum(signal.weighted for signal in scored)
        composite = max(0.0, min(1.0, composite))

        budget_breached = self._is_budget_breached(scored)
        recommended = self._level_from_score(composite, thresholds)

        # Never downgrade automatically — only an operator can reduce level
        if recommended.value < current_level.value:
            recommended = current_level

        return DegradationDecision(
            workflow_id=signals.workflow_id,
            branch_id=signals.branch_id,
            composite_score=composite,
            recommended_level=recommended,
            recommended_autonomy=AUTONOMY_MAP[recommended],
            current_level=current_level,
            level_changed=recommended != current_level,
            budget_breached=budget_breached,
            signals=scored,
            thresholds_used=thresholds,
        )

    def evaluate_batch(
        self,
        signal_batch: Sequence[TriggerSignals],
        *,
        current_levels: Optional[Mapping[str, DegradationLevel]] = None,
    ) -> list[DegradationDecision]:
        """Evaluate multiple workflow branches in one pass."""
        levels = current_levels or {}
        return [
            self.evaluate(
                signals,
                current_level=levels.get(
                    signals.workflow_id, DegradationLevel.NONE
                ),
            )
            for signals in signal_batch
        ]

    # ------------------------------------------------------------------
    # Signal scoring
    # ------------------------------------------------------------------

    def _score_all_signals(
        self,
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> list[SignalScore]:
        """Normalize each raw signal to [0, 1] and apply its weight."""
        return [
            self._score_failure_count(signals, thresholds),
            self._score_stale_context(signals, thresholds),
            self._score_policy_violations(signals, thresholds),
            self._score_latency(signals, thresholds),
            self._score_disagreement(signals, thresholds),
        ]

    @staticmethod
    def _score_failure_count(
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> SignalScore:
        """Normalize failure count against the budget limit.

        Uses a soft sigmoid-like curve so the score rises smoothly as
        failures approach the budget, rather than a hard 0/1 cliff.
        """
        budget = max(1, thresholds.max_failure_count)
        ratio = signals.failure_count / budget
        normalized = min(1.0, _soft_step(ratio))
        breached = signals.failure_count >= thresholds.max_failure_count
        return SignalScore(
            name="failure_count",
            raw_value=signals.failure_count,
            normalized=normalized,
            weight=thresholds.weight_failure,
            weighted=normalized * thresholds.weight_failure,
            breached=breached,
        )

    @staticmethod
    def _score_stale_context(
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> SignalScore:
        """Binary signal: stale context is either present or not."""
        normalized = 1.0 if signals.stale_context else 0.0
        return SignalScore(
            name="stale_context",
            raw_value=signals.stale_context,
            normalized=normalized,
            weight=thresholds.weight_stale_context,
            weighted=normalized * thresholds.weight_stale_context,
            breached=signals.stale_context,
        )

    @staticmethod
    def _score_policy_violations(
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> SignalScore:
        """Normalize policy violations against the max allowed."""
        limit = max(1, thresholds.max_policy_violations)
        ratio = signals.policy_violations / limit
        normalized = min(1.0, _soft_step(ratio))
        breached = signals.policy_violations >= thresholds.max_policy_violations
        return SignalScore(
            name="policy_violations",
            raw_value=signals.policy_violations,
            normalized=normalized,
            weight=thresholds.weight_policy_violations,
            weighted=normalized * thresholds.weight_policy_violations,
            breached=breached,
        )

    @staticmethod
    def _score_latency(
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> SignalScore:
        """Score latency as a ratio against the baseline × breach ratio.

        If p99 ≤ baseline, the score is 0.  If p99 ≥ baseline × breach_ratio,
        the score is 1.0.  In between, the score rises linearly.
        """
        baseline = max(1.0, thresholds.latency_baseline_ms)
        ceiling = baseline * thresholds.latency_breach_ratio
        if signals.latency_p99_ms <= baseline:
            normalized = 0.0
        elif signals.latency_p99_ms >= ceiling:
            normalized = 1.0
        else:
            normalized = (signals.latency_p99_ms - baseline) / (ceiling - baseline)

        breached = signals.latency_p99_ms >= ceiling
        return SignalScore(
            name="latency_p99",
            raw_value=signals.latency_p99_ms,
            normalized=normalized,
            weight=thresholds.weight_latency,
            weighted=normalized * thresholds.weight_latency,
            breached=breached,
        )

    @staticmethod
    def _score_disagreement(
        signals: TriggerSignals,
        thresholds: FailureBudgetThresholds,
    ) -> SignalScore:
        """Score inter-agent disagreement (already 0–1 by convention)."""
        clamped = max(0.0, min(1.0, signals.disagreement_score))
        breached = clamped >= thresholds.disagreement_threshold
        return SignalScore(
            name="disagreement",
            raw_value=signals.disagreement_score,
            normalized=clamped,
            weight=thresholds.weight_disagreement,
            weighted=clamped * thresholds.weight_disagreement,
            breached=breached,
        )

    # ------------------------------------------------------------------
    # Level mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _level_from_score(
        composite: float,
        thresholds: FailureBudgetThresholds,
    ) -> DegradationLevel:
        """Map a composite risk score to a degradation level."""
        if composite >= thresholds.level_5_threshold:
            return DegradationLevel.HARD_STOP
        if composite >= thresholds.level_4_threshold:
            return DegradationLevel.RECOMMEND_ONLY
        if composite >= thresholds.level_3_threshold:
            return DegradationLevel.SAFER_PROFILE
        if composite >= thresholds.level_2_threshold:
            return DegradationLevel.TIGHTEN
        if composite >= thresholds.level_1_threshold:
            return DegradationLevel.TRACE_SPIKE
        return DegradationLevel.NONE

    @staticmethod
    def _is_budget_breached(scored: Sequence[SignalScore]) -> bool:
        """Return True if any individual signal has breached its threshold."""
        return any(signal.breached for signal in scored)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _soft_step(ratio: float) -> float:
    """Smooth step function: rises slowly near 0, steeply near 1.

    Maps a ratio in [0, ∞) to a score in [0, 1) using a sigmoid-like
    curve.  This avoids hard cliffs and produces more nuanced scoring.
    """
    if ratio <= 0.0:
        return 0.0
    # Logistic-shaped curve: approaches 1.0 as ratio → ∞
    return ratio ** 1.5 / (1.0 + ratio ** 1.5)


def evaluate_triggers(
    signals: TriggerSignals,
    *,
    current_level: DegradationLevel = DegradationLevel.NONE,
    override_ladder: Optional[OverrideLadder] = None,
) -> DegradationDecision:
    """Convenience function for one-shot evaluation without managing state."""
    evaluator = TriggerEvaluator(override_ladder=override_ladder)
    return evaluator.evaluate(signals, current_level=current_level)
