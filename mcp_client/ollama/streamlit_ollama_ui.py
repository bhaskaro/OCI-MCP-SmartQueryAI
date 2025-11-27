import os
import sys
import asyncio
import json
from typing import Any, Dict, Tuple

import streamlit as st

# ---------------------------------------------------------
# Ensure project root is on sys.path so `mcp_client` is importable
# ---------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Now these imports should work
from mcp_client.mcp_client_helper import MCPClientWrapper
from mcp_client.ollama.smart_ollama_mcp_client import (
    call_ollama_for_plan,
    execute_plan,
)


def run_async(coro):
    """
    Simple helper to run async coroutines from Streamlit.
    Creates a fresh event loop per call to avoid conflicts.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def run_smart_query(user_query: str) -> Tuple[str, Dict[str, Any]]:
    """
    Orchestrates:
      1. Ollama → plan
      2. MCP tools → execution
    Returns:
      console_output (str), execution_result (dict)
    """
    logs: list[str] = []

    logs.append(f"User query:\n{user_query}\n")

    # MCP base URL (HTTP server for your MCP)
    mcp_base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000/mcp")
    client = MCPClientWrapper(base_url=mcp_base_url)

    # 1) Ask Ollama for a plan
    logs.append("Calling Ollama for MCP plan...\n")
    plan = call_ollama_for_plan(user_query)
    logs.append("Generated plan:\n")
    logs.append(json.dumps(plan, indent=2))

    # 2) Execute plan via MCP tools
    logs.append("\nExecuting plan via MCP tools...\n")
    execution_result = run_async(execute_plan(client, plan))

    # Show final variables in console-style output
    variables = execution_result.get("variables", {})
    logs.append("\n========= FINAL VARIABLES =========\n")
    try:
        logs.append(json.dumps(variables, indent=2, default=str))
    except Exception:
        logs.append(str(variables))

    logs.append("\n========= PLAN EXECUTION COMPLETE =========\n")

    console_output = "\n".join(logs)
    return console_output, execution_result


def main():
    st.set_page_config(
        page_title="OCI MCP SmartQuery AI",
        layout="wide",
    )

    # ---------- HEADER ----------
    st.markdown(
        """
        <h1 style="text-align:center; margin-bottom:0.2em;">
            OCI MCP SmartQuery AI
        </h1>
        <p style="text-align:center; margin-top:0;">
            Natural-language & AI-powered orchestration for Oracle Cloud Infrastructure
        </p>
        <hr style="border: 2px solid red; margin-top:0.8em; margin-bottom:1.2em;" />
        """,
        unsafe_allow_html=True,
    )

    # ---------- INPUT AREA ----------
    with st.container():
        prompt = st.text_area(
            "Enter your OCI prompt",
            value="get list of instances from test compartment",
            height=120,
            placeholder=(
                "e.g. create compute instance with the name SMARTVMTEST in compartment "
                "root/test. Take whatever subnet available in the same compartment."
            ),
        )

        col1, col2 = st.columns([1, 3])
        with col1:
            run_button = st.button("Run Smart Query", type="primary")
        with col2:
            st.write("")  # spacing

    # ---------- OUTPUT / CONSOLE ----------
    st.markdown("### Console Output")

    if "console_output" not in st.session_state:
        st.session_state.console_output = ""

    if run_button and prompt.strip():
        with st.spinner("Thinking with Ollama and calling MCP tools..."):
            try:
                console_output, _ = run_smart_query(prompt.strip())
                st.session_state.console_output = console_output
            except Exception as e:
                st.session_state.console_output = (
                    f"Error while executing smart query:\n{e}"
                )

    st.code(
        st.session_state.console_output or "# Console output will appear here…",
        language="bash",
    )

    # ---------- FOOTER ----------
    st.markdown(
        """
        <hr style="border: 2px solid red; margin-top:1.5em; margin-bottom:0.5em;" />
        <div style="text-align:center; font-size:0.9em; color:#555;">
            For technical help, contact <b>Vijaya Bhaskar Oggu</b> at
            <a href="mailto:bhaskaro@yahoo.com">bhaskaro@yahoo.com</a>.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
