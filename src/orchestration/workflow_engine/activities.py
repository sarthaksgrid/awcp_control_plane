from datetime import datetime
import httpx
from temporalio import activity


# REPLACE THIS WITH YOUR ACTUAL NGROK URL
NGROK_LLM_URL = "https://crumpet-alphabet-truffle.ngrok-free.dev/run"


@activity.defn
async def call_llm_activity(prompt: str) -> dict:

    activity.logger.info(
        "Calling external hosted LLM",
        extra={"prompt": prompt}
    )

    async with httpx.AsyncClient(timeout=120.0) as client:

        response = await client.post(
            NGROK_LLM_URL,
            json={
                "prompt": prompt
            }
        )

        response.raise_for_status()

        try:
            body = response.json()
        except Exception:
            body = {
                "text": response.text
            }

    result = {
        "llm_response": body,
        "timestamp": datetime.utcnow().isoformat()
    }

    return result