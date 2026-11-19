"""Kartverket's place-name search (api.kartverket.no/stedsnavn), as a Geocoder.

Place-name data © Kartverket, CC BY 4.0. No key or login is needed. What was searched for goes to Kartverket
as the `sok` parameter; nothing else about the owner does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from map_mcp.backends import http
from map_mcp.backends.kartverket_address import LAT_LON, written_as_a_name
from map_mcp.interfaces import Place

if TYPE_CHECKING:
    from map_mcp.backends.http import Limiter, Transport

URL = "https://api.kartverket.no/stedsnavn/v1/navn"
NAME = "kartverket_names"
#: Only what the answer needs, so the service sends less.
FIELDS = "navn.skrivemåte,navn.navneobjekttype,navn.kommuner,navn.representasjonspunkt"
#: The service's kinds the voice has a word for; any other is said as a place.
KINDS = {
    "By": "town",
    "Tettsted": "town",
    "Bygd": "village",
    "Grend": "village",
    "Innsjø": "lake",
    "Vann": "lake",
    "Tjern": "pond",
    "Elv": "river",
    "Fjell": "mountain",
    "Øy": "island",
    "Fjord": "fjord",
    "Gard": "farm",
    "Kommune": "municipality",
}
#: One shared limiter for the service, whichever instance asks.
LIMITER = http.Limiter()


class KartverketNames:
    """Finds places by their name."""

    def __init__(self, *, transport: Transport = http.urllib_transport, limiter: Limiter = LIMITER) -> None:
        """Ask through `transport`, at the pace `limiter` allows."""
        self._transport = transport
        self._limiter = limiter

    async def find(self, what: str) -> list[Place]:
        """The service's places named `what`, best first."""
        params = {"sok": what, "treffPerSide": "10", "utkoordsys": LAT_LON, "filtrer": FIELDS}
        answer = await http.get_json(NAME, URL, params, transport=self._transport, limiter=self._limiter)
        items = answer.get("navn", []) if isinstance(answer, dict) else []
        return [place for place in map(_place, items) if place is not None]


def _place(item: Any) -> Place | None:  # noqa: ANN401 - one item of the service's JSON
    """One place, or None when it lacks a part the voice or the backends need.

    The live service sends its point in the system asked for, with no koordsys beside it (seen
    19.11, though the spec lists one). A koordsys that is there and names another system is
    dropped, since metres read as degrees would put the place far out at sea.
    """
    try:
        point = item["representasjonspunkt"]
        # RULE: an item in another coordinate system is left out
        if str(point.get("koordsys", LAT_LON)) != LAT_LON:
            return None
        municipalities = item.get("kommuner") or []
        return Place(
            name=str(item["skrivemåte"]),
            municipality=written_as_a_name(str(municipalities[0]["kommunenavn"])) if municipalities else "",
            kind=KINDS.get(str(item["navneobjekttype"]), "place"),
            lat=float(point["nord"]),
            lon=float(point["øst"]),
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None
