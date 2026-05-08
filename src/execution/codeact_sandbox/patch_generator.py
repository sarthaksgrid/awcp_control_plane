"""
AWCP — Patch Generator
========================
Generates instrumentation patches for under-instrumented agents.

Produces:
  - OTel span emission hooks for step boundaries
  - Feature-flag callback wiring for autonomy transitions
  - Policy checkpoint events before write-capable calls
  - Integration diffs in unified format

Can use Codex CLI or Claude Code CLI as generation backends.
"""
