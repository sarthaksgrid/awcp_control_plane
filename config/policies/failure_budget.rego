# ============================================================
# AWCP — OPA Rego: Failure Budget Policy
# ============================================================
# Checks whether a workflow branch has exceeded its failure
# budget, triggering degradation.
#
# Input:  { workflow_id, branch_id, failure_count, budget_limit, window }
# Output: { "breached": true/false, "recommended_level": 1-5 }
# ============================================================
