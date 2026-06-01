import asyncio

from temporalio.client import Client
from temporalio.worker import Worker


async def main():

    client = await Client.connect(
        "localhost:7233"
    )

    from . import activities
    from .workflows import LLMWorkflow

    worker = Worker(
        client,
        task_queue="awcp-task-queue",
        workflows=[LLMWorkflow],
        activities=[activities.call_llm_activity],
    )

    print("Worker polling on awcp-task-queue")

    await worker.run()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Worker stopped")