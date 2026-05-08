"""
AWCP — gRPC Runtime Adapter
=============================
Normalizes inbound gRPC streaming events from existing
agent runtimes into governed WorkflowEvent envelopes.

Responsibilities:
  - Receive gRPC stream messages
  - Deserialize protobuf payloads
  - Map to canonical WorkflowEvent schema
  - Forward to the Workflow Intake Proxy
"""
