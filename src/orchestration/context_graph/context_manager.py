"""
AWCP — Context Graph Manager
================================
Maintains a DAG of context artifacts, hashes, and checkpoints
across a governed workflow.

Responsibilities:
  - Build the initial governing context slice (4K–16K tokens)
  - Track context hashes for staleness detection
  - Manage token budgets and relevance scoring
  - Store and retrieve cross-agent shared state
  - Maintain replay checkpoints for recovery
  - Fold RLM-compressed summaries back into the graph

Provides:
  - assemble_context()       — build governing slice for a branch
  - update_context()         — add new artifacts / evidence
  - check_freshness()        — compare current vs. stored hash
  - get_checkpoint()         — retrieve latest safe resume point
  - fold_summary()           — merge RLM output into the graph
"""
