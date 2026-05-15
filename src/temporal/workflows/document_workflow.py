from temporalio import workflow
from datetime import timedelta

with workflow.unsafe.imports_passed_through():

    from src.temporal.activities.document_activities import (
        extract_text,
        summarize_text,
        save_summary,
        send_email,
    )


@workflow.defn
class DocumentWorkflow:

    @workflow.run
    async def run(self, file_path: str):

        print("WORKFLOW STARTED")

        text = await workflow.execute_activity(
            extract_text,
            file_path,
            start_to_close_timeout=timedelta(seconds=30),
        )

        summary = await workflow.execute_activity(
            summarize_text,
            text,
            start_to_close_timeout=timedelta(seconds=30),
        )

        await workflow.execute_activity(
            save_summary,
            summary,
            start_to_close_timeout=timedelta(seconds=30),
        )

        await workflow.execute_activity(
            send_email,
            start_to_close_timeout=timedelta(seconds=30),
        )

        return summary