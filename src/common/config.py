"""
AWCP — Application Configuration
=================================
Centralized settings via pydantic-settings.
Loads from environment variables and .env files.

Covers:
  - Database URLs (PostgreSQL, Redis)
  - LLM provider keys (Anthropic, OpenAI)
  - Temporal server address
  - OPA endpoint
  - Feature-flag provider config
  - Observability exporter endpoints
"""
