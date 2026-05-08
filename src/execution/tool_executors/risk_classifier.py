"""
AWCP — Tool Risk Classifier
==============================
Classifies tool calls by risk tier to determine
whether they require an approval token.

Risk tiers:
  - LOW    — read-only, no state change (auto-authorized)
  - MEDIUM — limited state change, within declared scope
  - HIGH   — cross-system write, privilege elevation, bulk operations
  - CRITICAL — irreversible actions, data deletion, production deployment
"""
