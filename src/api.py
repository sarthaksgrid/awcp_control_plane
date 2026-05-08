"""
AWCP — FastAPI Application
=============================
Main FastAPI application that exposes the control-plane
REST API for operators, runtime adapters, and internal services.

API groups:
  - /api/v1/agents         — Agent Registry CRUD
  - /api/v1/workflows      — Workflow lifecycle operations
  - /api/v1/approvals      — Approval token management
  - /api/v1/evidence       — Evidence ledger queries
  - /api/v1/policies       — Policy management
  - /api/v1/degradation    — Degradation state queries
  - /api/v1/tools          — Tool registration and execution
  - /api/v1/health         — Health and readiness checks
"""
