"""Command line for map-mcp: serve the tools, or find one address or place, as the voice hears it."""

from __future__ import annotations

import argparse
import asyncio
import functools
import sys
from typing import TYPE_CHECKING

from map_mcp import settings
from map_mcp.fake import FakeKartverket, FakeNearby
from map_mcp.service import MapService

if TYPE_CHECKING:
    from map_mcp.backends.kartverket import Kartverket

#: Every verb this command has.
COMMANDS: tuple[str, ...] = ("serve", "find")
#: Help is laid out at one width on every terminal, so a page's copy of it stays true.
HELP = functools.partial(argparse.HelpFormatter, width=100)


def geocoder(*, simulate: bool) -> Kartverket | FakeKartverket:
    """Kartverket itself, or the made-up places when the run is simulated."""
    if simulate:
        return FakeKartverket()
    # The HTTP layer is a slow import, and a simulated run never needs it.
    from map_mcp.backends.kartverket import Kartverket  # noqa: PLC0415

    return Kartverket()


def places(*, simulate: bool) -> FakeNearby | None:
    """The made-up nearby places when the run is simulated; a real run has none until OpenStreetMap's backend."""
    return FakeNearby() if simulate else None


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="map-mcp", description=__doc__, formatter_class=HELP)
    verbs = parser.add_subparsers(dest="command", required=True)
    serve = verbs.add_parser("serve", formatter_class=HELP, help="serve the tools over stdio, for a voice session")
    find = verbs.add_parser("find", formatter_class=HELP, help="find an address or place, as the voice hears it")
    find.add_argument("what", help="the address or place name to look for")
    for verb in (serve, find):
        verb.add_argument("--simulate", action="store_true", help="answer from the made-up places")
    args = parser.parse_args(argv)
    try:
        configured = settings.load()
    except settings.SettingsError as broken:
        sys.stderr.write(f"{broken}\n")
        return 2
    simulate = args.simulate or configured.simulate
    service = MapService(geocoder(simulate=simulate), places(simulate=simulate))

    # The MCP server is a slow import, and only a working command needs it.
    from mcp.types import CallToolResult  # noqa: PLC0415

    from map_mcp.server import build_server  # noqa: PLC0415

    server = build_server(service, simulated=simulate)
    if args.command == "find":
        # Through the tool itself, so this says exactly what the voice would hear.
        result = asyncio.run(server.call_tool("map_find", {"what": args.what}))
        answer = result.structured_content if isinstance(result, CallToolResult) else None
        sys.stdout.write(str((answer or {}).get("say", "")) + "\n")
        return 0
    server.run("stdio")  # pragma: no cover - runs until stdin closes
    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
