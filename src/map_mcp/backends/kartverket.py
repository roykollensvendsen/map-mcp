"""Kartverket as one Geocoder: its address search and its place-name search, asked together.

Addresses come first, since a street and number is the likelier meaning when both match. When
one service fails, the other's answer still stands; only when both fail is the failure said.
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
        found = [answer for answer in answers if isinstance(answer, list)]
        # RULE: when one service fails the other still answers
        if not found:
            raise next(answer for answer in answers if isinstance(answer, BaseException))
        return [place for answer in found for place in answer]
