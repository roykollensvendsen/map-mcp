"""The MCP server: the map's tools, over stdio, for a voice session.

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
INSTRUCTIONS = (
    "Addresses and places in Norway, by name. Read each answer's 'say' aloud as it is. "
    "When it lists several matches, ask which one was meant. Address data © Kartverket."
)
SIMULATED = "SIMULATED map, with made-up places only: say so. "
FIND_DESCRIPTION = (
    "Where is an address or a place, and in which municipality?\n"
    "Finds an address or a place name, such as a town or a lake, and says its municipality and "
    "kind. With several matches it names the first three, so you can ask which one was meant. "
    "It only reads; it changes nothing. Address data © Kartverket."
)
NEARBY_DESCRIPTION = (
    "What's near a place, such as the nearest grocery or charger?\n"
    "Names the nearest three of one kind near an address or place name, each with its distance "
    "in a straight line. 'what' is one of: shop, grocery, charging, fuel, parking, toilet, cafe, "
    "bus stop. It looks 15 km out for a grocery, fuel or charging, and 3 km for the rest; "
    "'within_km' looks less far. It only reads; it changes nothing. "
    "Map data © OpenStreetMap contributors, ODbL."
)
#: Every tool, by name. The manifest lists the same, and each has a test file of its own.
TOOLS = ("map_find", "map_nearby")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)


def build_server(service: MapService, *, simulated: bool = False) -> MCPServer[Any]:
    """The MCP server with the map's tools, answering from `service`."""
    server: MCPServer[Any] = MCPServer(
        name="map-simulated" if simulated else "map",
        instructions=(SIMULATED + INSTRUCTIONS) if simulated else INSTRUCTIONS,
    )

    def marked(answer: dict[str, Any]) -> dict[str, Any]:
        answer["simulated"] = simulated
        if simulated:
            answer["say"] = "Simulated: " + answer["say"]
        return answer

    @server.tool(annotations=READ_ONLY, description=FIND_DESCRIPTION)
    async def map_find(what: str) -> dict[str, Any]:
        return marked(await service.find(what))

    @server.tool(annotations=READ_ONLY, description=NEARBY_DESCRIPTION)
    async def map_nearby(what: str, near: str, within_km: float | None = None) -> dict[str, Any]:
        return marked(await service.nearby(what, near, within_km))

    return server
