"""
AWCP — Control Hooks Manager
==============================
Manages the lifecycle of control hooks attached to agents:

  - Telemetry hooks      (OTel span emission for step boundaries)
  - Feature-flag hooks   (callback on autonomy mode transitions)
  - Policy callbacks     (checkpoint events before write-capable calls)

Provides:
  - attach_hooks()       — bind hooks to an agent
  - verify_hooks()       — check if all required hooks are present
  - generate_patch()     — create an instrumentation patch proposal for missing hooks
"""
