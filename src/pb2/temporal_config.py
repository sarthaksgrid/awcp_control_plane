"""Temporal settings shared by PB-2 API routes and workers."""

from __future__ import annotations

import os


TEMPORAL_ADDRESS = os.getenv("AWCP_TEMPORAL_ADDRESS", "localhost:7233")
PB2_TASK_QUEUE = os.getenv("AWCP_PB2_TASK_QUEUE", "pb2-governance-task-queue")


def temporal_workflow_id(workflow_id: str) -> str:
    """Map a business workflow ID to the Temporal workflow ID."""

    return f"pb2-{workflow_id}"
