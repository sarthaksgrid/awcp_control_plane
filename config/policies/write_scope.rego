# ============================================================
# AWCP — OPA Rego: Write Scope Policy
# ============================================================
# Evaluates whether a tool call falls within the agent's
# declared write scopes. Denies if scope is undeclared.
#
# Input:  { agent_id, tool_name, action_class, write_scopes }
# Output: { "allow": true/false, "reason": "..." }
# ============================================================
