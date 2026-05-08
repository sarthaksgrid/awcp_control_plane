# ============================================================
# AWCP — OPA Rego: Quarantine Policy
# ============================================================
# Blocks write-capable work for agents missing required
# control hooks (telemetry, feature flags, policy callbacks).
#
# Input:  { agent_id, hooks_status: { telemetry, flags, policy } }
# Output: { "quarantined": true/false, "missing_hooks": [...] }
# ============================================================
