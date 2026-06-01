import os


TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "ollama-run-task-queue")
TEMPORAL_UI_URL = os.getenv("TEMPORAL_UI_URL", "http://localhost:8080")

OLLAMA_API_BASE_URL = os.getenv(
    "OLLAMA_API_BASE_URL",
    "https://crumpet-alphabet-truffle.ngrok-free.dev",
).rstrip("/")
OLLAMA_RUN_URL = f"{OLLAMA_API_BASE_URL}/run"
