"""What the tools need from the map services, and the ways asking one can fail.

The design has four interfaces: Geocoder, Places, Router and Position. The tools know only
these, and a backend is one module that fills one of them. This file holds the Geocoder now;
the others come with their backends. The fake (`fake.py`) and each real backend answer the
same interface, so every test runs through the same door a real service does.

A position travels between the backends only. No answer to the voice carries one.
"""

from __future__ import annotations

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
