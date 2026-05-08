"""
AWCP — Handoff Coordinator
=============================
Manages agent-to-agent context transfers with
session continuity during governed workflows.

Responsibilities:
  - Isolate failing branches to prevent contamination
  - Transfer context between agents without loss
  - Maintain session continuity across handoffs
  - Create and enforce safe resume points
  - Log all handoffs in the evidence ledger

Provides:
  - initiate_handoff()    — start a governed handoff
  - transfer_context()    — pass context to receiving agent
  - isolate_branch()      — quarantine a failing branch
  - resume_from_point()   — restart from a safe checkpoint
"""
