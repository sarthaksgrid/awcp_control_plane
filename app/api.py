import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from temporalio.client import Client
from temporalio.exceptions import TemporalError

from app.workflows import OllamaRunWorkflow, deepSeekRunWorkflow


TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "ollama-run-task-queue")
TEMPORAL_UI_URL = os.getenv("TEMPORAL_UI_URL", "http://localhost:8080")

OLLAMA_API_BASE_URL = os.getenv(
    "OLLAMA_API_BASE_URL",
    "https://crumpet-alphabet-truffle.ngrok-free.dev",
).rstrip("/")
OLLAMA_RUN_URL = f"{OLLAMA_API_BASE_URL}/run"

DEEPSEEK_API_BASE_URL = os.getenv(
    "DEEPSEEK_API_BASE_URL",
    "https://simile-surcharge-evasion.ngrok-free.dev"
).rstrip("/")
DEEPSEEK_RUN_URL = f"{DEEPSEEK_API_BASE_URL}/run"

app = FastAPI(
    title="AWCP Temporal Control Plane",
    description="Starts Temporal workflows from HTTP requests.",
    version="1.0.0",
)


class WorkflowRunRequest(BaseModel):
    input: str = Field(..., min_length=1, description="Prompt/input to send to Ollama")


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    run_id: str | None
    ngrok_endpoint: str
    request_payload: dict[str, str]
    output: dict[str, Any]
    temporal_ui_url: str


# @app.get("/health")
# async def health() -> dict[str, str]:
#     return {"status": "ok"}


@app.post("/runollamaapi", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    try:
        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )
        workflow_id = f"ollama-run-{uuid4()}"
        workflow_request = {
            "endpoint_url": OLLAMA_RUN_URL,
            "method": "POST",
            "payload": {"input": request.input},
        }

        handle = await client.start_workflow(
            OllamaRunWorkflow.run,
            workflow_request,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )

        output = await handle.result()

        return {
            "workflow_id": workflow_id,
            "run_id": handle.result_run_id,
            "ngrok_endpoint": OLLAMA_RUN_URL,
            "request_payload": {"input": request.input},
            "output": output,
            "temporal_ui_url": (
                f"{TEMPORAL_UI_URL}/namespaces/{TEMPORAL_NAMESPACE}/workflows/"
                f"{workflow_id}/{handle.result_run_id}/history"
            ),
        }
    except TemporalError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not start or complete Temporal workflow: {exc}",
        ) from exc
    

@app.post("/rundeepseekapi", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    try:
        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )
        workflow_id = f"deepseek-run-{uuid4()}"
        workflow_request = {
            "endpoint_url": DEEPSEEK_RUN_URL,
            "method": "POST",
            "payload": {"input": request.input},
        }

        handle = await client.start_workflow(
            deepSeekRunWorkflow.run,
            workflow_request,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )

        output = await handle.result()

        return {
            "workflow_id": workflow_id,
            "run_id": handle.result_run_id,
            "ngrok_endpoint": DEEPSEEK_RUN_URL,
            "request_payload": {"input": request.input},
            "output": output,
            "temporal_ui_url": (
                f"{TEMPORAL_UI_URL}/namespaces/{TEMPORAL_NAMESPACE}/workflows/"
                f"{workflow_id}/{handle.result_run_id}/history"
            ),
        }
    except TemporalError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not start or complete Temporal workflow: {exc}",
        ) from exc



@app.get("/agents")
async def get_agents():
    agents = [
        {
            "name": "ollama",
            "endpoint": OLLAMA_RUN_URL,
            "status": "active"
        },
        {
            "name": "deepseek",
            "endpoint": DEEPSEEK_RUN_URL,
            "status": "active"
        }
    ]

    return {
        "total_agents": len(agents),
        "agents": agents
    }


@app.get("/workflow-stats")
async def workflow_stats():
    client = await Client.connect(
    TEMPORAL_ADDRESS,
    namespace=TEMPORAL_NAMESPACE,
    )

    running_count = 0
    completed_count = 0
    failed_count = 0

    async for _ in client.list_workflows(
        query='ExecutionStatus="Running"'
    ):
        running_count += 1

    async for _ in client.list_workflows(
        query='ExecutionStatus="Completed"'
    ):
        completed_count += 1

    async for _ in client.list_workflows(
        query='ExecutionStatus="Failed"'
    ):
        failed_count += 1

    return {
        "running": running_count,
        "completed": completed_count,
        "failed": failed_count,
    }