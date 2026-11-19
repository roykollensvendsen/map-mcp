"""The MCP server: the source's tools, over stdio, for a voice session.

It only puts the core together and names the tools; every answer comes from the service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from map_mcp.service import MapService

#: The Claude app shows a tool by the start of its description, cut at this many characters.
FIRST_LINE_MAX = 78
INSTRUCTIONS = "A made-up source. Read each answer's 'say' aloud as it is."
SIMULATED = "SIMULATED source, not a real one: say so. "
STATUS_DESCRIPTION = (
    "Is the source on, and at what level?\n"
    "Whether the source is switched on, and its level from 0 to 100. It only reads; it changes nothing."
)
#: Every tool, by name. The manifest lists the same, and each has a test file of its own.
TOOLS = ("map_status",)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)


def build_server(service: MapService, *, simulated: bool = False) -> MCPServer[Any]:
    """The MCP server with the source's tools, answering from `service`."""
    server: MCPServer[Any] = MCPServer(
        name="source-simulated" if simulated else "source",
        instructions=(SIMULATED + INSTRUCTIONS) if simulated else INSTRUCTIONS,
    )

    def marked(answer: dict[str, Any]) -> dict[str, Any]:
        answer["simulated"] = simulated
        if simulated:
            answer["say"] = "Simulated: " + answer["say"]
        return answer

    @server.tool(annotations=READ_ONLY, description=STATUS_DESCRIPTION)
    async def map_status() -> dict[str, Any]:
        return marked(await service.status())

    return server
