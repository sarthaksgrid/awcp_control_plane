import argparse
import asyncio
import json
from uuid import uuid4

from temporalio.client import Client

from awcp_control_plane.app.config import (
    OLLAMA_RUN_URL,
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
    TEMPORAL_TASK_QUEUE,
    TEMPORAL_UI_URL,
)
from awcp_control_plane.app.workflows import OllamaRunWorkflow


async def start_workflow(input_text: str) -> dict:
    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )
    workflow_id = f"ollama-run-{uuid4()}"
    workflow_request = {
        "endpoint_url": OLLAMA_RUN_URL,
        "method": "POST",
        "payload": {"input": input_text},
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
        "request_payload": {"input": input_text},
        "output": output,
        "temporal_ui_url": (
            f"{TEMPORAL_UI_URL}/namespaces/{TEMPORAL_NAMESPACE}/workflows/"
            f"{workflow_id}/{handle.result_run_id}/history"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a local Temporal workflow that calls the public ngrok Ollama API."
    )
    parser.add_argument("input", help="Prompt/input to send to the Ollama /run endpoint")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    result = await start_workflow(args.input)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
