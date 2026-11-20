"""OpenStreetMap's Overpass API (overpass-api.de), as the nearby-places service.

Map data © OpenStreetMap contributors, under the ODbL. No key or login is needed. Overpass gets
the kind of place, the reach, and the point at three decimals, about 100 m. Nothing else about
the owner is sent.

It keeps the limits on Overpass's own page, read 20.11. Regular use should stay near 100
questions a day. It sends one question at a time, with a short `timeout` and `maxsize`. A 429 or a
504 is said as a wait, 30 s unless the service names one, and is never retried. The same
question within an hour is answered from memory, so asking again costs Overpass nothing.
"""

from __future__ import annotations

import datetime as dt
import time
import unicodedata
from typing import TYPE_CHECKING, Any

from map_mcp.backends import http
from map_mcp.interfaces import BusyError, DailyLimitError, Nearby

if TYPE_CHECKING:
    from collections.abc import Callable

    from map_mcp.backends.http import Limiter, Transport

URL = "https://overpass-api.de/api/interpreter"
NAME = "overpass"
#: Overpass's page asks regular use to stay near a hundredth of its 10 000 a day.
DAILY_CAP = 100
#: Seconds Overpass may spend on the query, and the memory it may use, in bytes.
QUERY_TIMEOUT = 10
MAXSIZE = 16 * 1024 * 1024
#: The pause Overpass asks for after a 429 or a 504 that names none.
BUSY_WAIT = 30.0
#: The statuses Overpass sends when it is too busy: too many requests, and no room for the query.
# RULE: a gateway timeout from overpass is said as a wait
BUSY = (429, 504)
#: How long an answer is kept for the same question, in seconds.
KEEP = 3600.0
#: The longest name the voice reads; anyone can write a name in OpenStreetMap.
NAME_MAX = 60
#: The tags that make a place of each kind, in Overpass's own words.
FILTERS = {
    "shop": '["shop"]',
    "grocery": '["shop"~"^(supermarket|convenience|greengrocer)$"]',
    "charging": '["amenity"="charging_station"]',
    "fuel": '["amenity"="fuel"]',
    "parking": '["amenity"="parking"]',
    "toilet": '["amenity"="toilets"]',
    "cafe": '["amenity"="cafe"]',
    "bus stop": '["highway"="bus_stop"]',
}
#: One shared limiter for the service, whichever instance asks.
LIMITER = http.Limiter()


class Overpass:
    """Finds places of one kind near a point, in OpenStreetMap."""

    service = "OpenStreetMap"
    attribution = "Map data © OpenStreetMap contributors, ODbL"

    def __init__(
        self,
        *,
        transport: Transport = http.urllib_transport,
        limiter: Limiter = LIMITER,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], dt.date] = dt.date.today,
    ) -> None:
        """Ask through `transport`, at the pace `limiter` allows; `clock` and `today` let a test move time on."""
        self._transport = transport
        self._limiter = limiter
        self._clock = clock
        self._today = today
        self._day = today()
        self._asked = 0
        self._out = False
        self._kept: dict[tuple[str, float, float, int], tuple[float, list[Nearby]]] = {}

    async def nearby(self, kind: str, lat: float, lon: float, within_m: float) -> list[Nearby]:
        """The places of `kind` within `within_m` metres of the point, from memory when asked within the hour."""
        # RULE: a point is sent to OpenStreetMap at 3 decimals only
        question = (kind, round(lat, 3), round(lon, 3), round(within_m))
        kept = self._kept.get(question)
        # RULE: the same question within an hour is answered from memory
        if kept and self._clock() - kept[0] < KEEP:
            return kept[1]
        found = await self._ask(*question)
        now = self._clock()
        self._kept = {q: k for q, k in self._kept.items() if now - k[0] < KEEP} | {question: (now, found)}
        return found

    async def _ask(self, kind: str, lat: float, lon: float, within_m: int) -> list[Nearby]:
        """One question to Overpass, when none is out and today's share is not spent."""
        # RULE: one question at a time is sent
        if self._out:
            raise BusyError(http.MIN_INTERVAL)
        self._count_one()
        query = f"[out:json][timeout:{QUERY_TIMEOUT}][maxsize:{MAXSIZE}];"
        query += f"nwr{FILTERS[kind]}(around:{within_m},{lat},{lon});out center;"
        self._out = True
        try:
            answer = await http.get_json(
                NAME, URL, {"data": query}, transport=self._transport, limiter=self._limiter, busy=BUSY, wait=BUSY_WAIT
            )
        finally:
            self._out = False
        elements = answer.get("elements", []) if isinstance(answer, dict) else []
        return [place for place in (_nearby(kind, e) for e in elements) if place is not None]

    def _count_one(self) -> None:
        """Count a question against today's share, or refuse it when the share is spent."""
        if self._today() != self._day:
            self._day, self._asked = self._today(), 0
        # RULE: no more than the daily cap is asked
        if self._asked >= DAILY_CAP:
            http.log.warning("%s failed: daily cap, status None", NAME)
            msg = "asked OpenStreetMap as often as allowed today"
            raise DailyLimitError(msg)
        self._asked += 1


def _nearby(kind: str, element: Any) -> Nearby | None:  # noqa: ANN401 - one element of the service's JSON
    """One place: a node at its point, a way or an area at its centre; None without a point."""
    try:
        point = element if element.get("type") == "node" else element["center"]
        tags = element.get("tags") or {}
        return Nearby(
            name=spoken(str(tags.get("name", ""))), kind=kind, lat=float(point["lat"]), lon=float(point["lon"])
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def spoken(name: str) -> str:
    """A name from the map as plain text: no control or layout characters, one space between words, short."""
    # RULE: a name from the map is cleaned before the voice reads it
    kept = "".join(c if not unicodedata.category(c).startswith("C") else " " for c in name)
    return " ".join(kept.split())[:NAME_MAX]
