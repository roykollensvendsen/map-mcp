"""The core: ask the backends, and word every answer for the voice.

It knows no MCP. Every answer is a dict with `success`, an `outcome` and a `say`, the
sentence the voice reads aloud as it is, and it has one even when a backend fails. An answer
names places; it never carries a position.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from map_mcp.interfaces import BusyError, NotSetUpError, QueryError, UnconnectedPlaces, UnreachableError, metres

if TYPE_CHECKING:
    from map_mcp.interfaces import Geocoder, Nearby, Place, Places

UNREACHABLE = "Kartverket isn't answering. Try again in a minute."
NOT_SET_UP = "No address service is set up yet, so nothing was asked."
NO_QUERY = "Say an address or a place name to look for."
BROKE = "That went wrong inside map-mcp. Try again, and if it fails again, check its log."
#: How many matches the voice reads before it asks which one was meant.
READ_OUT = 3
#: map-mcp's own pacing waits under a second, too short to count aloud.
BUSY_A_MOMENT = "Kartverket is busy for a moment; ask again."  # what _busy says for a short wait
#: "here" needs the phone's position, which comes with the bridge_phone backend.
HERE_UNKNOWN = "Where you are isn't known here; say a place instead."
NEARBY_NOT_SET_UP = "No nearby-places service is set up yet, so nothing was asked."
#: The closed list a nearby search takes: each kind's word for one, for several, and how far
#: out in km it is looked for. Errands by car reach further than a walk to a cafe.
KINDS = {
    "shop": ("shop", "shops", 3),
    "grocery": ("grocery", "groceries", 15),
    "charging": ("charger", "chargers", 15),
    "fuel": ("fuel station", "fuel stations", 15),
    "parking": ("parking place", "parking places", 3),
    "toilet": ("toilet", "toilets", 3),
    "cafe": ("cafe", "cafes", 3),
    "bus stop": ("bus stop", "bus stops", 3),
}


class MapService:
    """What the tools ask, answered from the backends."""

    def __init__(self, geocoder: Geocoder, places: Places | None = None) -> None:
        """Answer from `geocoder` and `places`, each the fake or a real one; no places says so."""
        self._geocoder = geocoder
        self._places: Places = places or UnconnectedPlaces()

    async def nearby(self, what: str, near: str, within_km: float | None = None) -> dict[str, Any]:
        """The nearest three places of a kind near a named place, by name and distance."""
        kind = what.strip().casefold().replace("_", " ")
        within = _reach(kind, within_km)
        if isinstance(within, dict):
            return within
        origin = await self._origin(near.strip())
        if isinstance(origin, dict):
            return origin
        found = await self._around(kind, origin, within)
        if isinstance(found, dict):
            return found
        return _nearby(kind, origin, within, found, self._places.attribution)

    async def _origin(self, near: str) -> Place | dict[str, Any]:
        """The place to look near: the best match for its name, or the answer that says why not."""
        if near.casefold() == "here":
            return _failed("no_position", HERE_UNKNOWN)
        places = await self._search(near)
        if isinstance(places, dict):
            return places
        if not places:
            return _failed("not_found", f"I found no address or place called {near}.")
        return places[0]

    async def _around(self, kind: str, origin: Place, within_km: float) -> list[Nearby] | dict[str, Any]:
        """The places service's answer, or the failed answer that says why there is none."""
        service = self._places.service
        try:
            return await self._places.nearby(kind, origin.lat, origin.lon, within_km * 1000)
        except BusyError as busy:
            return _failed("busy", _busy(busy.seconds, service))
        except UnreachableError:
            return _failed("unreachable", f"{service} isn't answering. Try again in a minute.")
        except NotSetUpError:
            return _failed("not_set_up", NEARBY_NOT_SET_UP)
        # RULE: a broken places service still gives a sentence to say
        except Exception:  # noqa: BLE001 - whatever broke near a place, the voice gets a sentence
            return _failed("broke", BROKE)

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


def _busy(seconds: float, service: str = "Kartverket") -> str:
    """A wait under a second with no number, since it is gone before it is said; a longer one in seconds."""
    # RULE: our own short wait is said with no number and a service's wait in seconds
    if seconds < 1:
        return f"{service} is busy for a moment; ask again."
    return f"{service} is busy; try again in {_seconds(seconds)}."


def _the_kinds() -> str:
    """The closed list, read out, so the voice can ask which one."""
    kinds = list(KINDS)
    return f"I can look for a {', '.join(kinds[:-1])} or {kinds[-1]}. Which one?"


def _reach(kind: str, within_km: float | None) -> float | dict[str, Any]:
    """How far out to look: the kind's own reach, or less when asked; further, or a kind off the list, is refused."""
    if kind not in KINDS:
        return _failed("unknown_kind", _the_kinds())
    one, _, reach = KINDS[kind]
    within = reach if within_km is None else within_km
    # RULE: a reach past the kind's own is refused with the fix
    if within > reach:
        return _failed("too_far", f"I look at most {reach} km out for a {one}; ask for {reach} km or less.")
    return within


def _nearby(kind: str, origin: Place, within_km: float, found: list[Nearby], attribution: str) -> dict[str, Any]:
    """The answer: the nearest three by distance, with names and metres only, never a position."""
    # RULE: the nearest three are said by name and distance
    ranked = sorted(((metres(origin.lat, origin.lon, n.lat, n.lon), n) for n in found), key=_first)[:READ_OUT]
    return {
        "success": True,
        "outcome": "found" if ranked else "none_near",
        "nearby": [{"name": n.name, "metres": round(m)} for m, n in ranked],
        "attribution": attribution,
        "say": _near(kind, origin.name, within_km, ranked),
    }


def _first(pair: tuple[float, Nearby]) -> float:
    return pair[0]


def _near(kind: str, origin: str, within_km: float, ranked: list[tuple[float, Nearby]]) -> str:
    """The nearest one on its own, several as a list, or none within the reach."""
    one, several, _ = KINDS[kind]
    if not ranked:
        return f"None within {within_km:g} km of {origin}."
    if len(ranked) == 1:
        far, found = ranked[0]
        return f"The nearest {one} to {origin} is {_named(found)}, {_distance(far)} away."
    listed = "; ".join(f"{_named(found)}, {_distance(far)}" for far, found in ranked)
    return f"The nearest {several} to {origin}: {listed}."


def _named(found: Nearby) -> str:
    return found.name or "one with no name"


def _distance(far: float) -> str:
    """Metres to the nearest ten under a kilometre, then kilometres to one decimal."""
    if far < 1000:  # noqa: PLR2004 - a kilometre
        return f"{round(far, -1):.0f} m"
    return f"{far / 1000:.1f} km"


def _seconds(seconds: float) -> str:
    whole = max(1, math.ceil(seconds))
    return f"{whole} second" if whole == 1 else f"{whole} seconds"


def _failed(outcome: str, say: str) -> dict[str, Any]:
    return {"success": False, "outcome": outcome, "say": say}
