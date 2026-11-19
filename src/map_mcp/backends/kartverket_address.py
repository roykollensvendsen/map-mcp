"""Kartverket's address search (ws.geonorge.no/adresser), as a Geocoder.

Address data © Kartverket, CC BY 4.0. No key or login is needed. What was searched for goes to
Kartverket as the `sok` parameter; nothing else about the owner does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from map_mcp.backends import http
from map_mcp.interfaces import Place

if TYPE_CHECKING:
    from map_mcp.backends.http import Limiter, Transport

URL = "https://ws.geonorge.no/adresser/v1/sok"
NAME = "kartverket_address"
#: Kartverket's own number for latitude and longitude (ETRS89), so the point needs no conversion.
LAT_LON = "4258"
#: Only what the answer needs, so the service sends less.
FIELDS = "adresser.adressetekst,adresser.kommunenavn,adresser.representasjonspunkt"
#: One shared limiter for the service, whichever instance asks.
LIMITER = http.Limiter()


class KartverketAddress:
    """Finds addresses by their text."""

    def __init__(self, *, transport: Transport = http.urllib_transport, limiter: Limiter = LIMITER) -> None:
        """Ask through `transport`, at the pace `limiter` allows."""
        self._transport = transport
        self._limiter = limiter

    async def find(self, what: str) -> list[Place]:
        """The service's addresses for `what`, best first."""
        params = {"sok": what, "treffPerSide": "10", "utkoordsys": LAT_LON, "filtrer": FIELDS}
        answer = await http.get_json(NAME, URL, params, transport=self._transport, limiter=self._limiter)
        items = answer.get("adresser", []) if isinstance(answer, dict) else []
        return [place for place in map(_place, items) if place is not None]


def _place(item: Any) -> Place | None:  # noqa: ANN401 - one item of the service's JSON
    """One address, or None when it lacks a part the voice or the backends need."""
    try:
        point = item["representasjonspunkt"]
        return Place(
            name=str(item["adressetekst"]),
            municipality=written_as_a_name(str(item["kommunenavn"])),
            kind="address",
            lat=float(point["lat"]),
            lon=float(point["lon"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def written_as_a_name(municipality: str) -> str:
    """A municipality the service writes in capitals, as a name: each word with a capital first."""
    if municipality != municipality.upper():
        return municipality
    return "-".join(" ".join(w.capitalize() for w in part.split(" ")) for part in municipality.split("-"))
