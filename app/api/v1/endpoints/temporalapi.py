import os
from typing import Any
from uuid import uuid4

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from temporalio.client import Client
from temporalio.exceptions import TemporalError

from app.temporal.workflows import OllamaRunWorkflow, deepSeekRunWorkflow, ImageRunWorkflow

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


@router.get("/workflow-stats")
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
