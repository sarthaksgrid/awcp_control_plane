"""
AWCP — FastAPI Application
=============================
Main FastAPI application that exposes the control-plane
REST API for operators, runtime adapters, and internal services.

API groups:
  - /api/v1/agents         — Agent Registry CRUD
  - /api/v1/workflows      — Workflow lifecycle operations
  - /api/v1/approvals      — Approval token management
  - /api/v1/evidence       — Evidence ledger queries
  - /api/v1/policies       — Policy management
  - /api/v1/degradation    — Degradation state queries
  - /api/v1/tools          — Tool registration and execution
  - /api/v1/health         — Health and readiness checks
"""



from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from temporalio.client import Client

from src.pb2.routes import router as pb2_router
from src.temporal.workflows.document_workflow import DocumentWorkflow

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pb2_router)


@app.get("/")
async def root():
    return {"message": "API Running"}


@app.post("/process")
async def process_document():

    client = await Client.connect("localhost:7233")

    handle = await client.start_workflow(
        DocumentWorkflow.run,
        "src/temporal/uploads/sample.pdf",
        id="document-workflow-id",
        task_queue="document-task-queue",
    )

    return {
        "message": "Workflow started",
        "workflow_id": handle.id,
    }
