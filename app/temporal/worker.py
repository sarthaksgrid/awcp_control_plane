import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal.activities import call_deepseek_run, call_ollama_run, call_ollama_run_web, execute_agent, record_execution_event, run_image_deepseek_activity, record_agent_run, record_tool_call
from app.config.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TEMPORAL_TASK_QUEUE
from app.temporal.workflows import AgentRunWorkflow, OllamaRunWorkflow, deepSeekRunWorkflow, ImageRunWorkflow, OllamaRunWorkflowWeb


async def main() -> None:
    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )

    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[OllamaRunWorkflow, deepSeekRunWorkflow, AgentRunWorkflow, ImageRunWorkflow, OllamaRunWorkflowWeb],
        activities=[call_ollama_run, call_deepseek_run, execute_agent, run_image_deepseek_activity, call_ollama_run_web, record_execution_event, record_agent_run, record_tool_call],
    )

    print(
        f"Worker running on task queue '{TEMPORAL_TASK_QUEUE}' "
        f"for namespace '{TEMPORAL_NAMESPACE}'"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
