"""
AWCP — Structured Logging
==========================
Configures structlog with JSON output for production
and human-readable output for development.

Provides:
  - get_logger(name)  — returns a bound logger with request context
  - setup_logging()   — initializes the logging pipeline
"""
