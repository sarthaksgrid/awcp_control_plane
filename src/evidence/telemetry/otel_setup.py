"""
AWCP — OpenTelemetry Setup
=============================
Configures OpenTelemetry tracing and metrics for the
entire control plane.

Responsibilities:
  - Initialize TracerProvider with OTLP exporter
  - Instrument FastAPI, httpx, and SQLAlchemy
  - Provide convenience functions for custom spans
  - Manage adaptive trace sampling (increases during degradation)

Provides:
  - setup_telemetry()        — initialize OTel pipeline
  - get_tracer()             — get a named tracer
  - set_sampling_rate()      — adjust trace sampling dynamically
  - create_governance_span() — span with policy context attributes
"""
