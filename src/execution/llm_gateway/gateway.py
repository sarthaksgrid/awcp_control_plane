"""
AWCP — LLM Gateway
=====================
Unified interface to multiple LLM providers.

Responsibilities:
  - Provider routing (Anthropic / OpenAI / local models)
  - Provider pinning during degradation (safer profiles)
  - Failover between providers
  - Rate limiting and cost tracking
  - Caching for idempotent requests
  - Streaming support for real-time responses

Provides:
  - complete()        — standard completion request
  - stream()          — streaming completion
  - score()           — local LM scoring for triggers
  - summarize()       — RLM recursive summarization
  - switch_provider() — change provider for safer profile
"""
