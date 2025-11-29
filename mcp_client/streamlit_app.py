# streamlit_mcp_ollama_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests
import streamlit as st
from dotenv import load_dotenv

from mcp_client_helper import MCPClientWrapper

# Load environment variables from .env (project root)
load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

# Optional: safety checks so you don't accidentally run with missing config
if not OLLAMA_URL:
    raise RuntimeError("OLLAMA_URL is not set. Please define it in .env or environment.")
if not OLLAMA_MODEL:
    raise RuntimeError("OLLAMA_MODEL is not set. Please define it in .env or environment.")


mcp_client = MCPClientWrapper(server_path="python mcp_oci_server.py")


PLANNER_SYSTEM_PROMPT = """
You are an Oracle Cloud Infrastructure (OCI) assistant.

Your job is to translate natural language into a SINGLE structured JSON command.
The JSON MUST have this exact shape:

{
  "action": "create_instance",
  "compartment_name": "<string>",
  "instance_name": "<string>",
  "instance_shape": "<string or null>",
  "cpu_mem_shape": "<string or null>",
  "subnet_name": "<string or null>"
}

Rules:
- action is always "create_instance" for now.
- If user does not specify shape, set instance_shape to "VM.Standard1.1".
- If user does not specify subnet, set subnet_name to null (the server will pick any).
- compartment_name must be taken from user text (e.g. "test").
- NEVER add extra keys.
- Output ONLY valid JSON. No backticks, no explanation.
"""


def call_ollama_for_plan(user_query: str) -> Dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    content = data["message"]["content"]
    return json.loads(content)


def run_create_instance_flow(plan: Dict[str, Any]) -> Dict[str, Any]:
    # 1. Resolve compartment OCID
    comp_name = plan["compartment_name"]
    instance_name = plan["instance_name"]
    instance_shape = plan.get("instance_shape") or "VM.Standard1.1"
    cpu_mem_shape = plan.get("cpu_mem_shape") or None
    subnet_name = plan.get("subnet_name") or None

    # Compartment OCID
    comp_ocid_content = st.session_state.loop.run_until_complete(
        mcp_client.call_tool(
            "get_compartment_ocid",
            {"compartment_name": comp_name},
        )
    )
    comp_ocid = comp_ocid_content[0].text  # FastMCP returns content parts

    # Subnet OCID (will auto pick if subnet_name is None)
    subnet_ocid_content = st.session_state.loop.run_until_complete(
        mcp_client.call_tool(
            "get_available_subnet",
            {
                "compartment_ocid": comp_ocid,
                "subnet_name": subnet_name,
            },
        )
    )
    subnet_ocid = subnet_ocid_content[0].text

    # Create instance
    instance_content = st.session_state.loop.run_until_complete(
        mcp_client.call_tool(
            "create_compute_instance",
            {
                "compartment_name": comp_name,
                "instance_name": instance_name,
                "instance_shape": instance_shape,
                "cpu_mem_shape": cpu_mem_shape,
                "subnet_name": subnet_name,
            },
        )
    )

    # instance_content should be JSON-serializable
    return instance_content[0].json if hasattr(instance_content[0], "json") else instance_content[0].text


def main() -> None:
    st.set_page_config(page_title="OCI VM Smart Assistant", layout="wide")
    st.title("🔊 OCI VM Smart Assistant (Ollama + MCP)")

    if "loop" not in st.session_state:
        import asyncio

        st.session_state.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(st.session_state.loop)

    st.markdown(
        """
        Type a request like:

        **"create compute instance with the name SMARTVMTEST in compartment test. 
        Take whatever subnet available in the same compartment."**
        """
    )

    user_query = st.text_area("Your request", height=120)

    col1, col2 = st.columns(2)
    with col1:
        run_btn = st.button("Plan & Create VM")
    with col2:
        dry_run = st.checkbox("Dry run (plan only, no VM creation)", value=True)

    if run_btn and user_query.strip():
        with st.spinner("Calling Ollama to plan the action..."):
            plan = call_ollama_for_plan(user_query)

        st.subheader("Planned JSON command")
        st.json(plan)

        if dry_run:
            st.info("Dry run mode: not calling MCP tools.")
        else:
            with st.spinner("Calling MCP tools and OCI..."):
                result = run_create_instance_flow(plan)

            st.subheader("Instance creation result (raw)")
            st.write(result)


if __name__ == "__main__":
    main()
