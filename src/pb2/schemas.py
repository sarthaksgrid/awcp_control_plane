"""Shared PB-2 request/response models.

These models are intentionally small and stable. They form the contract that
PB-1, DS, UI, and DevOps can integrate against while the implementation moves
from in-memory demo services to Temporal, OPA, Modal, and persistent storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


Decision = Literal["allow", "deny", "escalate"]
RiskTier = Literal["low", "medium", "high", "critical"]
ApprovalStatus = Literal["pending", "approved", "denied", "expired", "consumed"]


def new_id(prefix: str) -> str:
    """Create readable IDs for demos and UI traces."""

    return f"{prefix}-{uuid4().hex[:10]}"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def normalize_utc(value: datetime) -> datetime:
    """Normalize stored timestamps from old local files to aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AgentEvent(BaseModel):
    """Canonical event after PB-1 normalizes an agent runtime signal."""

    workflow_id: str = Field(default_factory=lambda: new_id("wf"))
    branch_id: str = "main"
    agent_id: str = "refund-agent-v1"
    owner: str = "agent-ops"
    action_class: str = "billing.refund"
    tool_name: str = "refund_customer"
    risk_tier: RiskTier = "high"
    declared_write_scopes: list[str] = Field(default_factory=lambda: ["crm.read", "billing.write"])
    requested_scope: str = "billing.write"
    payload: dict[str, Any] = Field(
        default_factory=lambda: {"customer_id": "cus_1042", "amount": 50, "currency": "USD"}
    )
    context_hash: str = "ctx-demo-safe"


class PolicyDecision(BaseModel):
    """Decision shape returned by DS scoring and OPA policy evaluation."""

    decision: Decision
    risk_score: float
    reason: str
    requires_approval: bool = False
    next_safe_action: str = "continue"


class EvidenceEntry(BaseModel):
    """Append-only evidence item used by the UI and replay/recovery flow."""

    id: str = Field(default_factory=lambda: new_id("ev"))
    workflow_id: str
    branch_id: str
    actor: str
    action: str
    policy_result: Decision | str
    context_hash: str
    degradation_state: str = "full"
    replay_trace: dict[str, Any] = Field(default_factory=dict)
    rollback_pointer: str | None = None
    approval_token_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        """Support old local evidence rows written before timezone-aware UTC."""

        return normalize_utc(value)


class ApprovalRequest(BaseModel):
    """High-risk action paused until an operator issues a narrow token."""

    id: str = Field(default_factory=lambda: new_id("apr"))
    workflow_id: str
    branch_id: str
    action_class: str
    requested_scope: str
    risk_tier: RiskTier
    risk_score: float
    status: ApprovalStatus = "pending"
    reason: str
    rollback_pointer: str
    proposed_tool_plan: list[str]
    context_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    token: str | None = None
    operator: str | None = None

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        """Support old local approval rows written before timezone-aware UTC."""

        return normalize_utc(value)


class SandboxRunRequest(BaseModel):
    """CodeAct execution request.

    The local implementation is a safe stub. Future PB-1/DevOps work can swap
    the body for Modal while preserving this call shape.
    """

    workflow_id: str
    branch_id: str = "main"
    code: str = "print('sandbox dry-run complete')"
    artifact: dict[str, Any] = Field(default_factory=dict)


class WorkflowRecord(BaseModel):
    """Current PB-2 view of a governed workflow."""

    workflow_id: str
    branch_id: str
    agent_id: str
    owner: str
    status: str
    autonomy_mode: str
    risk_tier: RiskTier
    policy_decision: Decision | str
    context_hash: str
    idempotency_key: str
    latest_summary: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        """Support old local workflow rows written before timezone-aware UTC."""

        return normalize_utc(value)


class ApprovalAction(BaseModel):
    """Operator action submitted from the React approval queue."""

    operator: str = "operator.demo"
