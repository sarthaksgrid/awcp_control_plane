from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

from temporalio.client import Client


class RunRequest(BaseModel):
    prompt: str


app = FastAPI()

TASK_QUEUE = "awcp-task-queue"


@app.on_event("startup")
async def startup_event():

    app.state.temporal_client = await Client.connect(
        "localhost:7233"
    )

    print("Connected to Temporal")


@app.get("/")
async def health():

    return {
        "status": "ok"
    }


@app.post("/run")
async def run_workflow(req: RunRequest):

    client: Client = getattr(
        app.state,
        "temporal_client",
        None
    )

    if client is None:

        raise HTTPException(
            status_code=500,
            detail="Temporal client unavailable"
        )

    workflow_id = f"awcp-{uuid.uuid4()}"

    from .orchestration.workflow_engine.workflows import (
        LLMWorkflow
    )

    handle = await client.start_workflow(
        LLMWorkflow.run,
        req.prompt,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return {
        "workflow_id": handle.id,
        "run_id": handle.run_id
    }