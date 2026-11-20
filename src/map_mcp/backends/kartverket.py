"""Kartverket as one Geocoder: its address search and its place-name search, asked together.

Addresses come first, since a street and number is the likelier meaning when both match. When
one service fails and the other finds places, those places stand. When no place was found and
a service failed, the failure is said: "nothing found" would be untrue when a search never ran.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from map_mcp.backends.kartverket_address import KartverketAddress
from map_mcp.backends.kartverket_names import KartverketNames

if TYPE_CHECKING:
    from collections.abc import Sequence

    from map_mcp.interfaces import Place

log = logging.getLogger("map_mcp.backends")
#: What each search is called in the log, in the order they are asked.
SEARCHES = ("address search", "place-name search")


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
        failed = _failures(answers)
        # RULE: when one service fails the other still answers
        if failed and not places:
            raise failed[0][1]
        _log_behind_places(failed)
        return places


def _failures(answers: Sequence[object]) -> list[tuple[str, BaseException]]:
    """Each search that failed, named, with its failure, in the order they were asked."""
    return [
        (search, answer) for search, answer in zip(SEARCHES, answers, strict=True) if isinstance(answer, BaseException)
    ]


def _log_behind_places(failed: list[tuple[str, BaseException]]) -> None:
    """Log each failed search whose failure the other search's places would otherwise hide."""
    for search, failure in failed:
        # Only the kind of failure: its message may hold what was asked.
        # RULE: a failure behind places found is still logged
        log.warning("%s failed: %s; the other search answered", search, type(failure).__name__)
