"""
AWCP — Approval Token Manager
================================
JWT-based approval token generation, validation, and lifecycle.

Token claims:
  - workflow_id       — bound workflow
  - branch_id         — bound branch
  - action_class      — permitted action (e.g., billing.adjustment)
  - issued_by         — operator identity
  - issued_at         — timestamp
  - expires_at        — expiry timestamp
  - consumed          — whether the token has been used
  - rollback_pointer  — checkpoint for rollback if action fails
"""
