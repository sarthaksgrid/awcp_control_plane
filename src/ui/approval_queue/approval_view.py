"""
AWCP — Approval Queue View
==============================
Operator view for reviewing and acting on pending
approval requests.

Displays:
  - Pending approval requests sorted by risk and SLA
  - For each request: tool plan, context diff, rollback pointer, expiry window
  - Actions: approve, deny, narrow scope, escalate
  - History: recent approval decisions and their outcomes
"""
