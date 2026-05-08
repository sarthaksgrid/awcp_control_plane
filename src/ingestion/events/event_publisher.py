"""
AWCP — Event Publisher
=======================
Publishes control-plane events back to external systems
(e.g., Slack, PagerDuty, incident channels) and to internal
message topics for downstream consumers.

Responsibilities:
  - Format events for each destination (JSON, Slack blocks, etc.)
  - Publish to Kafka / NATS topics
  - Send webhook notifications for approval requests
  - Retry with exponential backoff on failures
"""
