"""What the tools need from the map services, and the ways asking one can fail.

The design has four interfaces: Geocoder, Places, Router and Position. The tools know only
these, and a backend is one module that fills one of them. This file holds the Geocoder and
Places now; the others come with their backends. The fake (`fake.py`) and each real backend answer the
same interface, so every test runs through the same door a real service does.

A position travels between the backends only. No answer to the voice carries one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class MapError(Exception):
    """Asking a service failed; each kind below is said to the voice in its own words."""


class UnreachableError(MapError):
    """The service did not answer in time."""


class BusyError(MapError):
    """The service refuses to be asked again so soon."""

    def __init__(self, seconds: float) -> None:
        """Keep how long to wait, so the voice can say it."""
        super().__init__(f"ask again in {seconds:.0f} s")
        self.seconds = seconds


class QueryError(MapError):
    """The service refused the request itself, such as a search with no word in it."""


class NotSetUpError(MapError):
    """No real service is set up, so nothing was asked."""


@dataclass(frozen=True)
class Place:
    """One match: its name, its municipality, what kind of place it is, and where it is."""

    name: str
    municipality: str
    kind: str
    lat: float
    lon: float


class Geocoder(Protocol):
    """Finds addresses and place names."""

    async def find(self, what: str) -> list[Place]:
        """The service's matches for `what`, best first."""
        ...


class Unconnected:
    """The real geocoder, until one is set up: every search says so."""

    async def find(self, what: str) -> list[Place]:  # noqa: ARG002 - the interface's own signature
        """Refuse, naming the next step."""
        msg = "no address service is set up yet; run with --simulate"
        raise NotSetUpError(msg)


@dataclass(frozen=True)
class Nearby:
    """One place of a kind near a point: its name, which may be empty, its kind and where it is."""

    name: str
    kind: str
    lat: float
    lon: float


class Places(Protocol):
    """Finds places of one kind near a point."""

    #: The service's name, as the voice says it when the service is busy or away.
    service: str
    #: Where its data comes from, carried in every answer, as the data's licence asks.
    attribution: str

    async def nearby(self, kind: str, lat: float, lon: float, within_m: float) -> list[Nearby]:
        """The places of `kind` within `within_m` metres of the point, in any order."""
        ...


class UnconnectedPlaces:
    """The real nearby-places service, until one is built: every search says so."""

    service = "OpenStreetMap"
    attribution = ""

    async def nearby(self, kind: str, lat: float, lon: float, within_m: float) -> list[Nearby]:  # noqa: ARG002
        """Refuse, naming the next step."""
        msg = "no nearby-places service is set up yet; run with --simulate"
        raise NotSetUpError(msg)


#: The earth's mean radius, for a straight-line distance.
EARTH_M = 6_371_008.8


def metres(lat: float, lon: float, to_lat: float, to_lon: float) -> float:
    """The straight-line distance between two points, over the earth's surface."""
    north, east = math.radians(to_lat - lat), math.radians(to_lon - lon)
    across = (
        math.sin(north / 2) ** 2
        + math.cos(math.radians(lat)) * math.cos(math.radians(to_lat)) * math.sin(east / 2) ** 2
    )
    return 2 * EARTH_M * math.asin(math.sqrt(across))
