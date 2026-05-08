"""
AWCP — Degradation Trigger Evaluator
=======================================
Scores and combines multi-signal triggers to determine
whether a degradation level change is warranted.

Signals scored:
  - failure_count       — recent failed write attempts
  - stale_context       — boolean from context hash comparison
  - policy_violations   — count in current window
  - latency_p99         — compared to baseline
  - disagreement_score  — inter-agent consistency measure

Returns a DegradationDecision with recommended level.
"""
