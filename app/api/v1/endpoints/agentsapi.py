import os
from typing import Any
from uuid import uuid4

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
import httpx
from pydantic import BaseModel, Field
from temporalio.client import Client
from temporalio.exceptions import TemporalError

from app.temporal.workflows import OllamaRunWorkflow, deepSeekRunWorkflow, ImageRunWorkflow

from app.schemas.schemas import WorkflowRunRequest, WorkflowRunResponse, WorkflowRunResponsepayload, AgentRunRequest, WorkflowRunResponseImage, AgentRegisterRequest

from fastapi import APIRouter, Depends

router = APIRouter()



TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE")
TEMPORAL_UI_URL = os.getenv("TEMPORAL_UI_URL")

OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL").rstrip("/")
OLLAMA_RUN_URL = f"{OLLAMA_API_BASE_URL}"

DEEPSEEK_API_BASE_URL = os.getenv("DEEPSEEK_API_BASE_URL",).rstrip("/")
DEEPSEEK_RUN_URL = f"{DEEPSEEK_API_BASE_URL}"




@router.post("/ollama-search", response_model=WorkflowRunResponsepayload)
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
            "ngrok_endpoint": f"{OLLAMA_RUN_URL}/chat/ollama",
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
    

@router.post("/deepseek-search", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest) -> dict[str, Any]:
    try:
        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )
        workflow_id = f"deepseek-run-{uuid4()}"
        workflow_request = {
            "endpoint_url": f"{DEEPSEEK_RUN_URL}/run",
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




@router.post("/nvidia-image-read", response_model=WorkflowRunResponseImage)
async def run_workflow_image(
    image: UploadFile = File(...)
) -> dict[str, Any]:
    try:
        image_bytes = await image.read()

        client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )

        workflow_id = f"deepseek-image-run-{uuid4()}"

        workflow_request = {
            # "endpoint_url": f"{DEEPSEEK_RUN_URL}/analyze-image" ,
            "endpoint_url": f"{DEEPSEEK_RUN_URL}/run-traceable-pipeline" ,
            "method": "POST",
            "filename": image.filename,
            "content_type": image.content_type,
            "image_bytes": image_bytes,
        }

        handle = await client.start_workflow(
            ImageRunWorkflow.run,
            workflow_request,
            id=workflow_id,
            task_queue=TEMPORAL_TASK_QUEUE,
        )

        output = await handle.result()

        return {
            "workflow_id": workflow_id,
            "run_id": handle.result_run_id,
            "ngrok_endpoint": DEEPSEEK_RUN_URL,
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
    


@router.get("/agents")
async def get_agents():

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://crumpet-alphabet-truffle.ngrok-free.dev/agents"
        )

    return response.json()
