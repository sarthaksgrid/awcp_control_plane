"""
AWCP — Replayable Evidence Ledger
====================================
Immutable, append-only store of all control-plane events.

Each entry records:
  - workflow_id + branch_id
  - actor (agent or operator)
  - action (tool call, approval, degradation step)
  - policy_result (allow / deny / escalate)
  - approval_token (if issued)
  - context_snapshot_hash
  - degradation_state
  - replay_trace reference
  - rollback_pointer
  - timestamp

Powers:
  - Audit trail and chain of custody
  - Deterministic replay from any checkpoint
  - Operator recovery decisions
  - Post-incident analysis

Provides:
  - write_entry()          — append a new evidence entry
  - get_entries()          — query entries by workflow/branch
  - get_replay_trace()     — retrieve full replay chain
  - get_rollback_point()   — find nearest safe rollback
"""
