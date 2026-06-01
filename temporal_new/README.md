# Local Temporal Calling Public Ngrok Ollama API

This project does **not** create a local FastAPI server.

Your Temporal server and worker run locally. A terminal command starts the workflow. The workflow input contains the public ngrok endpoint, method, and request body. The workflow activity calls:

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
Terminal command
  -> local Temporal workflow
  -> local Temporal worker activity
  -> public ngrok FastAPI Ollama /run
  -> result printed in terminal
  -> workflow visible in Temporal UI
```

Calling the ngrok URL directly with `curl` will access Ollama, but it will **not** show in Temporal. To show it in Temporal, start the workflow with `python -m app.starter`.

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
temporal_new/
  app/
    starter.py     # Starts workflow from terminal
    worker.py      # Local Temporal worker
    workflows.py   # Temporal workflow
    activities.py  # Calls public ngrok /run endpoint
    config.py      # Local settings
  requirements.txt
  .env.example
```

## 1. Install

```bash
cd /Users/pryadav/Desktop/Temporal/temporal_new
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

If your Temporal UI runs on `8233`, set this before running the starter:

```bash
export TEMPORAL_UI_URL=http://localhost:8233
```

## 3. Start The Worker

Keep this terminal running:

```bash
cd /Users/pryadav/Desktop/Temporal/temporal_new
source .venv/bin/activate
python -m app.worker
```

Expected log:

```text
Worker running on task queue 'ollama-run-task-queue' for namespace 'default'
```

## 4. Start A Workflow From Terminal

Open another terminal:

```bash
cd /Users/pryadav/Desktop/Temporal/temporal_new
source .venv/bin/activate
python -m app.starter "Explain Temporal in one sentence"
```

Try another input:

```bash
python -m app.starter "Give me three uses of Temporal workflows"
```

Each command starts a new workflow, loads the ngrok endpoint into the workflow input, calls the ngrok Ollama FastAPI through an activity, waits for the result, and prints output like:

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
