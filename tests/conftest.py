"""
AWCP — Test Fixtures
======================
Shared pytest fixtures for all test modules:

  - db_session         — async database session (isolated per test)
  - test_client        — FastAPI test client (httpx AsyncClient)
  - sample_agent       — pre-registered test agent
  - sample_workflow    — sample workflow state
  - mock_opa           — mocked OPA evaluator
  - mock_temporal      — mocked Temporal client
  - mock_llm           — mocked LLM provider
"""
