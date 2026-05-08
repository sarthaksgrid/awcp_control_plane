"""
AWCP — Shared Domain Models
============================
Pydantic models shared across all layers:

  - AgentIdentity       — owner, runtime, declared write scopes, flags
  - WorkflowState       — branch id, checkpoint, autonomy mode, degradation level
  - ApprovalToken       — scoped token with expiry, branch binding, action class
  - PolicyDecision      — allow / deny / escalate with evidence references
  - EvidenceEntry       — ledger row: actor, action, context hash, outcome
  - DegradationState    — current level, trigger signals, override ladder
  - ToolCallRequest     — tool name, args, risk tier, workflow binding
"""
