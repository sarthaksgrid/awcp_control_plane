"""
AWCP Streamlit UI - Agent Workforce Control Plane Interface

This UI provides an interface to interact with the AWCP FastAPI backend,
allowing users to run different AI agents with appropriate inputs (text, image, document).
"""

import streamlit as st
import requests
import json
from typing import Optional, Dict, Any
from io import BytesIO

# Configuration
API_BASE_URL = "http://localhost:8000"

# Page configuration
st.set_page_config(
    page_title="AWCP Control Plane",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
        color: #1E88E5;
    }
    .agent-card {
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
        background-color: #f5f5f5;
    }
    .status-success {
        color: #4CAF50;
        font-weight: bold;
    }
    .status-error {
        color: #f44336;
        font-weight: bold;
    }
    .output-box {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)


def check_api_health() -> bool:
    """Check if the FastAPI backend is accessible."""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_agents() -> Optional[list]:
    """Fetch available agents from the API."""
    try:
        response = requests.get(f"{API_BASE_URL}/agents", timeout=10)
        if response.status_code == 200:
            data = response.json()
            # The API returns {"total_agents": N, "agents": [...]}
            return data.get("agents", [])
        return None
    except Exception as e:
        st.error(f"Failed to fetch agents: {str(e)}")
        return None


def run_ollama_search(input_text: str) -> Dict[str, Any]:
    """Call the Ollama search endpoint."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/run-ollama-api-web",
            json={"input": input_text},
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API Error: {str(e)}")


def run_deepseek_search(input_text: str) -> Dict[str, Any]:
    """Call the DeepSeek search endpoint."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/deepseek-search",
            json={"input": input_text},
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API Error: {str(e)}")


def run_nvidia_image_read(image_file) -> Dict[str, Any]:
    """Call the NVIDIA image read endpoint."""
    try:
        files = {"image": (image_file.name, image_file, image_file.type)}
        response = requests.post(
            f"{API_BASE_URL}/nvidia-image-read",
            files=files,
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API Error: {str(e)}")


def run_ollama_web(input_text: str) -> Dict[str, Any]:
    """Call the Ollama web search endpoint (tool-enabled)."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/run-ollama-api-web",
            json={"input": input_text},
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API Error: {str(e)}")


def get_temporal_stats() -> Optional[Dict[str, int]]:
    """Fetch Temporal workflow statistics."""
    try:
        response = requests.get(f"{API_BASE_URL}/workflow-stats", timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None


def display_output(result: Dict[str, Any]):
    """Display the agent execution output in a formatted way."""
    st.markdown("### 📤 Output")
    
    with st.expander("🔍 **Full Response**", expanded=True):
        # Extract relevant information
        output = result.get("output", {})
        body = output.get("body", {})
        
        # Display main output/answer
        if isinstance(body, dict):
            if "output" in body:
                st.markdown("#### Agent Response:")
                st.success(body["output"])
            elif "answer" in body:
                st.markdown("#### Agent Response:")
                st.success(body["answer"])
            
            # Display model used
            if "model" in body:
                st.info(f"🤖 **Model:** {body['model']}")
            
            # Display search information if available
            if body.get("search_used"):
                st.warning(f"🔎 **Search Used:** Yes")
                if "search_query" in body:
                    st.info(f"📝 **Search Query:** {body['search_query']}")
            
            # Display tool calls if available
            if "tool_calls" in body and body["tool_calls"]:
                st.markdown("#### 🛠️ Tool Calls:")
                for tool in body["tool_calls"]:
                    with st.container():
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.write(f"**Tool:** {tool.get('tool_name', 'unknown')}")
                        with col2:
                            status = tool.get('status', 'unknown')
                            if status == "succeeded":
                                st.markdown(f'<span class="status-success">✅ {status}</span>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<span class="status-error">❌ {status}</span>', unsafe_allow_html=True)
        else:
            st.write(body)
    
    # Workflow information
    with st.expander("ℹ️ **Workflow Details**"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Workflow ID:** `{result.get('workflow_id', 'N/A')}`")
            st.write(f"**Run ID:** `{result.get('run_id', 'N/A')}`")
        with col2:
            st.write(f"**Endpoint:** `{result.get('ngrok_endpoint', 'N/A')}`")
            if "temporal_ui_url" in result:
                st.markdown(f"[🔗 View in Temporal UI]({result['temporal_ui_url']})")


def main():
    """Main Streamlit application."""
    
    # Header
    st.markdown('<div class="main-header">🤖 AWCP Control Plane</div>', unsafe_allow_html=True)
    st.markdown("**Agent Workforce Control Plane** - Execute AI agents with Temporal orchestration")
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 🎛️ Control Panel")
        
        # API Health Check
        if check_api_health():
            st.success("✅ API Connected")
        else:
            st.error("❌ API Disconnected")
            st.warning(f"Make sure FastAPI is running at {API_BASE_URL}")
            return
        
        # Temporal Stats
        st.markdown("### 📊 Temporal Stats")
        stats = get_temporal_stats()
        if stats:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Running", stats.get("running", 0))
            with col2:
                st.metric("Completed", stats.get("completed", 0))
            with col3:
                st.metric("Failed", stats.get("failed", 0))
        else:
            st.info("Unable to fetch stats")
        
        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.markdown("""
        This interface allows you to interact with various AI agents:
        - **Ollama Search**: Text-based agent with web search
        - **DeepSeek**: Advanced text processing
        - **NVIDIA Image**: Image analysis
        """)
    
    # Main content
    st.markdown("## 🎯 Select Agent & Input")
    
    # Agent selection
    agent_type = st.selectbox(
        "Choose Agent Type:",
        [
            "Ollama Search (Text + Web)",
            "Ollama Web (Tool-enabled)",
            "DeepSeek (Text Only)",
            "NVIDIA Image Reader (Image Only)"
        ],
        help="Select the agent you want to use"
    )
    
    st.markdown("---")
    
    # Input section based on agent type
    if "Image" in agent_type:
        st.markdown("### 📷 Upload Image")
        uploaded_file = st.file_uploader(
            "Choose an image file",
            type=["png", "jpg", "jpeg", "webp"],
            help="Upload an image for analysis"
        )
        
        if uploaded_file:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(uploaded_file, caption="Uploaded Image", use_column_width=True)
            with col2:
                st.info(f"**Filename:** {uploaded_file.name}")
                st.info(f"**Type:** {uploaded_file.type}")
                st.info(f"**Size:** {uploaded_file.size / 1024:.2f} KB")
        
        if st.button("🚀 Analyze Image", type="primary", use_container_width=True):
            if uploaded_file:
                with st.spinner("🔄 Processing image..."):
                    try:
                        result = run_nvidia_image_read(uploaded_file)
                        st.success("✅ Image analyzed successfully!")
                        display_output(result)
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("⚠️ Please upload an image first")
    
    else:
        st.markdown("### ✍️ Text Input")
        text_input = st.text_area(
            "Enter your query:",
            height=150,
            placeholder="Type your question or request here...",
            help="Enter the text you want to process"
        )
        
        if st.button("🚀 Run Agent", type="primary", use_container_width=True):
            if text_input.strip():
                with st.spinner("🔄 Processing request..."):
                    try:
                        # Route to appropriate endpoint
                        if "Ollama Search" in agent_type:
                            result = run_ollama_search(text_input)
                        elif "Ollama Web" in agent_type:
                            result = run_ollama_web(text_input)
                        elif "DeepSeek" in agent_type:
                            result = run_deepseek_search(text_input)
                        else:
                            st.error("Unknown agent type")
                            return
                        
                        st.success("✅ Request completed successfully!")
                        display_output(result)
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("⚠️ Please enter some text first")
    
    # Footer
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; color: #666;">AWCP Control Plane v1.0 | '
        'Powered by Temporal & FastAPI</div>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
