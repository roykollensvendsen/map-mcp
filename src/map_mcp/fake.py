"""A made-up Kartverket that refuses what the real one refuses.

A fake that says yes to everything lets a test pass that the real service would fail. So this
one keeps the service's limits: a search needs a word, and it can be told to stop answering or
to be busy for a while, as the real one can. Write each new limit of a real service in here
first, with a test, before the code that copes with it.

Every place here is made up, and every position sits by 0,0, in the sea, so none can be a
real home.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any

from map_mcp.backends.http import Response
from map_mcp.interfaces import BusyError, Place, QueryError, UnreachableError


def made_up(name: str, municipality: str, kind: str = "address", lat: float = 0.01, lon: float = 0.02) -> Place:
    """A made-up place, by default an address, with a position by 0,0."""
    return Place(name=name, municipality=municipality, kind=kind, lat=lat, lon=lon)


#: The fake's own places, when a test names none.
MADE_UP = (
    made_up("Prøvestien 4", "Prøveby"),
    made_up("Prøveby", "Prøveby", "town", 0.0, 0.0),
    made_up("Prøvevatnet", "Prøveby", "lake", 0.03, 0.01),
)


#: The place-name service's own word for a kind the fake's places name in English.
SERVICE_KINDS = {"town": "By", "lake": "Innsjø"}


class FakeKartverket:
    """Kartverket's search in memory, with the real one's limits."""

    def __init__(self, places: list[Place] | tuple[Place, ...] = MADE_UP) -> None:
        """Answer from `places`, in their order, which stands for the service's ranking."""
        self.places = list(places)
        self.unreachable = False
        #: Seconds the service says to wait before it is asked again; 0 when it answers.
        self.busy_for = 0.0
        self.asked = 0

    async def find(self, what: str) -> list[Place]:
        """The places whose name holds `what`, whatever its case."""
        self.asked += 1
        if self.unreachable:
            msg = "the address service did not answer"
            raise UnreachableError(msg)
        if self.busy_for:
            raise BusyError(self.busy_for)
        # RULE: the fake refuses an empty search as the address service does
        if not what.strip():
            msg = "a search needs a word to look for"
            raise QueryError(msg)
        wanted = what.strip().casefold()
        return [place for place in self.places if wanted in place.name.casefold()]


@dataclass(frozen=True)
class Sent:
    """One request the HTTP fake was sent: its path, its query and its headers."""

    path: str
    params: dict[str, str]
    headers: dict[str, str]


#: What each service was seen to answer a blank search with, on 19.11.
BLANK_ADDRESS = Response(400, {}, b'{"message": "no search word"}')
BLANK_NAMES = Response(422, {}, b'{"errors": {"message": {"query": {"sok": ["too short"]}}}}')


class FakeKartverketHttp:
    """Kartverket over HTTP, in memory: a transport for the real backends, in the service's shape.

    It answers `/adresser/v1/sok` as the address search does, from the made-up places of kind
    "address", and `/stedsnavn/v1/navn` as the place-name search does, from the rest. The
    place-name kinds go back to the service's own words. A blank `sok` gets what each service
    was seen to send on 19.11: a 400 with a message from the address search, and a 422 with an
    errors object from the place-name search. It can be busy (429), broken (500), slow (a
    timeout whose text holds the URL, as the standard library's does), or answer with what is
    not JSON.
    """

    def __init__(self, places: list[Place] | tuple[Place, ...] = MADE_UP) -> None:
        """Answer from `places`, in their order."""
        self.places = list(places)
        self.requests: list[Sent] = []
        self.busy_for = 0.0
        #: The Retry-After a 429 carries; None sends none.
        self.retry_after: str | None = "auto"
        self.status_500 = False
        self.timeout = False
        self.not_json = False
        self.drop_point = False
        #: The coordinate system the place-name search answers in.
        self.names_koordsys = 4258

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> Response:  # noqa: ARG002
        """Answer one GET the way the service would."""
        parts = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        self.requests.append(Sent(parts.path, params, dict(headers)))
        return self._trouble(url) or self._search(parts.path, params)

    def _trouble(self, url: str) -> Response | None:
        """The failure the fake was told to give, or None when it answers. Each failure holds the URL."""
        if self.timeout:
            msg = f"timed out reading {url}"
            raise TimeoutError(msg)
        if self.busy_for:
            return self._busy()
        if self.status_500:
            return Response(500, {}, f"failed on {url}".encode())
        if self.not_json:
            return Response(200, {}, f"<html>{url}</html>".encode())
        return None

    def _busy(self) -> Response:
        wait = str(int(self.busy_for)) if self.retry_after == "auto" else self.retry_after
        return Response(429, {} if wait is None else {"retry-after": wait}, b"")

    def _search(self, path: str, params: dict[str, str]) -> Response:
        """The search at `path`, as the service answers it."""
        if not params.get("sok", "").strip():
            return BLANK_NAMES if path.startswith("/stedsnavn/") else BLANK_ADDRESS
        searches = {"/adresser/v1/sok": ("adresser", self._addresses), "/stedsnavn/v1/navn": ("navn", self._names)}
        if path not in searches:
            return Response(404, {}, b"")
        key, search = searches[path]
        return Response(200, {}, json.dumps({key: search(params["sok"])}).encode())

    def _matching(self, what: str, *, address: bool) -> list[Place]:
        wanted = what.strip().casefold()
        return [p for p in self.places if (p.kind == "address") == address and wanted in p.name.casefold()]

    def _addresses(self, what: str) -> list[dict[str, Any]]:
        found = []
        for place in self._matching(what, address=True):
            item: dict[str, Any] = {"adressetekst": place.name, "kommunenavn": place.municipality.upper()}
            if not self.drop_point:
                item["representasjonspunkt"] = {"epsg": "EPSG:4258", "lat": place.lat, "lon": place.lon}
            found.append(item)
        return found

    def _names(self, what: str) -> list[dict[str, Any]]:
        found = []
        for place in self._matching(what, address=False):
            item: dict[str, Any] = {
                "skrivemåte": place.name,
                "navneobjekttype": SERVICE_KINDS.get(place.kind, place.kind),
                "kommuner": [{"kommunenavn": place.municipality, "kommunenummer": "0000"}]
                if place.municipality
                else [],
                "representasjonspunkt": {"øst": place.lon, "nord": place.lat, "koordsys": self.names_koordsys},
            }
            found.append(item)
        return found
