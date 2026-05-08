# ============================================================
# AWCP — OPA Rego: Risk Tier Policy
# ============================================================
# Evaluates a tool call's risk score against the approval
# threshold. Returns "escalate" if score exceeds limit.
#
# Input:  { tool_name, risk_score, threshold, workflow_state }
# Output: { "decision": "allow"|"escalate"|"deny", "reason": "..." }
# ============================================================
