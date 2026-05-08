"""
AWCP — Tool Executor Service
================================
Executes governed tool calls after policy approval.

Each tool call passes through:
  1. Policy check (OPA evaluator)
  2. Approval token validation (if high-risk)
  3. Sandboxed execution
  4. Result capture and evidence recording
  5. State assertion (post-conditions)

Provides:
  - execute_tool()       — run a tool call with full governance
  - register_tool()      — register a new tool executor
  - list_tools()         — list available tools and risk tiers
"""
