"""
AWCP — Safer Profile Manager
================================
Manages model and tool permissions during degradation.

Week 3 DS-2 implementation:
  - Define executable profiles for each autonomy mode
  - Disable write-capable tools as autonomy drops
  - Track which safer profile is active per workflow branch
  - Provide permission checks for tool execution paths
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from src.common.models import AutonomyMode, RiskTier


class ProfileName(str, Enum):
    FULL_AUTONOMY = "FULL_AUTONOMY"
    CONSERVATIVE = "CONSERVATIVE"
    RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
    READ_ONLY = "READ_ONLY"
    HARD_STOP = "HARD_STOP"


RISK_ORDER: dict[RiskTier, int] = {
    RiskTier.LOW: 1,
    RiskTier.MEDIUM: 2,
    RiskTier.HIGH: 3,
    RiskTier.CRITICAL: 4,
}


@dataclass(frozen=True)
class SaferProfile:
    """Execution constraints attached to one autonomy mode."""

    name: ProfileName
    autonomy_mode: AutonomyMode
    allow_read_tools: bool
    allow_write_tools: bool
    require_human_approval_for_writes: bool
    max_write_risk_tier: RiskTier | None
    retry_limit: int
    concurrency_limit: int
    model_temperature: float
    trace_verbosity: str
    disabled_tool_classes: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "autonomy_mode": self.autonomy_mode.value,
            "allow_read_tools": self.allow_read_tools,
            "allow_write_tools": self.allow_write_tools,
            "require_human_approval_for_writes": self.require_human_approval_for_writes,
            "max_write_risk_tier": self.max_write_risk_tier.value
            if self.max_write_risk_tier
            else None,
            "retry_limit": self.retry_limit,
            "concurrency_limit": self.concurrency_limit,
            "model_temperature": self.model_temperature,
            "trace_verbosity": self.trace_verbosity,
            "disabled_tool_classes": list(self.disabled_tool_classes),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProfileApplication:
    """Audit record for applying a safer profile to a branch."""

    workflow_id: str
    branch_id: str
    profile: SaferProfile
    reason: str
    applied_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "profile": self.profile.to_dict(),
            "reason": self.reason,
            "applied_at": self.applied_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ToolPermissionDecision:
    """Result of checking whether a tool call is allowed in the active profile."""

    allowed: bool
    profile_name: ProfileName
    autonomy_mode: AutonomyMode
    reason: str
    requires_human_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "profile_name": self.profile_name.value,
            "autonomy_mode": self.autonomy_mode.value,
            "reason": self.reason,
            "requires_human_approval": self.requires_human_approval,
        }


DEFAULT_PROFILES: dict[ProfileName, SaferProfile] = {
    ProfileName.FULL_AUTONOMY: SaferProfile(
        name=ProfileName.FULL_AUTONOMY,
        autonomy_mode=AutonomyMode.FULL,
        allow_read_tools=True,
        allow_write_tools=True,
        require_human_approval_for_writes=False,
        max_write_risk_tier=RiskTier.CRITICAL,
        retry_limit=3,
        concurrency_limit=8,
        model_temperature=0.7,
        trace_verbosity="standard",
        notes="Default mode. Governed writes remain enabled.",
    ),
    ProfileName.CONSERVATIVE: SaferProfile(
        name=ProfileName.CONSERVATIVE,
        autonomy_mode=AutonomyMode.CONSERVATIVE,
        allow_read_tools=True,
        allow_write_tools=False,
        require_human_approval_for_writes=True,
        max_write_risk_tier=RiskTier.LOW,
        retry_limit=1,
        concurrency_limit=2,
        model_temperature=0.2,
        trace_verbosity="high",
        disabled_tool_classes=("write", "deploy", "delete", "payment", "external_mutation"),
        notes="Read-only analysis and low-risk recommendations only.",
    ),
    ProfileName.RECOMMENDATION_ONLY: SaferProfile(
        name=ProfileName.RECOMMENDATION_ONLY,
        autonomy_mode=AutonomyMode.RECOMMENDATION_ONLY,
        allow_read_tools=True,
        allow_write_tools=False,
        require_human_approval_for_writes=True,
        max_write_risk_tier=None,
        retry_limit=0,
        concurrency_limit=1,
        model_temperature=0.1,
        trace_verbosity="full",
        disabled_tool_classes=("write", "deploy", "delete", "payment", "external_mutation"),
        notes="No state-changing tool execution until explicit human approval.",
    ),
    ProfileName.READ_ONLY: SaferProfile(
        name=ProfileName.READ_ONLY,
        autonomy_mode=AutonomyMode.CONSERVATIVE,
        allow_read_tools=True,
        allow_write_tools=False,
        require_human_approval_for_writes=True,
        max_write_risk_tier=None,
        retry_limit=0,
        concurrency_limit=1,
        model_temperature=0.1,
        trace_verbosity="full",
        disabled_tool_classes=("write", "deploy", "delete", "payment", "external_mutation"),
        notes="Observation-only profile used by remediation and replay paths.",
    ),
    ProfileName.HARD_STOP: SaferProfile(
        name=ProfileName.HARD_STOP,
        autonomy_mode=AutonomyMode.HARD_STOP,
        allow_read_tools=False,
        allow_write_tools=False,
        require_human_approval_for_writes=True,
        max_write_risk_tier=None,
        retry_limit=0,
        concurrency_limit=0,
        model_temperature=0.0,
        trace_verbosity="full",
        disabled_tool_classes=("read", "write", "deploy", "delete", "payment", "external_mutation"),
        notes="All execution paused. Operator intervention required.",
    ),
}


PROFILE_BY_AUTONOMY: dict[AutonomyMode, ProfileName] = {
    AutonomyMode.FULL: ProfileName.FULL_AUTONOMY,
    AutonomyMode.CONSERVATIVE: ProfileName.CONSERVATIVE,
    AutonomyMode.RECOMMENDATION_ONLY: ProfileName.RECOMMENDATION_ONLY,
    AutonomyMode.HARD_STOP: ProfileName.HARD_STOP,
}


class SaferProfileManager:
    """Stores and evaluates safer execution profiles per workflow branch."""

    def __init__(
        self,
        profiles: Mapping[ProfileName, SaferProfile] | None = None,
    ) -> None:
        self._profiles = dict(profiles or DEFAULT_PROFILES)
        self._active_profiles: dict[tuple[str, str], ProfileApplication] = {}

    def get_profile(self, profile_name: ProfileName | str) -> SaferProfile:
        name = profile_name if isinstance(profile_name, ProfileName) else ProfileName(str(profile_name))
        return self._profiles[name]

    def profile_for_autonomy(self, autonomy_mode: AutonomyMode | str) -> SaferProfile:
        mode = autonomy_mode if isinstance(autonomy_mode, AutonomyMode) else AutonomyMode(str(autonomy_mode))
        return self.get_profile(PROFILE_BY_AUTONOMY[mode])

    def apply_profile(
        self,
        workflow_id: str,
        branch_id: str,
        autonomy_mode: AutonomyMode | str,
        *,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProfileApplication:
        """Apply the profile corresponding to an autonomy mode."""

        profile = self.profile_for_autonomy(autonomy_mode)
        application = ProfileApplication(
            workflow_id=workflow_id,
            branch_id=branch_id,
            profile=profile,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self._active_profiles[(workflow_id, branch_id)] = application
        return application

    def get_active_profile(
        self,
        workflow_id: str,
        branch_id: str,
    ) -> SaferProfile:
        application = self._active_profiles.get((workflow_id, branch_id))
        if application is None:
            return self.get_profile(ProfileName.FULL_AUTONOMY)
        return application.profile

    def get_profile_application(
        self,
        workflow_id: str,
        branch_id: str,
    ) -> ProfileApplication | None:
        return self._active_profiles.get((workflow_id, branch_id))

    def reset_profile(self, workflow_id: str, branch_id: str) -> None:
        self._active_profiles.pop((workflow_id, branch_id), None)

    def check_tool_permission(
        self,
        workflow_id: str,
        branch_id: str,
        *,
        tool_name: str,
        risk_tier: RiskTier | str = RiskTier.LOW,
        write_capable: bool = False,
        tool_class: str | None = None,
        approval_token_valid: bool = False,
    ) -> ToolPermissionDecision:
        """Return whether a tool is executable under the active profile."""

        profile = self.get_active_profile(workflow_id, branch_id)
        risk = risk_tier if isinstance(risk_tier, RiskTier) else RiskTier(str(risk_tier))
        tool_class = tool_class or ("write" if write_capable else "read")

        if profile.autonomy_mode is AutonomyMode.HARD_STOP:
            return ToolPermissionDecision(
                allowed=False,
                profile_name=profile.name,
                autonomy_mode=profile.autonomy_mode,
                reason="hard stop is active; all execution requires operator intervention",
                requires_human_approval=True,
            )

        if tool_class in profile.disabled_tool_classes:
            if (
                profile.autonomy_mode is AutonomyMode.RECOMMENDATION_ONLY
                and write_capable
                and approval_token_valid
            ):
                return ToolPermissionDecision(
                    allowed=True,
                    profile_name=profile.name,
                    autonomy_mode=profile.autonomy_mode,
                    reason=f"{tool_name} allowed by explicit approval token",
                )
            return ToolPermissionDecision(
                allowed=False,
                profile_name=profile.name,
                autonomy_mode=profile.autonomy_mode,
                reason=f"{tool_class} tools are disabled in {profile.name.value}",
                requires_human_approval=profile.require_human_approval_for_writes and write_capable,
            )

        if not write_capable:
            return ToolPermissionDecision(
                allowed=profile.allow_read_tools,
                profile_name=profile.name,
                autonomy_mode=profile.autonomy_mode,
                reason="read-only tool allowed" if profile.allow_read_tools else "read tools disabled",
            )

        if not profile.allow_write_tools:
            if profile.autonomy_mode is AutonomyMode.RECOMMENDATION_ONLY and approval_token_valid:
                return ToolPermissionDecision(
                    allowed=True,
                    profile_name=profile.name,
                    autonomy_mode=profile.autonomy_mode,
                    reason=f"{tool_name} write allowed by explicit approval token",
                )
            return ToolPermissionDecision(
                allowed=False,
                profile_name=profile.name,
                autonomy_mode=profile.autonomy_mode,
                reason=f"write tools are disabled in {profile.name.value}",
                requires_human_approval=profile.require_human_approval_for_writes,
            )

        if profile.max_write_risk_tier and RISK_ORDER[risk] > RISK_ORDER[profile.max_write_risk_tier]:
            return ToolPermissionDecision(
                allowed=False,
                profile_name=profile.name,
                autonomy_mode=profile.autonomy_mode,
                reason=(
                    f"{tool_name} risk {risk.value} exceeds "
                    f"{profile.name.value} max {profile.max_write_risk_tier.value}"
                ),
                requires_human_approval=profile.require_human_approval_for_writes,
            )

        return ToolPermissionDecision(
            allowed=True,
            profile_name=profile.name,
            autonomy_mode=profile.autonomy_mode,
            reason=f"{tool_name} allowed in {profile.name.value}",
        )
