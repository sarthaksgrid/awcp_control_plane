"""
AWCP — Temporal Worker Setup
==============================
Configures and starts the Temporal worker process,
registering all workflows and activities.

Responsibilities:
  - Connect to the Temporal server
  - Register workflow and activity implementations
  - Start the worker event loop
  - Handle graceful shutdown
"""
