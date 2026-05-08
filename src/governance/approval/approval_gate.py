"""
AWCP — Approval Gate Controller
==================================
Issues and validates narrow, expiring approval tokens
for workflow-scoped write actions.

Token properties:
  - Bound to a single workflow branch
  - Scoped to a specific action class (e.g., billing.adjustment)
  - Has an expiry window (e.g., 15 minutes)
  - Single-use: consumed on first successful execution
  - Recorded in the evidence ledger

Operations:
  - request_approval()   — pause workflow and notify operator
  - issue_token()        — operator approves → create scoped token
  - validate_token()     — verify token matches request context
  - revoke_token()       — operator or system cancels token
  - check_expiry()       — scheduled scan for expired tokens
"""
