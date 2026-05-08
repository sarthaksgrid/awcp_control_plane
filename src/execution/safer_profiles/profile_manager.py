"""
AWCP — Safer Profile Manager
================================
Manages model and mode switches during degradation.

When the degradation engine triggers a safer profile:
  - Pin to a more conservative model
  - Reduce temperature / creativity settings
  - Switch to recommendation-only output mode
  - Disable write-capable tool calls
  - Increase trace verbosity

Profiles:
  - FULL_AUTONOMY       — default, all capabilities enabled
  - CONSERVATIVE        — safer model, tighter retry limits
  - RECOMMENDATION_ONLY — no writes, suggest-only mode
  - READ_ONLY           — analysis and observation only
  - HARD_STOP           — all execution paused, operator required
"""
