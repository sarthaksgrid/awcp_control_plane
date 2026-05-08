"""
AWCP — OPA Policy Evaluator
==============================
Evaluates workflow steps and tool-call requests against
Open Policy Agent (OPA) policies.

Responsibilities:
  - Build the OPA input document from WorkflowState + ToolCallRequest
  - Query the OPA server for a policy decision
  - Interpret the result (allow / deny / escalate)
  - Cache decisions for idempotent replays

Policy domains:
  - write_scope_check    — is the requested tool within declared scopes?
  - risk_tier_check      — does the risk score exceed the approval threshold?
  - failure_budget_check — has the workflow breached its failure budget?
  - quarantine_check     — is the agent in quarantine?
"""
