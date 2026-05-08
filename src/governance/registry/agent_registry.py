"""
AWCP — Agent Registry Service
================================
Versioned catalog of all agents in the workforce.

Stores per agent:
  - Agent ID, owner, team
  - Runtime binding (which adapter)
  - Declared write scopes
  - Feature-flag callback endpoints
  - Observability status (OTel hooks present?)
  - Quarantine state and onboarding readiness
  - Policy callback points

Operations:
  - register_agent()         — add a new agent
  - update_agent()           — modify write scopes, flags, etc.
  - get_agent()              — lookup by agent_id
  - list_agents()            — list with filters (quarantined, active, etc.)
  - check_onboarding()       — verify required hooks before write promotion
  - set_quarantine_status()  — quarantine or release an agent
"""
