from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# from app.activities import call_deepseek_run

with workflow.unsafe.imports_passed_through():
    from app.activities import call_ollama_run, call_deepseek_run


@workflow.defn
class OllamaRunWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            call_ollama_run,
            request,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
    
@workflow.defn
class deepSeekRunWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            call_deepseek_run,
            request,
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
