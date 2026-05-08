"""
AWCP — Temporal Workflow Definitions
=======================================
Defines Temporal workflow classes that govern agent actions:

  - GovernedWorkflow       — main orchestration DAG
  - ApprovalWaitWorkflow   — durable wait for operator token
  - ReplayWorkflow         — checkpoint-based recovery replay
  - DegradationWorkflow    — progressive autonomy reduction

Each workflow step defines:
  - Pre-conditions (risk signals, stale-context checks, failure budgets)
  - Execution policy (timeout, retry, idempotency keys, autonomy mode)
  - Post-conditions (output validation, state assertions, ledger writes)
"""
