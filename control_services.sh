#!/bin/bash
#
# Script to control the OCI MCP Server and Streamlit UI processes.
# Usage: ./control_services.sh [start|stop|restart]
#

# --- Configuration ---
BASE_DIR="/scratch/voggu/oci/OCI-MCP-SmartQueryAI"
MCP_SERVER_CMD="python -m mcp_server.mcp_oci_server"
STREAMLIT_UI_CMD="streamlit run mcp_client/ollama/streamlit_ollama_ui.py --server.address=0.0.0.0 --server.port=8501"

# Function to find the PID (Process ID) of a running command
# We look for the main Python server and the Streamlit UI command line
get_pids() {
    # Check for the OCI Server process (mcp_oci_server)
    SERVER_PID=$(pgrep -f "mcp_server.mcp_oci_server")
    
    # Check for the Streamlit process (streamlit_ollama_ui.py)
    STREAMLIT_PID=$(pgrep -f "streamlit_ollama_ui.py")
}

# --- Stop Function ---
stop_services() {
    get_pids
    
    echo "--- Stopping Services ---"
    
    local stopped=0
    
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID"
        echo "✅ Stopped OCI MCP Server (PID: $SERVER_PID)"
        stopped=1
    else
        echo "ℹ️ OCI MCP Server not running."
    fi
    
    if [ -n "$STREAMLIT_PID" ]; then
        kill "$STREAMLIT_PID"
        echo "✅ Stopped Streamlit UI (PID: $STREAMLIT_PID)"
        stopped=1
    else
        echo "ℹ️ Streamlit UI not running."
    fi
    
    if [ $stopped -eq 0 ]; then
        echo "No processes were running."
    fi
}

# --- Start Function ---
start_services() {
    # 1. Ensure we are in the correct directory
    cd "$BASE_DIR" || { echo "Error: Directory $BASE_DIR not found."; exit 1; }
    
    # 2. Activate the virtual environment only after changing directory
    source .venv/bin/activate || { echo "Error: Failed to activate virtual environment."; exit 1; }
    
    get_pids
    
    echo "--- Starting Services ---"
    
    # 1. Start MCP Server if not running
    if [ -z "$SERVER_PID" ]; then
        # Run in background and pipe stdout/stderr to files (optional, but good practice)
        nohup $MCP_SERVER_CMD > /tmp/mcp_server.log 2>&1 &
        echo "✅ Started OCI MCP Server. Logs in /tmp/mcp_server.log"
    else
        echo "ℹ️ OCI MCP Server is already running (PID: $SERVER_PID)."
    fi
    
    # Wait briefly before starting the UI, ensuring the server is initializing
    sleep 2
    
    # 2. Start Streamlit UI if not running
    if [ -z "$STREAMLIT_PID" ]; then
        # Run in background and pipe stdout/stderr to files
        nohup $STREAMLIT_UI_CMD > /tmp/streamlit_ui.log 2>&1 &
        echo "✅ Started Streamlit UI. Access at http://0.0.0.0:8501. Logs in /tmp/streamlit_ui.log"
    else
        echo "ℹ️ Streamlit UI is already running (PID: $STREAMLIT_PID)."
    fi
}

# --- Main Logic ---
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        # Give services a moment to shut down gracefully
        sleep 3
        start_services
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac

exit 0
