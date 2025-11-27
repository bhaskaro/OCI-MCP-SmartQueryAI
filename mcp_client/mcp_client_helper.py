# mcp_client/mcp_client_helper.py
from __future__ import annotations

from typing import Any, Dict

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class MCPClientWrapper:
    """
    Minimal MCP client wrapper that connects to the OCI MCP server
    over Streamable HTTP transport.
    """

    def __init__(self, base_url: str = "http://localhost:8000/mcp") -> None:
        self.base_url = base_url

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Call a tool by name with JSON-serializable args and return the raw ToolResult.
        """
        # NOTE: streamablehttp_client yields (read, write, close_handle)
        async with streamablehttp_client(self.base_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=args)
                return result
