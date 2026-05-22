"""Worker process for the PB-2 governed Temporal workflow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from temporalio.client import Client
from temporalio.worker import Worker

from src.pb2.temporal_config import PB2_TASK_QUEUE, TEMPORAL_ADDRESS
from src.temporal.activities.pb2_activities import (
    pb2_create_approval,
    pb2_run_sandbox,
    pb2_save_workflow,
    pb2_score_event,
    pb2_write_evidence,
)
from src.temporal.workflows.governed_agent_workflow import GovernedAgentWorkflow


async def main() -> None:
    """Connect to local Temporal and serve PB-2 tasks."""

    client = await Client.connect(TEMPORAL_ADDRESS)
    worker = Worker(
        client,
        task_queue=PB2_TASK_QUEUE,
        workflows=[GovernedAgentWorkflow],
        activities=[
            pb2_score_event,
            pb2_write_evidence,
            pb2_create_approval,
            pb2_save_workflow,
            pb2_run_sandbox,
        ],
    )

    print(f"PB-2 GOVERNANCE WORKER STARTED on {PB2_TASK_QUEUE}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
