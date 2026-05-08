"""
AWCP — Replay Engine
======================
Replays workflow branches from checkpoints using
the evidence ledger and context graph.

Responsibilities:
  - Load checkpoint state from the ledger
  - Reconstruct governing context at the checkpoint
  - Re-execute in recommendation-only or validation mode
  - Generate a replay summary for operator review
  - Determine if safe resume is possible

Uses Recursive Language Models (RLMs) to compress
large trace histories into actionable summaries.

Provides:
  - replay_from_checkpoint()   — replay a branch
  - generate_replay_summary()  — RLM-compressed summary
  - validate_resume()          — check if safe to resume
"""
