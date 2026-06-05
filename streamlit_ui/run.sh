#!/bin/bash

# AWCP Streamlit UI Launcher
# This script starts the Streamlit interface for the AWCP Control Plane

echo "🤖 Starting AWCP Streamlit UI..."
echo ""
echo "Prerequisites:"
echo "1. FastAPI backend should be running on http://localhost:8000"
echo "2. Temporal server and worker should be active"
echo ""

# Check if FastAPI is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ FastAPI backend is accessible"
else
    echo "⚠️  Warning: FastAPI backend not detected at http://localhost:8000"
    echo "   Make sure to start it before using the UI"
fi

echo ""
echo "Starting Streamlit..."
echo "---"

# Run Streamlit
streamlit run app.py
