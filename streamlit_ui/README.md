# AWCP Streamlit UI

A user-friendly interface for the Agent Workforce Control Plane (AWCP) that allows you to interact with various AI agents through a web interface.

## Features

- **Multiple Agent Support**: Interface for Ollama, DeepSeek, and NVIDIA Image agents
- **Dynamic Input Types**: 
  - Text input for language models
  - Image upload for vision models
- **Real-time Status**: 
  - API health monitoring
  - Temporal workflow statistics
- **Detailed Output Display**: 
  - Formatted agent responses
  - Tool call tracking
  - Workflow information with links to Temporal UI

## Setup

### Prerequisites

1. **FastAPI Backend Running**: Make sure your AWCP FastAPI server is running on `http://localhost:8000`
2. **Temporal Worker Running**: Ensure your Temporal worker is active
3. **Python 3.8+**: Required for Streamlit

### Installation

1. Navigate to the streamlit_ui directory:
```bash
cd streamlit_ui
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the UI

Start the Streamlit application:
```bash
streamlit run app.py
```

The UI will open in your default browser at `http://localhost:8501`

## Usage

### 1. Check API Connection

When you open the UI, the sidebar will show:
- ✅ **API Connected** - Backend is accessible
- ❌ **API Disconnected** - Backend is not running

### 2. Select Agent Type

Choose from available agents:

#### **Ollama Search (Text + Web)**
- Text-based queries
- Web search capability
- Best for: General questions requiring real-time information

#### **Ollama Web (Tool-enabled)**
- Advanced tool-calling capabilities
- Web search integration
- Displays tool execution details

#### **DeepSeek (Text Only)**
- Advanced text processing
- No external tools
- Best for: Code analysis, reasoning tasks

#### **NVIDIA Image Reader (Image Only)**
- Image analysis and description
- Supports: PNG, JPG, JPEG, WebP
- Best for: Visual understanding tasks

### 3. Provide Input

**For Text Agents:**
- Enter your query in the text area
- Click "🚀 Run Agent"

**For Image Agent:**
- Upload an image file
- Preview appears automatically
- Click "🚀 Analyze Image"

### 4. View Results

The output section displays:

- **Agent Response**: Main answer or output
- **Model Used**: Which AI model processed the request
- **Search Info**: If web search was used
- **Tool Calls**: Details of any tools executed
- **Workflow Details**: Temporal workflow information with UI link

### 5. Monitor Temporal Workflows

The sidebar shows real-time statistics:
- **Running**: Currently executing workflows
- **Completed**: Successfully finished workflows
- **Failed**: Workflows that encountered errors

## Configuration

### Changing API Base URL

Edit the `API_BASE_URL` variable in `app.py`:

```python
API_BASE_URL = "http://your-api-server:8000"
```

### Customizing Agents

To add new agents:

1. Add the agent endpoint in your FastAPI backend
2. Create a new function in `app.py` to call the endpoint
3. Add the agent option to the selectbox
4. Add routing logic in the button handler

## Troubleshooting

### "API Disconnected" Error

**Problem**: Cannot connect to FastAPI backend

**Solutions**:
- Verify FastAPI is running: `curl http://localhost:8000/health`
- Check if port 8000 is in use by another application
- Ensure no firewall is blocking the connection

### "Timeout Error" When Running Agent

**Problem**: Request takes too long

**Solutions**:
- Check if Temporal worker is running
- Verify ngrok tunnels are active (if using remote agents)
- Increase timeout in the request functions (currently 120 seconds)

### Image Upload Fails

**Problem**: Cannot upload image

**Solutions**:
- Verify image format (PNG, JPG, JPEG, WebP only)
- Check image file size (shouldn't be too large)
- Ensure FastAPI endpoint `/nvidia-image-read` is accessible

### Output Not Displaying Correctly

**Problem**: Output section is empty or malformed

**Solutions**:
- Check browser console for JavaScript errors
- Verify API response structure matches expected format
- Clear Streamlit cache: `streamlit cache clear`

## Architecture

```
┌─────────────────┐
│  Streamlit UI   │
│  (Port 8501)    │
└────────┬────────┘
         │ HTTP Requests
         ▼
┌─────────────────┐
│   FastAPI       │
│  (Port 8000)    │
└────────┬────────┘
         │ Temporal Workflows
         ▼
┌─────────────────┐
│   Temporal      │
│   Server        │
└────────┬────────┘
         │ Activity Execution
         ▼
┌─────────────────┐
│  AI Agents      │
│ (Ollama, etc.)  │
└─────────────────┘
```

## Development

### Project Structure

```
streamlit_ui/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

### Adding New Features

1. **New Agent Type**:
   - Add endpoint function (e.g., `run_new_agent()`)
   - Update agent selection dropdown
   - Add routing logic in button handler

2. **Custom Input Type**:
   - Add input widget (e.g., document uploader)
   - Create corresponding API call function
   - Update UI layout

3. **Enhanced Output Display**:
   - Modify `display_output()` function
   - Add new expanders or columns
   - Format data presentation

## Best Practices

1. **Always check API health** before running agents
2. **Use appropriate agent** for your task type
3. **Monitor Temporal stats** for system health
4. **Keep queries concise** for faster responses
5. **Use Temporal UI link** to debug workflow issues

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Verify all services are running (FastAPI, Temporal, Worker)
3. Review logs in Temporal UI for detailed error information

## License

This UI is part of the AWCP Control Plane project.
