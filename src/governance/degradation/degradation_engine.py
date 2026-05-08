"""
AWCP — Degradation Policy Engine
====================================
Evaluates multi-signal triggers and progressively reduces
agent autonomy to preserve service continuity.

Degradation ladder (default, overridable per workflow):
  1. Increase trace sampling depth
  2. Tighten retry and concurrency limits
  3. Switch to safer model / profile
  4. Move to recommendation-only mode
  5. Hard stop — operator escalation

Trigger signals:
  - Failure budget breach (N failed writes in window)
  - Stale context detection (context hash mismatch)
  - Policy violation count
  - Latency spike
  - Agent disagreement score

Provides:
  - evaluate_degradation()  — check if triggers warrant level change
  - apply_degradation()     — execute the degradation step
  - get_degradation_state() — current level for a workflow branch
  - override_ladder()       — set workflow-specific thresholds
"""
