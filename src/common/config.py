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
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    project_name: str = "AWCP"
    environment: str = "development"
    database_url: str 
    opa_url: str
    temporal_host: str
    log_level:str = "INFO"

    model_config = SettingsConfigDict(
        env_file = ".env",
        case_sensitive = False,
    )

settings = Settings() 