from pydantic import BaseModel, Field
from typing import Any



class WorkflowRunResponse(BaseModel):
    workflow_id: str
    run_id: str | None
    ngrok_endpoint: str
    output: dict[str, Any]
    temporal_ui_url: str


class ExecutionEventRelayRequest(BaseModel):
    workflow_id: str
    run_id: str
    event: dict[str, Any]



class WorkflowRunRequest(BaseModel):
    input: str = Field(..., min_length=1, description="Prompt/input to send to Ollama")


class WorkflowRunResponsepayload(BaseModel):
    workflow_id: str
    run_id: str | None
    ngrok_endpoint: str
    request_payload: dict[str, str]
    output: dict[str, Any]
    temporal_ui_url: str


class AgentRunRequest(BaseModel):
    agent_id: int
    input: str

class AgentRegisterRequest(BaseModel):
    name: str
    url: str



class WorkflowRunResponseImage(BaseModel):
    workflow_id: str
    run_id: str | None
    ngrok_endpoint: str
    output: dict[str, Any]
    temporal_ui_url: str