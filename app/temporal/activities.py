from typing import Any

import httpx
from temporalio import activity
from temporalio.client import Client

from app.config.config import TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE


def _payload_with_workflow_context(
    request: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(payload)
    workflow_id = request.get("workflow_id")
    run_id = request.get("run_id")
    if workflow_id is not None:
        enriched["workflow_id"] = workflow_id
    if run_id is not None:
        enriched["run_id"] = run_id
    return enriched


def _runtime_events_from_body(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []

    events: list[dict[str, Any]] = []
    
    # Check for tool_calls field (new format)
    tool_calls = body.get("tool_calls")
    if isinstance(tool_calls, list):
        for item in tool_calls:
            if isinstance(item, dict):
                events.append(item)
        return events
    
    # Check for tool_events field (old format)
    for key in ("tool_events", "execution_events"):
        items = body.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("event") not in (
                    "agent_started",
                    "agent_completed",
                ):
                    events.append(item)
    
    return events


async def _signal_workflow_events(
    request: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    workflow_id = request.get("workflow_id")
    run_id = request.get("run_id")
    if not workflow_id or not events:
        return

    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    for event in events:
        await handle.signal("execution_event", event)


@activity.defn
async def record_execution_event(event: dict[str, Any]) -> dict[str, Any]:
    activity.logger.info(f"EXECUTION_EVENT | {event}")
    return {"recorded": event}


@activity.defn
async def record_agent_run(agent_response: dict[str, Any]) -> dict[str, Any]:
    pass


@activity.defn
async def record_tool_call(tool_data: dict[str, Any]) -> dict[str, Any]:
    """
    Record a single tool call (merged started + final status) as one activity.
    This activity appears once per tool call in the Temporal UI.
    """
    tool_name = tool_data.get("tool_name")
    status = tool_data.get("status")
    
    activity.logger.info(
        f"TOOL_CALL | "
        f"tool={tool_name} | "
        f"status={status}"
    )
    
    return {
        "activity_type": "tool_call",
        "tool_name": tool_name,
        "input": tool_data.get("input"),
        "status": status,
        "output": tool_data.get("output"),
        "error": tool_data.get("error"),
    }


@activity.defn
async def call_ollama_run(request: dict[str, Any]) -> dict[str, Any]:
    endpoint_url = request["endpoint_url"]
    payload = request["payload"]

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.post(
            endpoint_url,
            json=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "ngrok-skip-browser-warning": "true",
            },
        )

    response.raise_for_status()

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    return {
        "called_url": endpoint_url,
        "method": "POST",
        "status_code": response.status_code,
        "payload": payload,
        "body": body,
    }




@activity.defn
async def call_deepseek_run(request: dict[str, Any]) -> dict[str, Any]:
    endpoint_url = request["endpoint_url"]
    payload = request["payload"]

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.post(
            endpoint_url,
            json=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "ngrok-skip-browser-warning": "true",
            },
        )

    response.raise_for_status()

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    return {
        "called_url": endpoint_url,
        "method": "POST",
        "status_code": response.status_code,
        "payload": payload,
        "body": body,
    }






# ----------------Cheking Agent Workflow-----------------
@activity.defn
async def execute_agent(request: dict):

    payload = _payload_with_workflow_context(request, request["payload"])

    async with httpx.AsyncClient() as client:

        response = await client.post(
            request["endpoint_url"],
            json=payload,
            timeout=300,
        )

        response.raise_for_status()

        body = response.json()
        await _signal_workflow_events(
            request,
            _runtime_events_from_body(body),
        )
        return body
    


@activity.defn
async def run_image_deepseek_activity(request: dict[str, Any]) -> dict[str, Any]:
    endpoint_url = request["endpoint_url"]

    image_bytes = bytes(request["image_bytes"])

    files = {
        "file": (
            request["filename"],
            image_bytes,
            request["content_type"],
        )
    }

    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        response = await client.post(
            endpoint_url,
            files=files,
            headers={
                "accept": "application/json",
                "ngrok-skip-browser-warning": "true",
            },
        )

    response.raise_for_status()

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    return {
        "called_url": endpoint_url,
        "method": "POST",
        "status_code": response.status_code,
        "body": body,
    }





# ------ from typing import Any  -----

@activity.defn
async def call_ollama_run_web(
    request: dict[str, Any]
) -> dict[str, Any]:

    endpoint_url = request["endpoint_url"]
    payload = _payload_with_workflow_context(request, request["payload"])

    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True
    ) as client:

        response = await client.post(
            endpoint_url,
            json=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "ngrok-skip-browser-warning": "true",
            },
        )

    response.raise_for_status()

    try:
        body = response.json()
    except ValueError:
        body = {"raw_response": response.text}

    metadata = {}

    if isinstance(body, dict):
        for key, value in body.items():

            if key in [
                "output",
                "answer",
                "response",
                "body",
                "tool_events",
            ]:
                continue

            metadata[key] = value

    tool_events = _runtime_events_from_body(body)
    await _signal_workflow_events(request, tool_events)

    for event in tool_events:

        activity.logger.info(
            f"TOOL_EVENT | "
            f"tool={event.get('tool')} | "
            f"status={event.get('status')}"
        )

    activity.logger.info(
        f"Agent metadata: {metadata}"
    )

    return {
        "called_url": endpoint_url,
        "method": "POST",
        "status_code": response.status_code,
        "payload": payload,

        # NEW
        "tool_events": tool_events,

        "metadata": metadata,
        "body": body,
    }