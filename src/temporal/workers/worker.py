import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from src.temporal.workflows.document_workflow import DocumentWorkflow

from src.temporal.activities.document_activities import (
    extract_text,
    summarize_text,
    save_summary,
    send_email,
)


async def main():

    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="document-task-queue",
        workflows=[DocumentWorkflow],
        activities=[
            extract_text,
            summarize_text,
            save_summary,
            send_email,
        ],
    )

    print("WORKER STARTED")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())