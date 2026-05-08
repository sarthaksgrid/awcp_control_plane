"""
AWCP — Control Signal Router
==============================
Routes inbound control signals (alerts, flag changes, policy events)
to the appropriate control-plane handlers.

Signal types handled:
  - Failure budget alerts       → Degradation Policy Engine
  - Feature flag toggles        → Agent Registry hooks
  - Policy schedule triggers    → Quarantine / expiry scans
  - Operator manual overrides   → Approval Gate Controller
"""
