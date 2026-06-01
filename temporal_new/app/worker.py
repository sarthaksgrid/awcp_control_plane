import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.activities import call_ollama_run
from app.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TEMPORAL_TASK_QUEUE
from app.workflows import OllamaRunWorkflow


async def main() -> None:
    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )

    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[OllamaRunWorkflow],
        activities=[call_ollama_run],
    )

    print(
        f"Worker running on task queue '{TEMPORAL_TASK_QUEUE}' "
        f"for namespace '{TEMPORAL_NAMESPACE}'"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
