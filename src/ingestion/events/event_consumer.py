"""
AWCP — Event Consumer
======================
Consumes workflow events from message brokers
(Kafka / NATS / SQS) and routes them into the
Workflow Intake Proxy for normalization.

Responsibilities:
  - Subscribe to configured topics / subjects
  - Deserialize event payloads
  - Apply back-pressure and rate limiting
  - Acknowledge / NACK messages based on processing outcome
"""
