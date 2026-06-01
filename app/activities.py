from typing import Any

import httpx
from temporalio import activity

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
