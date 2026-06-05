# AWCP Streamlit UI - Quick Start Guide

## 🚀 Getting Started in 3 Steps

### Step 1: Start Your Backend Services

Ensure these are running:

```bash
# Terminal 1: Start Temporal
temporal server start-dev

# Terminal 2: Start Temporal Worker
cd /path/to/awcp_control_plane
source venv/bin/activate  # or .venv/bin/activate
python -m app.temporal.worker

# Terminal 3: Start FastAPI
cd /path/to/awcp_control_plane
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Step 2: Install Streamlit Dependencies

```bash
cd streamlit_ui
pip install -r requirements.txt
```

### Step 3: Launch the UI

```bash
streamlit run app.py
```

Or use the launcher script:
```bash
bash run.sh
```

The UI will open automatically at `http://localhost:8501`

## 📝 Example Usage

### Example 1: Ask a Question with Web Search

1. Select: **"Ollama Search (Text + Web)"**
2. Enter: *"What is the current price of Bitcoin?"*
3. Click: **"🚀 Run Agent"**
4. Result: Agent will search the web and provide current Bitcoin price

### Example 2: Analyze an Image

1. Select: **"NVIDIA Image Reader (Image Only)"**
2. Click: **"Browse files"** and select an image
3. Click: **"🚀 Analyze Image"**
4. Result: Agent will describe what's in the image

### Example 3: Use Tool-Enabled Agent

1. Select: **"Ollama Web (Tool-enabled)"**
2. Enter: *"Find information about Python 3.12 features"*
3. Click: **"🚀 Run Agent"**
4. Result: See which tools were called and their results

## 🎨 UI Features

### Main Panel
- **Agent Selection**: Dropdown to choose your AI agent
- **Input Area**: Text box or file uploader (depending on agent)
- **Run Button**: Execute the agent with your input
- **Output Section**: Formatted display of results

### Sidebar
- **API Status**: Real-time connection indicator
- **Temporal Stats**: Live workflow metrics
  - Running workflows
  - Completed workflows
  - Failed workflows
- **About**: Quick reference information

## 🔍 Understanding the Output

### Agent Response
The main answer or result from the AI agent.

### Model Information
Which AI model was used (e.g., `llama3.1:8b`, `deepseek-coder`)

### Search Used
Indicates if the agent performed a web search for information.

### Tool Calls
Shows which tools were executed:
- ✅ **succeeded**: Tool ran successfully
- ❌ **failed**: Tool encountered an error

### Workflow Details
- **Workflow ID**: Unique identifier for this execution
- **Run ID**: Temporal run identifier
- **Temporal UI Link**: Click to view detailed execution in Temporal

## 🛠️ Available Agents

| Agent | Input Type | Best For | Tools |
|-------|-----------|----------|-------|
| **Ollama Search** | Text | General questions, current events | Web search |
| **Ollama Web** | Text | Complex queries requiring tools | Multiple tools |
| **DeepSeek** | Text | Code analysis, reasoning | None |
| **NVIDIA Image** | Image | Visual understanding | Image analysis |

## ⚙️ Configuration

### Change API URL

If your FastAPI is running on a different host/port, edit `app.py`:

```python
API_BASE_URL = "http://your-server:port"
```

### Timeout Settings

Default timeout is 120 seconds. To change it, edit the timeout parameter in `app.py`:

```python
response = requests.post(
    f"{API_BASE_URL}/endpoint",
    json={"input": text_input},
    timeout=180  # Change to 180 seconds
)
```

## 🐛 Common Issues

### Issue: "API Disconnected"

**Cause**: FastAPI backend is not running

**Fix**:
```bash
# Check if FastAPI is running
curl http://localhost:8000/health

# If not, start it
cd /path/to/awcp_control_plane
uvicorn app.main:app --reload
```

### Issue: Request Times Out

**Cause**: Temporal worker is not running or agent is slow

**Fix**:
1. Check Temporal worker is running
2. Check ngrok tunnels are active
3. Increase timeout in code

### Issue: Empty Output

**Cause**: Agent returned unexpected format

**Fix**:
1. Check FastAPI logs for errors
2. View workflow in Temporal UI (click the link in output)
3. Verify agent endpoint is working

## 📊 Monitoring

### View Temporal Workflows

Click the "View in Temporal UI" link in the output to see:
- Workflow execution timeline
- Activity details
- Error messages (if any)
- Retry attempts

### Check API Logs

```bash
# FastAPI logs (if running with uvicorn)
# Will show in the terminal where uvicorn is running

# Temporal worker logs
# Will show in the terminal where worker is running
```

## 🎓 Tips & Best Practices

1. **Start Simple**: Begin with basic text queries before trying complex tasks
2. **Monitor Status**: Keep an eye on the sidebar stats
3. **Use Temporal UI**: When debugging, the Temporal UI link is invaluable
4. **Check Tool Calls**: For tool-enabled agents, verify which tools were used
5. **Save Workflow IDs**: Copy workflow IDs for future reference

## 🔄 Workflow

```
User Input → Streamlit UI → FastAPI → Temporal → AI Agent → Response
    ↑                                                            ↓
    └────────────────────────────────────────────────────────────┘
```

## 📞 Getting Help

1. **Check README.md**: Detailed documentation
2. **Review Troubleshooting**: Common issues and solutions
3. **Temporal UI**: Detailed workflow execution information
4. **FastAPI Docs**: Visit `http://localhost:8000/docs` for API documentation

## 🎉 You're Ready!

Now you can:
- ✅ Run AI agents through a friendly UI
- ✅ Monitor workflow execution
- ✅ View detailed results
- ✅ Debug issues using Temporal UI

Happy agent orchestration! 🤖
