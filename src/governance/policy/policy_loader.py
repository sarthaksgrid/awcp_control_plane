"""
AWCP — Policy Rules Loader
=============================
Loads and manages OPA Rego policy files from disk or
remote policy bundles.

Responsibilities:
  - Load .rego files from config/policies/
  - Push policy bundles to the OPA server
  - Hot-reload policies on file change
  - Validate policy syntax before deployment
"""
