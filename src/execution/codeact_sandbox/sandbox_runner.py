"""
AWCP — CodeAct Sandbox Runner
================================
Sandboxed code generation and execution environment.

Agents generate Python or TypeScript for:
  - State-changing tool calls
  - Replay analysis
  - Instrumentation patch proposals

Execution happens in isolated Modal containers with:
  - Resource limits (CPU, memory, time)
  - Network restrictions
  - Artifact capture (stdout, stderr, diffs, traces)
  - Evidence folding back into the ledger

Provides:
  - run_sandboxed()          — execute code in an isolated container
  - generate_patch()         — create instrumentation patch for review
  - capture_artifacts()      — collect outputs for evidence ledger
"""
