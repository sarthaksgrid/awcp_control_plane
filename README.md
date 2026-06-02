# Local Temporal Calling Public Ngrok Ollama API

This project starts a local Temporal workflow from a local FastAPI endpoint.

The FastAPI route starts the Temporal workflow directly from `app/api.py`.

Your Temporal server, worker, and optional FastAPI server run locally. The workflow input contains the public ngrok endpoint, method, and request body. The workflow activity calls:

```text
POST https://crumpet-alphabet-truffle.ngrok-free.dev/run
```

with body:

```json
{
  "input": "your prompt"
}
```

## Flow

```text
Local FastAPI POST /run
  -> local Temporal workflow
  -> local Temporal worker activity
  -> public ngrok FastAPI Ollama /run
  -> result returned as HTTP response
  -> workflow visible in Temporal UI
```

Calling the ngrok URL directly with `curl` will access Ollama, but it will **not** show in Temporal. To show it in Temporal, start the workflow with `POST http://127.0.0.1:8000/run`.

The ngrok endpoint is loaded into Temporal as workflow input:

```json
{
  "endpoint_url": "https://crumpet-alphabet-truffle.ngrok-free.dev/run",
  "method": "POST",
  "payload": {
    "input": "your prompt"
  }
}
```

## Structure

```text
awcp_control_plane/
  app/
    api.py         # Local FastAPI app that starts workflows over HTTP
    worker.py      # Local Temporal worker
    workflows.py   # Temporal workflow
    activities.py  # Calls public ngrok /run endpoint
    config.py      # Local settings
  requirements.txt
  .env.example
```

## 1. Install

```bash
cd /Users/pryadav/Desktop/Grid_Dynamic_Internship_Programm/Capstone_Project/awcp_control_plane
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Start Temporal Locally

Use your local Temporal setup. This project expects:

```text
Temporal server: localhost:7233
Namespace: default
Temporal UI: http://localhost:8080
```

If you use Temporal CLI, run this in a separate terminal:

```bash
temporal server start-dev
```

If your Temporal UI runs on `8233`, set this before starting the API:

```bash
export TEMPORAL_UI_URL=http://localhost:8233
```

## 3. Start The Worker

Keep this terminal running:

```bash
cd /Users/pryadav/Desktop/Grid_Dynamic_Internship_Programm/Capstone_Project/awcp_control_plane
source .venv/bin/activate
python -m app.worker
```

Expected log:

```text
Worker running on task queue 'ollama-run-task-queue' for namespace 'default'
```

## 4. Start The FastAPI Server

Keep Temporal and the worker running. Open another terminal:

```bash
cd /Users/pryadav/Desktop/Grid_Dynamic_Internship_Programm/Capstone_Project/awcp_control_plane
source .venv/bin/activate
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

Send input to the local FastAPI endpoint:

```bash
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"input":"Explain Temporal in one sentence"}'
```

The HTTP response looks like this:

```json
{
  "workflow_id": "ollama-run-...",
  "run_id": "...",
  "ngrok_endpoint": "https://crumpet-alphabet-truffle.ngrok-free.dev/run",
  "request_payload": {
    "input": "Explain Temporal in one sentence"
  },
  "output": {
    "called_url": "https://crumpet-alphabet-truffle.ngrok-free.dev/run",
    "method": "POST",
    "status_code": 200,
    "payload": {
      "input": "Explain Temporal in one sentence"
    },
    "body": {}
  },
  "temporal_ui_url": "http://localhost:8080/namespaces/default/workflows/..."
}
```

You can also open the interactive docs:

```text
http://127.0.0.1:8000/docs
```

## 5. View In Temporal UI

Open:

```text
http://localhost:8080
```

Search for the returned `workflow_id`, or open the returned `temporal_ui_url`.

You should see:

```text
OllamaRunWorkflow
  -> call_ollama_run
```

In the workflow history, open the workflow input or activity input. You will see the ngrok endpoint URL and payload there.

If it finishes quickly, check completed or closed workflows.

## Optional: Test Ngrok Directly

This tests the public Ollama FastAPI only. It does not create a Temporal workflow:

```bash
curl -X POST https://crumpet-alphabet-truffle.ngrok-free.dev/run \
  -H "Content-Type: application/json" \
  -H "ngrok-skip-browser-warning: true" \
  -d '{"input":"test from terminal"}'
```
