"""Kartverket as one Geocoder: its address search and its place-name search, asked together.

Addresses come first, since a street and number is the likelier meaning when both match. When
one service fails and the other finds places, those places stand. When no place was found and
a service failed, the failure is said: "nothing found" would be untrue when a search never ran.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from map_mcp.backends.kartverket_address import KartverketAddress
from map_mcp.backends.kartverket_names import KartverketNames

if TYPE_CHECKING:
    from map_mcp.interfaces import Place


class Kartverket:
    """Finds addresses and places by name, from both of Kartverket's searches."""

    def __init__(self, *, addresses: KartverketAddress | None = None, names: KartverketNames | None = None) -> None:
        """Ask `addresses` and `names`, each Kartverket's own by default."""
        self._addresses = addresses or KartverketAddress()
        self._names = names or KartverketNames()

    async def find(self, what: str) -> list[Place]:
        """Addresses for `what`, then places named `what`."""
        answers = await asyncio.gather(self._addresses.find(what), self._names.find(what), return_exceptions=True)
        places = [place for answer in answers if isinstance(answer, list) for place in answer]
        failed = [answer for answer in answers if isinstance(answer, BaseException)]
        # RULE: when one service fails the other still answers
        if failed and not places:
            raise failed[0]
        return places
