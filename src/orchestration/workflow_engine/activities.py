"""
AWCP — Temporal Activity Definitions
=======================================
Defines Temporal activities invoked by governed workflows:

  - evaluate_policy()         — call OPA for a policy decision
  - request_approval()        — pause for operator token
  - execute_tool_call()       — run a sandboxed tool action
  - apply_degradation()       — step down autonomy level
  - write_evidence()          — record entry in the evidence ledger
  - check_context_freshness() — validate context hash
  - generate_patch()          — create instrumentation patch
"""
