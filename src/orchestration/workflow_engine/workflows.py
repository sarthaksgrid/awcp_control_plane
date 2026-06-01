from datetime import timedelta

from temporalio import workflow


with workflow.unsafe.imports_passed_through():
    from src.orchestration.workflow_engine.activities import (
        call_llm_activity,
    )


@workflow.defn
class LLMWorkflow:

    @workflow.run
    async def run(self, prompt: str) -> dict:

        workflow.logger.info(
            "Workflow started",
            extra={"prompt": prompt}
        )

        result = await workflow.execute_activity(
            call_llm_activity,
            prompt,
            start_to_close_timeout=timedelta(seconds=120),
        )

        workflow.logger.info(
            "Workflow completed",
            extra={"result": result}
        )

        return result