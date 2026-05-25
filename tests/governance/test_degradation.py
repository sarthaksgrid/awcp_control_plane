"""Tests for the Degradation Policy Engine and trigger evaluation."""

from src.common.models import AutonomyMode, RiskTier
from src.execution.safer_profiles.profile_manager import (
    ProfileName,
    SaferProfileManager,
)
from src.governance.degradation.degradation_engine import DegradationEngine
from src.governance.degradation.trigger_evaluator import (
    DegradationLevel,
    TriggerSignals,
)


def test_failure_budget_breach_forces_conservative_mode() -> None:
    engine = DegradationEngine()
    signals = TriggerSignals(
        workflow_id="wf-degrade-1",
        branch_id="main",
        failure_count=3,
    )

    transition = engine.evaluate_and_apply(signals)
    state = engine.get_degradation_state("wf-degrade-1", "main")
    profile = engine.profile_manager.get_active_profile("wf-degrade-1", "main")

    assert transition.from_mode is AutonomyMode.FULL
    assert transition.to_mode is AutonomyMode.CONSERVATIVE
    assert transition.budget_breached is True
    assert state.autonomy_mode is AutonomyMode.CONSERVATIVE
    assert profile.name is ProfileName.CONSERVATIVE
    assert profile.allow_write_tools is False


def test_progressive_ladder_moves_to_recommendation_only() -> None:
    engine = DegradationEngine()
    engine.override_ladder_for_workflow(
        "wf-degrade-2",
        level_4_threshold=0.65,
        level_5_threshold=0.95,
    )
    engine.evaluate_and_apply(
        TriggerSignals(
            workflow_id="wf-degrade-2",
            branch_id="main",
            failure_count=3,
        )
    )

    transition = engine.evaluate_and_apply(
        TriggerSignals(
            workflow_id="wf-degrade-2",
            branch_id="main",
            failure_count=3,
            stale_context=True,
            policy_violations=2,
            latency_p99_ms=1600,
            disagreement_score=0.6,
        )
    )
    write_permission = engine.profile_manager.check_tool_permission(
        "wf-degrade-2",
        "main",
        tool_name="billing.refund",
        risk_tier=RiskTier.HIGH,
        write_capable=True,
        tool_class="write",
    )
    approved_permission = engine.profile_manager.check_tool_permission(
        "wf-degrade-2",
        "main",
        tool_name="billing.refund",
        risk_tier=RiskTier.HIGH,
        write_capable=True,
        tool_class="write",
        approval_token_valid=True,
    )

    assert transition.from_mode is AutonomyMode.CONSERVATIVE
    assert transition.to_mode is AutonomyMode.RECOMMENDATION_ONLY
    assert transition.to_level is DegradationLevel.RECOMMEND_ONLY
    assert write_permission.allowed is False
    assert write_permission.requires_human_approval is True
    assert approved_permission.allowed is True


def test_hard_stop_is_terminal_until_operator_reset() -> None:
    engine = DegradationEngine()
    hard_stop = engine.evaluate_and_apply(
        TriggerSignals(
            workflow_id="wf-degrade-3",
            branch_id="main",
            failure_count=100,
            stale_context=True,
            policy_violations=50,
            latency_p99_ms=5000,
            disagreement_score=1.0,
        )
    )
    low_risk_after_stop = engine.evaluate_and_apply(
        TriggerSignals(workflow_id="wf-degrade-3", branch_id="main")
    )
    read_permission = engine.profile_manager.check_tool_permission(
        "wf-degrade-3",
        "main",
        tool_name="invoice.lookup",
        risk_tier=RiskTier.LOW,
        write_capable=False,
        tool_class="read",
    )

    assert hard_stop.to_mode is AutonomyMode.HARD_STOP
    assert low_risk_after_stop.to_mode is AutonomyMode.HARD_STOP
    assert read_permission.allowed is False
    assert read_permission.requires_human_approval is True

    reset_state = engine.reset_degradation("wf-degrade-3", "main")

    assert reset_state.autonomy_mode is AutonomyMode.FULL
    assert reset_state.level is DegradationLevel.NONE


def test_safer_profile_manager_enforces_conservative_read_only_mode() -> None:
    manager = SaferProfileManager()
    manager.apply_profile(
        "wf-profile-1",
        "main",
        AutonomyMode.CONSERVATIVE,
        reason="failure budget breach",
    )

    read_permission = manager.check_tool_permission(
        "wf-profile-1",
        "main",
        tool_name="invoice.lookup",
        risk_tier=RiskTier.LOW,
        write_capable=False,
        tool_class="read",
    )
    write_permission = manager.check_tool_permission(
        "wf-profile-1",
        "main",
        tool_name="billing.refund",
        risk_tier=RiskTier.LOW,
        write_capable=True,
        tool_class="write",
    )

    assert read_permission.allowed is True
    assert write_permission.allowed is False
    assert write_permission.requires_human_approval is True
