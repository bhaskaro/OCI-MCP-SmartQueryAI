import asyncio
import json
import os
import sys
from typing import Any, Dict, List

import requests

from mcp_client.mcp_client_helper import MCPClientWrapper

# ----------------- CONFIG -----------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.1.101:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000/mcp")


# ----------------- OLLAMA PLANNER PROMPT -----------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PLANNER_PROMPT_FILE = os.path.join(CURRENT_DIR, "planner_prompt.txt")


def load_planner_prompt() -> str:
    """Load the planner system prompt from an external text file."""
    if not os.path.exists(PLANNER_PROMPT_FILE):
        raise FileNotFoundError(f"Planner prompt file not found: {PLANNER_PROMPT_FILE}")

    with open(PLANNER_PROMPT_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        raise ValueError("planner_prompt.txt is empty")

    return content


def call_ollama_for_plan(user_query: str) -> Dict[str, Any]:
    """Ask Ollama to produce a JSON plan for MCP tool calls."""
    planner_prompt = load_planner_prompt()

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": user_query},
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
        },
    }

    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Expecting pure JSON as the assistant message content
    content = data["message"]["content"]
    plan = json.loads(content)
    return plan


# ----------------- MCP RESULT HELPERS -----------------


def unwrap_mcp_result(result: Any) -> Any:
    """
    Normalize MCP tool result to a Python object (parsed JSON or simple text).

    Handles:
      - result.structuredContent (preferred), including {"result": X}
      - result.content: possibly multiple content parts
    """
    # Prefer structuredContent if present (often already a dict/list)
    sc = getattr(result, "structuredContent", None)
    if sc is not None:
        # If server uses {"result": X}, unwrap that directly
        if isinstance(sc, dict) and "result" in sc:
            return sc["result"]
        return sc

    content_list = getattr(result, "content", None)
    if content_list:
        parts: List[Any] = []

        for c in content_list:
            text = getattr(c, "text", "")
            if not text:
                continue
            text_str = text.strip()

            # Try JSON parse first
            if text_str.startswith("{") or text_str.startswith("["):
                try:
                    parsed = json.loads(text_str)
                    # Also unwrap {"result": X} here if present
                    if isinstance(parsed, dict) and "result" in parsed:
                        parsed = parsed["result"]
                    parts.append(parsed)
                    continue
                except Exception:
                    # Fall back to raw text if JSON parse fails
                    pass

            parts.append(text_str)

        # Single item → return just that; multiple → return list
        if len(parts) == 1:
            return parts[0]
        return parts

    return None



# ----------------- PLAN EXECUTION -----------------


def resolve_value(value: Any, variables: Dict[str, Any], step_idx: int, key: str) -> Any:
    """
    Resolve references like:
      - "$var"           -> variables["var"]
      - "$var.field"     -> variables["var"]["field"] (if dict)

    Plus convenience:
      - if variables["var"] is {"result": X} and "$var" is used, return X.
    """
    if isinstance(value, str) and value.startswith("$"):
        ref = value[1:]  # strip leading '$'

        # Nested reference: $var.field
        if "." in ref:
            var_name, field = ref.split(".", 1)
            if var_name not in variables:
                raise KeyError(
                    f"Step {step_idx}: variable '{var_name}' not found for arg '{key}'."
                )

            obj = variables[var_name]

            # Explicitly handle null / None
            if obj is None:
                raise ValueError(
                    f"Step {step_idx}: variable '{var_name}' is null, likely because a "
                    f"previous tool (e.g., get_instance_by_name) did not find a result. "
                    f"Cannot access field '{field}' for arg '{key}'."
                )

            if not isinstance(obj, dict):
                raise TypeError(
                    f"Step {step_idx}: variable '{var_name}' is not a dict; "
                    f"cannot access field '{field}'."
                )
            if field not in obj:
                raise KeyError(
                    f"Step {step_idx}: field '{field}' not found in variable '{var_name}'."
                )
            return obj[field]

        # Simple reference: $var
        var_name = ref
        if var_name not in variables:
            raise KeyError(
                f"Step {step_idx}: variable '{var_name}' not found for arg '{key}'."
            )
        obj = variables[var_name]

        # Explicitly handle null / None
        if obj is None:
            raise ValueError(
                f"Step {step_idx}: variable '{var_name}' is null, likely because a "
                f"previous tool did not find a result. Cannot use it for arg '{key}'."
            )

        # Auto-unwrap {"result": X} pattern
        if isinstance(obj, dict) and set(obj.keys()) == {"result"}:
            return obj["result"]

        return obj

    # Non-reference → return as-is
    return value


async def execute_plan(client: MCPClientWrapper, plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the plan generated by Ollama, keeping track of variables and raw step results.
    """
    variables: Dict[str, Any] = {}
    raw_results: List[Dict[str, Any]] = []

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("Plan 'steps' must be a list.")

    for idx, step in enumerate(steps, start=1):
        tool = step.get("tool")
        args = step.get("args", {}) or {}
        save_as = step.get("save_as")

        if not tool:
            raise ValueError(f"Step {idx} missing 'tool'.")

        # Resolve references in args
        resolved_args: Dict[str, Any] = {}
        for key, value in args.items():
            resolved_args[key] = resolve_value(value, variables, idx, key)

        print(f"\n[PLAN] Step {idx}: calling tool '{tool}' with args: {resolved_args}")

        # ---- CALL MCP TOOL ----
        result = await client.call_tool(tool, resolved_args)

        # Raw debug (object type)
        print(f"ollama mcp client [PLAN] raw MCP result type: {type(result)}")

        # ---- UNWRAP RESULT ----
        unwrapped = unwrap_mcp_result(result)

        # Debug: show unwrapped content
        try:
            print(
                "ollama mcp client [PLAN] UNWRAPPED result:\n"
                + json.dumps(unwrapped, indent=2, default=str)
            )
        except Exception:
            print("ollama mcp client [PLAN] UNWRAPPED result (non-JSON):", unwrapped)

        raw_results.append(
            {
                "step": idx,
                "tool": tool,
                "args": resolved_args,
                "raw_result": result,
                "parsed_result": unwrapped,
            }
        )

        # Save to variables if requested
        if isinstance(save_as, str) and save_as.strip():
            # Normalize variable name: strip any leading '$'
            var_name = save_as.lstrip("$")
            variables[var_name] = unwrapped

            # Extra debug: for lists, show length
            if isinstance(unwrapped, list):
                print(
                    f"[PLAN]   Saved result as variable '{var_name}' "
                    f"(list with {len(unwrapped)} items)"
                )
            else:
                print(f"[PLAN]   Saved result as variable '{var_name}'")

    return {
        "variables": variables,
        "steps": raw_results,
    }


# ----------------- PRETTY PRINT HELPERS -----------------


def pretty_print_variable(name: str, value: Any) -> None:
    """
    Nicer printing for common structures:
      - lists of dicts (e.g. images, subnets, instances)
      - everything else via JSON dump.
    """
    print(f"\nVariable: {name}")

    # List of dicts → show summary lines
    if isinstance(value, list) and value and isinstance(value[0], dict):
        print(f"(list of {len(value)} items)")
        for item in value:
            # Try to use common keys if present
            name_val = item.get("name") or item.get("display_name") or ""
            id_val = item.get("id") or item.get("ocid") or ""
            time_val = item.get("time_created") or item.get("timeCreated") or ""
            if name_val or id_val or time_val:
                print(f"- {name_val} | {id_val} | {time_val}")
            else:
                # Fallback to compact JSON if no known keys
                print("- ", json.dumps(item, separators=(",", ":")))
        return

    # Dict / other types → JSON dump if possible
    try:
        print(json.dumps(value, indent=2, default=str))
    except Exception:
        print(value)


# ----------------- SMART ENTRYPOINT -----------------


async def smart_main(user_query: str):
    print(f"User query: {user_query}\n")

    # 1. Ask Ollama to create a plan
    print("Calling Ollama for MCP plan...")
    plan = call_ollama_for_plan(user_query)
    print("\nGenerated plan:\n", json.dumps(plan, indent=2))

    # 2. Create MCP client
    client = MCPClientWrapper(base_url=MCP_BASE_URL)

    # 3. Execute plan
    print("\nExecuting plan via MCP tools...")
    execution_result = await execute_plan(client, plan)

    print("\n========= FINAL VARIABLES =========")
    for name, value in execution_result["variables"].items():
        pretty_print_variable(name, value)

    print("\n========= PLAN EXECUTION COMPLETE =========")


if __name__ == "__main__":
    # Usage:
    #   python -m mcp_client.ollama.smart_ollama_mcp_client
    #   python -m mcp_client.ollama.smart_ollama_mcp_client "create compute instance ..."

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        # Default example query:
        query = (
            "create compute instance with the name SMARTVMTEST in compartment root/test. "
            "Take whatever subnet available in the same compartment."
        )

    asyncio.run(smart_main(query))
