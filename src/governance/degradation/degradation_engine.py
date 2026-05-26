"""
AWCP — Degradation Policy Engine
====================================
Evaluates trigger decisions and progressively reduces agent autonomy.

Week 3 DS-2 implementation:
  - State transition matrix: FULL -> CONSERVATIVE -> RECOMMENDATION_ONLY
    -> HARD_STOP
  - Apply safer profiles when autonomy changes
  - Keep per-workflow branch degradation state
  - Prevent automatic downgrades; only operator reset can restore autonomy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from src.common.models import AutonomyMode
from src.execution.safer_profiles.profile_manager import (
    ProfileApplication,
    SaferProfileManager,
)
from src.governance.degradation.trigger_evaluator import (
    DegradationDecision,
    DegradationLevel,
    OverrideLadder,
    TriggerEvaluator,
    TriggerSignals,
)


AUTONOMY_RANK: dict[AutonomyMode, int] = {
    AutonomyMode.FULL: 0,
    AutonomyMode.CONSERVATIVE: 1,
    AutonomyMode.RECOMMENDATION_ONLY: 2,
    AutonomyMode.HARD_STOP: 3,
}


LEVEL_TO_AUTONOMY: dict[DegradationLevel, AutonomyMode] = {
    DegradationLevel.NONE: AutonomyMode.FULL,
    DegradationLevel.TRACE_SPIKE: AutonomyMode.FULL,
    DegradationLevel.TIGHTEN: AutonomyMode.CONSERVATIVE,
    DegradationLevel.SAFER_PROFILE: AutonomyMode.CONSERVATIVE,
    DegradationLevel.RECOMMEND_ONLY: AutonomyMode.RECOMMENDATION_ONLY,
    DegradationLevel.HARD_STOP: AutonomyMode.HARD_STOP,
}


AUTONOMY_TO_LEVEL: dict[AutonomyMode, DegradationLevel] = {
    AutonomyMode.FULL: DegradationLevel.NONE,
    AutonomyMode.CONSERVATIVE: DegradationLevel.SAFER_PROFILE,
    AutonomyMode.RECOMMENDATION_ONLY: DegradationLevel.RECOMMEND_ONLY,
    AutonomyMode.HARD_STOP: DegradationLevel.HARD_STOP,
}


TRANSITION_MATRIX: dict[AutonomyMode, tuple[AutonomyMode, ...]] = {
    AutonomyMode.FULL: (
        AutonomyMode.FULL,
        AutonomyMode.CONSERVATIVE,
        AutonomyMode.RECOMMENDATION_ONLY,
        AutonomyMode.HARD_STOP,
    ),
    AutonomyMode.CONSERVATIVE: (
        AutonomyMode.CONSERVATIVE,
        AutonomyMode.RECOMMENDATION_ONLY,
        AutonomyMode.HARD_STOP,
    ),
    AutonomyMode.RECOMMENDATION_ONLY: (
        AutonomyMode.RECOMMENDATION_ONLY,
        AutonomyMode.HARD_STOP,
    ),
    AutonomyMode.HARD_STOP: (AutonomyMode.HARD_STOP,),
}


@dataclass(frozen=True)
class DegradationTransition:
    """Audit record for one autonomy transition."""

    workflow_id: str
    branch_id: str
    from_mode: AutonomyMode
    to_mode: AutonomyMode
    from_level: DegradationLevel
    to_level: DegradationLevel
    reason: str
    budget_breached: bool
    profile_application: ProfileApplication
    decision: dict[str, Any] | None = None
    transitioned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def changed(self) -> bool:
        return self.from_mode != self.to_mode

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "from_level": self.from_level.value,
            "to_level": self.to_level.value,
            "changed": self.changed,
            "reason": self.reason,
            "budget_breached": self.budget_breached,
            "profile_application": self.profile_application.to_dict(),
            "decision": self.decision,
            "transitioned_at": self.transitioned_at.isoformat(),
        }


@dataclass
class DegradationState:
    """Current degradation state for a workflow branch."""

    workflow_id: str
    branch_id: str
    autonomy_mode: AutonomyMode = AutonomyMode.FULL
    level: DegradationLevel = DegradationLevel.NONE
    transition_count: int = 0
    last_reason: str = "initial state"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[DegradationTransition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "autonomy_mode": self.autonomy_mode.value,
            "level": self.level.value,
            "transition_count": self.transition_count,
            "last_reason": self.last_reason,
            "updated_at": self.updated_at.isoformat(),
            "history": [transition.to_dict() for transition in self.history],
        }


class DegradationEngine:
    """Applies progressive autonomy reduction using DS-1 trigger decisions."""

    def __init__(
        self,
        *,
        trigger_evaluator: TriggerEvaluator | None = None,
        profile_manager: SaferProfileManager | None = None,
    ) -> None:
        self.trigger_evaluator = trigger_evaluator or TriggerEvaluator()
        self.profile_manager = profile_manager or SaferProfileManager()
        self._states: dict[tuple[str, str], DegradationState] = {}

    @property
    def override_ladder(self) -> OverrideLadder:
        return self.trigger_evaluator.override_ladder

    def evaluate_degradation(
        self,
        signals: TriggerSignals,
    ) -> DegradationDecision:
        """Evaluate DS-1 signals using the current branch degradation level."""

        state = self.get_degradation_state(signals.workflow_id, signals.branch_id)
        return self.trigger_evaluator.evaluate(signals, current_level=state.level)

    def apply_degradation(
        self,
        decision: DegradationDecision,
        *,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DegradationTransition:
        """Apply the progressive autonomy transition for a trigger decision."""

        state = self.get_degradation_state(decision.workflow_id, decision.branch_id)
        target_mode = self._target_mode(decision, state)
        target_mode = self._apply_transition_matrix(state.autonomy_mode, target_mode)
        target_level = max(
            AUTONOMY_TO_LEVEL[target_mode],
            decision.recommended_level,
            key=lambda level: level.value,
        )

        transition_reason = reason or self._reason_from_decision(decision, target_mode)
        profile_application = self.profile_manager.apply_profile(
            decision.workflow_id,
            decision.branch_id,
            target_mode,
            reason=transition_reason,
            metadata={
                "composite_score": decision.composite_score,
                "recommended_level": decision.recommended_level.value,
                "budget_breached": decision.budget_breached,
                **dict(metadata or {}),
            },
        )

        transition = DegradationTransition(
            workflow_id=decision.workflow_id,
            branch_id=decision.branch_id,
            from_mode=state.autonomy_mode,
            to_mode=target_mode,
            from_level=state.level,
            to_level=target_level,
            reason=transition_reason,
            budget_breached=decision.budget_breached,
            profile_application=profile_application,
            decision=decision.to_dict(),
        )

        if transition.changed or target_level != state.level:
            state.transition_count += 1
        state.autonomy_mode = target_mode
        state.level = target_level
        state.last_reason = transition_reason
        state.updated_at = datetime.now(timezone.utc)
        state.history.append(transition)
        return transition

    def evaluate_and_apply(
        self,
        signals: TriggerSignals,
        *,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DegradationTransition:
        """Convenience method for evaluating signals and applying the result."""

        return self.apply_degradation(
            self.evaluate_degradation(signals),
            reason=reason,
            metadata=metadata,
        )

    def get_degradation_state(
        self,
        workflow_id: str,
        branch_id: str,
    ) -> DegradationState:
        """Return existing state or initialize the branch at full autonomy."""

        key = (workflow_id, branch_id)
        if key not in self._states:
            self._states[key] = DegradationState(workflow_id=workflow_id, branch_id=branch_id)
            self.profile_manager.apply_profile(
                workflow_id,
                branch_id,
                AutonomyMode.FULL,
                reason="initial full autonomy",
            )
        return self._states[key]

    def reset_degradation(
        self,
        workflow_id: str,
        branch_id: str,
        *,
        reason: str = "operator reset",
    ) -> DegradationState:
        """Explicit operator reset back to full autonomy."""

        state = self.get_degradation_state(workflow_id, branch_id)
        self.profile_manager.apply_profile(
            workflow_id,
            branch_id,
            AutonomyMode.FULL,
            reason=reason,
        )
        state.autonomy_mode = AutonomyMode.FULL
        state.level = DegradationLevel.NONE
        state.last_reason = reason
        state.updated_at = datetime.now(timezone.utc)
        return state

    def override_ladder_for_workflow(
        self,
        workflow_id: str,
        **overrides: Any,
    ) -> None:
        """Set workflow-specific threshold overrides."""

        self.override_ladder.set_override(workflow_id, **overrides)

    @staticmethod
    def _target_mode(
        decision: DegradationDecision,
        state: DegradationState,
    ) -> AutonomyMode:
        target = LEVEL_TO_AUTONOMY[decision.recommended_level]

        # DS-2 rule: a breached failure budget must enter graceful degradation
        # even if the composite score has not crossed the Conservative cutoff.
        if decision.budget_breached and target is AutonomyMode.FULL:
            target = AutonomyMode.CONSERVATIVE

        if AUTONOMY_RANK[target] < AUTONOMY_RANK[state.autonomy_mode]:
            return state.autonomy_mode
        return target

    @staticmethod
    def _apply_transition_matrix(
        current: AutonomyMode,
        requested: AutonomyMode,
    ) -> AutonomyMode:
        allowed = TRANSITION_MATRIX[current]
        if requested in allowed:
            return requested
        return allowed[-1]

    @staticmethod
    def _reason_from_decision(
        decision: DegradationDecision,
        target_mode: AutonomyMode,
    ) -> str:
        breached = [
            signal.name
            for signal in decision.signals
            if signal.breached
        ]
        if breached:
            return (
                f"autonomy reduced to {target_mode.value}; breached signals: "
                + ", ".join(breached)
            )
        return (
            f"autonomy evaluated as {target_mode.value}; "
            f"composite_score={decision.composite_score:.3f}"
        )


def evaluate_degradation(
    signals: TriggerSignals,
    *,
    engine: DegradationEngine | None = None,
) -> DegradationDecision:
    """One-shot helper mirroring the module-level API in the scaffold."""

    return (engine or DegradationEngine()).evaluate_degradation(signals)


def apply_degradation(
    decision: DegradationDecision,
    *,
    engine: DegradationEngine | None = None,
) -> DegradationTransition:
    """One-shot helper for applying a degradation decision."""

    return (engine or DegradationEngine()).apply_degradation(decision)
