"""
AWCP — Metrics Collector
===========================
Custom metrics for the control plane dashboard:

  - awcp_workflows_degraded        — gauge of workflows in degraded mode
  - awcp_pending_tokens            — gauge of pending approval tokens
  - awcp_quarantined_agents        — gauge of quarantined agents
  - awcp_governed_actions_total    — counter of completed governed actions
  - awcp_recovery_duration_seconds — histogram of recovery times
  - awcp_policy_evaluations_total  — counter of policy decisions
  - awcp_tool_risk_score           — histogram of tool call risk scores
"""
