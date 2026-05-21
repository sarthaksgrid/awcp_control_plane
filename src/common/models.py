from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AutonomyMode(str, Enum):
    FULL = "FULL"
    CONSERVATIVE = "CONSERVATIVE"
    RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
    HARD_STOP = "HARD_STOP"

class WriteScope(BaseModel):
    system: str
    action_class: str
    resource_id: Optional[str] = None

class AgentIdentity(BaseModel):
    agent_id: str
    owner: str
    team: str
    runtime: str
    risk_tier: RiskTier = RiskTier.MEDIUM
    declared_scopes: List[WriteScope] = Field(default_factory=list)
    feature_flags: Dict[str, Any] = Field(default_factory=dict)

class WorkflowState(BaseModel):
    workflow_id: str
    branch_id: str
    step_number: int
    autonomy_mode: AutonomyMode = AutonomyMode.FULL
    degradation_level: int = 0
    start_time: datetime = Field(default_factory=datetime.now)
    last_checkpoint: Optional[str] = None

class EvidenceEntry(BaseModel):
    entry_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    actor_id: str
    action: str
    context_hash: str
    outcome: str
    policy_ref: Optional[str] = None

class GoverningSliceSchema(BaseModel):
    """
    Pydantic schema for the minimum governance state.

    This is the API / serialization schema. The runtime dataclass used by
    ContextGraphManager.assemble_context() lives in
    src.orchestration.context_graph.context_manager.GoverningSlice.
    Target: 4K - 16K tokens.
    """
    identity: AgentIdentity
    state: WorkflowState
    current_tool_plan: Optional[str] = None
    recent_history: List[Dict[str, Any]] = Field(default_factory=list)
    active_evidence: List[EvidenceEntry] = Field(default_factory=list)
    token_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ToolCallRequest(BaseModel):
    tool_id: str
    name: str
    arguments: Dict[str, Any]
    risk_tier: RiskTier
    workflow_id: str
    branch_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
