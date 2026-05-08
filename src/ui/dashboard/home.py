"""
AWCP — Control Center Home Page
===================================
Risk-first home screen for Agent Ops operators.

Displays:
  - KPI cards: degraded workflows, pending tokens, blocked agents,
    governed actions completed, median recovery time
  - Workflow queue: prioritized by failure budgets and policy urgency
  - Tool/action gate: state-changing actions awaiting governance
  - Quick actions: open incident channel, trigger drift sweep

This is the primary Streamlit page for the operator.
"""
