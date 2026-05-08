"""
AWCP — Custom Exceptions
=========================
Domain-specific exceptions used throughout the control plane:

  - PolicyDeniedError           — action blocked by policy engine
  - ApprovalTokenExpiredError   — token has passed its expiry window
  - ApprovalTokenInvalidError   — token scope does not match request
  - DegradationThresholdError   — failure budget breached
  - QuarantineError             — agent lacks required control hooks
  - ContextStaleError           — context hash mismatch detected
  - ReplayError                 — replay failed from checkpoint
  - AdapterNormalizationError   — runtime event could not be normalized
"""
