"""
AWCP — Base Runtime Adapter
=============================
Abstract base class for all runtime adapters (REST, gRPC, WebSocket).

Every adapter must:
  1. Normalize inbound events into a WorkflowEvent envelope
  2. Map the source runtime to an AgentIdentity
  3. Attach owner metadata for registry lookup
  4. Emit an OTel span for the ingestion boundary

Concrete implementations:
  - RestAdapter       (rest_adapter.py)
  - GrpcAdapter       (grpc_adapter.py)
  - WebSocketAdapter  (websocket_adapter.py)
"""
