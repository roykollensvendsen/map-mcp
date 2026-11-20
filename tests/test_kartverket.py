"""map_find against Kartverket: addresses and place names asked together, with no network.

Both backends share one made-up Kartverket over HTTP (`fake.py`). Every place here is made up.
"""

import asyncio
import logging

import pytest

from map_mcp import cli
from map_mcp.backends import http, kartverket_names
from map_mcp.backends.kartverket import Kartverket
from map_mcp.backends.kartverket_address import KartverketAddress
from map_mcp.backends.kartverket_names import KartverketNames
from map_mcp.fake import FakeKartverket, FakeKartverketHttp
from map_mcp.interfaces import BusyError, UnreachableError


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _kartverket(addresses=None, names=None):
    addresses = addresses or FakeKartverketHttp()
    names = names or addresses
    return Kartverket(
        addresses=KartverketAddress(transport=addresses, limiter=http.Limiter(clock=_Clock())),
        names=KartverketNames(transport=names, limiter=http.Limiter(clock=_Clock())),
    )


def test_addresses_come_before_place_names():
    """One search asks both services, and an address is the likelier meaning of a street and number."""
    places = asyncio.run(_kartverket().find("Prøve"))
    assert [(p.name, p.kind) for p in places] == [
        ("Prøvestien 4", "address"),
        ("Prøveby", "town"),
        ("Prøvevatnet", "lake"),
    ]


def test_when_one_service_fails_the_other_still_answers():
    broken = FakeKartverketHttp()
    broken.status_500 = True
    places = asyncio.run(_kartverket(addresses=broken, names=FakeKartverketHttp()).find("Prøve"))
    assert [p.name for p in places] == ["Prøveby", "Prøvevatnet"]


def test_when_both_services_fail_the_failure_is_said():
    broken = FakeKartverketHttp()
    broken.status_500 = True
    with pytest.raises(UnreachableError):
        asyncio.run(_kartverket(addresses=broken).find("Prøve"))


def test_a_real_run_asks_kartverket_and_a_simulated_run_the_made_up_places():
    assert isinstance(cli.geocoder(simulate=False), Kartverket)
    assert isinstance(cli.geocoder(simulate=True), FakeKartverket)


def test_the_place_name_search_is_read_from_the_host_kartverket_recommends():
    """The place-name service moved to api.kartverket.no; ws.geonorge.no is only a proxy for it."""
    assert kartverket_names.URL.startswith("https://api.kartverket.no/stedsnavn/v1/")


def test_when_one_service_fails_and_the_other_finds_nothing_the_failure_is_said():
    """Nothing found would be untrue when one search never ran: the owner hears the failure instead."""
    busy = FakeKartverketHttp()
    busy.busy_for = 30
    with pytest.raises(BusyError) as said:
        asyncio.run(_kartverket(addresses=busy, names=FakeKartverketHttp()).find("Ingensteds"))
    assert said.value.seconds == 30


class _Broken:
    """A search whose own code breaks, as it would on an answer of a shape it does not know."""

    async def find(self, what):
        raise KeyError(what)


def test_a_failure_behind_places_found_is_still_logged(caplog):
    """Places from one search stand, but a search broken in code must not hide behind them for good.

    The log names the search and the kind of failure, never what was asked.
    """
    working = KartverketNames(transport=FakeKartverketHttp(), limiter=http.Limiter(clock=_Clock()))
    with caplog.at_level(logging.WARNING):
        places = asyncio.run(Kartverket(addresses=_Broken(), names=working).find("Prøve"))
    assert [p.name for p in places] == ["Prøveby", "Prøvevatnet"]
    assert "address search failed: KeyError" in caplog.text
    assert "Prøve" not in caplog.text
