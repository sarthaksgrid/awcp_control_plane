import base64
import os
from typing import Any
from uuid import uuid4

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from temporalio.client import Client
from temporalio.exceptions import TemporalError

from app.temporal.workflows import AgentRunWorkflow, ImageRunWorkflow, OllamaRunWorkflowWeb

from fastapi import APIRouter, Depends, UploadFile, File

from app.schemas.schemas import AgentRunRequest, WorkflowRunRequest, WorkflowRunResponsepayload

router = APIRouter()



TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE")
TEMPORAL_UI_URL = os.getenv("TEMPORAL_UI_URL")

OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL").rstrip("/")
OLLAMA_RUN_URL = f"{OLLAMA_API_BASE_URL}"

DEEPSEEK_API_BASE_URL = os.getenv("DEEPSEEK_API_BASE_URL",).rstrip("/")
DEEPSEEK_RUN_URL = f"{DEEPSEEK_API_BASE_URL}"
DEEPSEEK_RUN_URL = f"{DEEPSEEK_API_BASE_URL}/analyze-image"


router = APIRouter()

"""
@router.post("/run-agent")
async def run_agent(request: AgentRunRequest):

    if not Path(AGENTS_FILE).exists():
        raise HTTPException(
            status_code=500,
            detail="agents.json not found"
        )

    with open(AGENTS_FILE, "r") as f:
        agents = json.load(f)

    selected_agent = next(
        (agent for agent in agents if agent["id"] == request.agent_id),
        None
    )

    if not selected_agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    try:
        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )

        workflow_id = f"agent-run-{uuid4()}"

        workflow_request = {
            "agent_id": selected_agent["id"],
            "agent_name": selected_agent["name"],
            "endpoint_url": f"{selected_agent["url"]}/run",
            "method": "POST",
            "payload": {
                "input": request.input
            }
        }

        handle = await client.start_workflow(
            AgentRunWorkflow.run,   # or a generic workflow
            workflow_request,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )

        output = await handle.result()

        return {
            "workflow_id": workflow_id,
            "run_id": handle.result_run_id,
            "agent": selected_agent["name"],
            "input": request.input,
            "output": output,
        }

    except TemporalError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Temporal error: {exc}"
        ) from exc
    
"""
# ----- for tool call ---

@router.post("/run-ollama-api-web", response_model=WorkflowRunResponsepayload)
async def run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    try:
        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )
        workflow_id = f"ollama-run-{uuid4()}"
        workflow_request = {
            "endpoint_url": f"{OLLAMA_RUN_URL}/chat/ollama-search",
            "method": "POST",
            "payload": {"input": request.input},
        }

        handle = await client.start_workflow(
            OllamaRunWorkflowWeb.run,
            workflow_request,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )

        output = await handle.result()

        return {
            "workflow_id": workflow_id,
            "run_id": handle.result_run_id,
            "ngrok_endpoint": f"{OLLAMA_RUN_URL}/chat/ollama-search" ,
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