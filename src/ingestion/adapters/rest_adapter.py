"""
AWCP — REST Runtime Adapter
=============================
Normalizes inbound REST webhook / callback events
from existing agent runtimes into governed WorkflowEvent envelopes.

Responsibilities:
  - Parse incoming HTTP payloads (JSON)
  - Validate required fields (runtime_id, owner, event_type)
  - Map to canonical WorkflowEvent schema
  - Forward normalized event to the Workflow Intake Proxy
"""
