"""
AWCP — Workflow Intake Proxy
==============================
The front door of the control plane.

Responsibilities:
  - Receive normalized events from adapters and consumers
  - Assign workflow identity (or reuse existing)
  - Map owner via Agent Registry lookup
  - Shape inbound load (rate limiting, priority queuing)
  - Open or resume a governed workflow branch
  - Emit intake telemetry spans
"""
