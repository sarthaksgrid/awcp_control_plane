"""
AWCP — WebSocket Runtime Adapter
==================================
Normalizes inbound WebSocket messages from real-time
agent runtimes into governed WorkflowEvent envelopes.

Responsibilities:
  - Maintain persistent WebSocket connections
  - Parse incoming frames (JSON/binary)
  - Map to canonical WorkflowEvent schema
  - Forward to the Workflow Intake Proxy
"""
