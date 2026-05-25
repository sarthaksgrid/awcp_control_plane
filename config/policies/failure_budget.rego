# ============================================================
# AWCP — OPA Rego: Failure Budget Policy
# ============================================================
# Evaluates whether a workflow branch has exceeded its failure
# budget, triggering degradation.
#
# Input:
#   {
#     "workflow_id":        "wf-001",
#     "branch_id":          "branch-main",
#     "failure_count":      4,
#     "budget_limit":       3,
#     "policy_violations":  1,
#     "max_violations":     2,
#     "latency_p99_ms":     1800,
#     "latency_baseline_ms": 800,
#     "latency_breach_ratio": 2.0,
#     "stale_context":      true,
#     "disagreement_score": 0.7,
#     "disagreement_threshold": 0.6,
#     "window_seconds":     300
#   }
#
# Output:
#   {
#     "breached":           true/false,
#     "signals_breached":   ["failure_count", ...],
#     "recommended_level":  0-5,
#     "reason":             "..."
#   }
#
# Degradation levels:
#   0 = None (full autonomy)
#   1 = Increase trace sampling
#   2 = Tighten retry/concurrency limits
#   3 = Switch to safer profile
#   4 = Recommendation-only mode
#   5 = Hard stop (operator escalation)
#
# This policy runs in the OPA sidecar and is called by the
# Trigger Evaluator (src/governance/degradation/trigger_evaluator.py)
# for external policy validation alongside the local scoring.
#
# Reference:
#   Agent-Workforce-Control-Plane-Magazine.html §02 Scenario A,
#   §08 Degradation Policy Engine
# ============================================================

package awcp.failure_budget

import rego.v1

# ── Failure count breach ──────────────────────────────────────

failure_budget_breached if {
    input.failure_count >= input.budget_limit
}

# ── Policy violation breach ───────────────────────────────────

policy_violation_breached if {
    input.policy_violations >= input.max_violations
}

# ── Latency breach ────────────────────────────────────────────

latency_breached if {
    input.latency_p99_ms >= input.latency_baseline_ms * input.latency_breach_ratio
}

# ── Stale context breach ──────────────────────────────────────

stale_context_breached if {
    input.stale_context == true
}

# ── Disagreement breach ───────────────────────────────────────

disagreement_breached if {
    input.disagreement_score >= input.disagreement_threshold
}

# ── Collect breached signal names ─────────────────────────────

signals_breached contains "failure_count" if {
    failure_budget_breached
}

signals_breached contains "policy_violations" if {
    policy_violation_breached
}

signals_breached contains "latency_p99" if {
    latency_breached
}

signals_breached contains "stale_context" if {
    stale_context_breached
}

signals_breached contains "disagreement" if {
    disagreement_breached
}

# ── Overall breach determination ──────────────────────────────

default breached := false

breached if {
    count(signals_breached) > 0
}

# ── Recommended degradation level ─────────────────────────────
# More breached signals → higher recommended level.
# Hard stop requires 4+ signals or explicit failure budget breach
# combined with stale context.

default recommended_level := 0

recommended_level := 5 if {
    count(signals_breached) >= 4
}

recommended_level := 5 if {
    failure_budget_breached
    stale_context_breached
    policy_violation_breached
}

recommended_level := 4 if {
    not recommended_level == 5
    count(signals_breached) >= 3
}

recommended_level := 3 if {
    not recommended_level == 5
    not recommended_level == 4
    count(signals_breached) >= 2
}

recommended_level := 2 if {
    not recommended_level == 5
    not recommended_level == 4
    not recommended_level == 3
    failure_budget_breached
}

recommended_level := 1 if {
    not recommended_level == 5
    not recommended_level == 4
    not recommended_level == 3
    not recommended_level == 2
    count(signals_breached) >= 1
}

# ── Reason string ─────────────────────────────────────────────

default reason := "All signals within budget."

reason := concat("; ", [
    sprintf("Breached signals: %v", [signals_breached]),
    sprintf("Recommended level: %d", [recommended_level]),
]) if {
    breached
}
