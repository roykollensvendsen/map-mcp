"""The core: ask the backends, and word every answer for the voice.

It knows no MCP. Every answer is a dict with `success`, an `outcome` and a `say`, the
sentence the voice reads aloud as it is, and it has one even when a backend fails. An answer
names places; it never carries a position.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from map_mcp.interfaces import BusyError, NotSetUpError, QueryError, UnreachableError

if TYPE_CHECKING:
    from map_mcp.interfaces import Geocoder, Place

UNREACHABLE = "Kartverket isn't answering. Try again in a minute."
NOT_SET_UP = "No address service is set up yet, so nothing was asked."
NO_QUERY = "Say an address or a place name to look for."
BROKE = "That went wrong inside map-mcp. Try again, and if it fails again, check its log."
#: How many matches the voice reads before it asks which one was meant.
READ_OUT = 3
#: map-mcp's own pacing waits under a second, too short to count aloud.
BUSY_A_MOMENT = "Kartverket is busy for a moment; ask again."


class MapService:
    """What the tools ask, answered from the backends."""

    def __init__(self, geocoder: Geocoder) -> None:
        """Answer from `geocoder`, the fake or a real one."""
        self._geocoder = geocoder

    async def find(self, what: str) -> dict[str, Any]:
        """The best match for an address or place name, or the top few when there are several."""
        what = what.strip()
        if not what:
            return _failed("no_query", NO_QUERY)
        places = await self._search(what)
        if isinstance(places, dict):
            return places
        if not places:
            return _failed("not_found", f"I found no address or place called {what}.")
        # RULE: several matches are read as the top three
        read = places[:READ_OUT]
        return {
            "success": True,
            "outcome": "found",
            "matches": [{"name": p.name, "municipality": p.municipality, "kind": p.kind} for p in read],
            "say": _found(places, read),
        }

    async def _search(self, what: str) -> list[Place] | dict[str, Any]:
        """The geocoder's matches, or the failed answer that says why there are none."""
        try:
            return await self._geocoder.find(what)
        except BusyError as busy:
            return _failed("busy", _busy(busy.seconds))
        except UnreachableError:
            return _failed("unreachable", UNREACHABLE)
        except QueryError:
            return _failed("no_query", NO_QUERY)
        except NotSetUpError:
            return _failed("not_set_up", NOT_SET_UP)
        # RULE: every answer has a sentence to say even when a backend fails
        except Exception:  # noqa: BLE001 - whatever broke, the voice gets a sentence
            return _failed("broke", BROKE)


def _found(places: list[Place], read: list[Place]) -> str:
    """One match as itself; several as a list to choose from."""
    if len(places) == 1:
        return f"{_label(places[0])}."
    listed = "; ".join(_label(p) for p in read)
    if len(places) > len(read):
        return f"{len(places)} matches; the first three: {listed}. Which one?"
    return f"{len(places)} matches: {listed}. Which one?"


def _label(place: Place) -> str:
    """An address with its municipality; a town as a town; any other place with where it lies."""
    if place.kind == "address":
        return f"{place.name}, {place.municipality}"
    if place.name == place.municipality:
        return f"{place.name}, a {place.kind}"
    return f"{place.name}, a {place.kind} in {place.municipality}"


def _busy(seconds: float) -> str:
    """A wait under a second with no number, since it is gone before it is said; a longer one in seconds."""
    # RULE: our own short wait is said with no number and a service's wait in seconds
    if seconds < 1:
        return BUSY_A_MOMENT
    return f"Kartverket is busy; try again in {_seconds(seconds)}."


def _seconds(seconds: float) -> str:
    whole = max(1, math.ceil(seconds))
    return f"{whole} second" if whole == 1 else f"{whole} seconds"


def _failed(outcome: str, say: str) -> dict[str, Any]:
    return {"success": False, "outcome": outcome, "say": say}
