"""Kartverket's address search, through the HTTP layer every backend shares, with no network.

The transport is a fake Kartverket over HTTP (`fake.py`): it answers in the service's own shape
and refuses what it refuses. Every address and position here is made up.
"""

import asyncio
import logging
import pathlib
import re
import tomllib

import pytest

from map_mcp.backends import http
from map_mcp.backends.kartverket_address import KartverketAddress
from map_mcp.fake import FakeKartverketHttp
from map_mcp.interfaces import BusyError, QueryError, UnreachableError

ROOT = pathlib.Path(__file__).parent.parent


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _address(fake=None, clock=None):
    fake = fake or FakeKartverketHttp()
    clock = clock or _Clock()
    return KartverketAddress(transport=fake, limiter=http.Limiter(clock=clock)), fake, clock


def test_an_address_is_found_with_its_municipality_written_as_a_name():
    """The service writes municipalities in capitals; the voice reads them as names."""
    address, fake, _ = _address()
    places = asyncio.run(address.find("Prøvestien"))
    assert [(p.name, p.municipality, p.kind) for p in places] == [("Prøvestien 4", "Prøveby", "address")]
    assert (places[0].lat, places[0].lon) == (0.01, 0.02)
    sent = fake.requests[0]
    assert sent.path == "/adresser/v1/sok"
    assert (sent.params["sok"], sent.params["utkoordsys"]) == ("Prøvestien", "4258")


def test_every_request_names_map_mcp_and_nothing_else():
    """The plugin, its version and where to read about it: no name, email or host of the owner."""
    assert re.fullmatch(r"map-mcp/\d+\.\d+\.\d+ \(\+https://github\.com/roykollensvendsen/map-mcp\)", http.USER_AGENT)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert f"map-mcp/{version} (+https://github.com/roykollensvendsen/map-mcp)" == http.USER_AGENT
    address, fake, _ = _address()
    asyncio.run(address.find("Prøvestien"))
    assert fake.requests[0].headers["User-Agent"] == http.USER_AGENT


def test_a_blank_search_is_refused_by_the_service():
    with pytest.raises(QueryError):
        asyncio.run(_address()[0].find(" "))


def test_a_busy_answer_is_said_as_a_wait():
    fake = FakeKartverketHttp()
    fake.busy_for = 30
    address, fake, _ = _address(fake)
    with pytest.raises(BusyError) as busy:
        asyncio.run(address.find("Prøvestien"))
    assert busy.value.seconds == 30


def test_a_busy_service_is_never_asked_again_in_a_loop():
    fake = FakeKartverketHttp()
    fake.busy_for = 30
    address, fake, _ = _address(fake)
    with pytest.raises(BusyError):
        asyncio.run(address.find("Prøvestien"))
    assert len(fake.requests) == 1


def test_a_busy_answer_with_no_wait_given_says_a_minute():
    fake = FakeKartverketHttp()
    fake.busy_for = 30
    fake.retry_after = None
    with pytest.raises(BusyError) as busy:
        asyncio.run(_address(fake)[0].find("Prøvestien"))
    assert busy.value.seconds == http.DEFAULT_WAIT


def test_a_service_is_asked_at_most_five_times_a_second():
    """Kartverket publishes no limit, so map-mcp keeps its own polite one, and waits by saying so."""
    address, _, clock = _address()
    asyncio.run(address.find("Prøvestien"))
    with pytest.raises(BusyError):
        asyncio.run(address.find("Prøvestien"))
    clock.now += http.MIN_INTERVAL
    assert asyncio.run(address.find("Prøvestien"))


def test_two_searches_a_moment_apart_on_their_own_clocks_both_pass():
    """Proof the limit is about time: each backend's own limiter starts empty."""
    assert asyncio.run(_address()[0].find("Prøvestien"))
    assert asyncio.run(_address()[0].find("Prøvestien"))


@pytest.mark.parametrize("failure", ["status_500", "timeout", "not_json"])
def test_an_error_from_a_backend_never_carries_the_request(failure, caplog):
    """A URL holds what was searched, and later a position: none of it reaches an error or the log."""
    fake = FakeKartverketHttp()
    setattr(fake, failure, True)
    address, _, _ = _address(fake)
    with caplog.at_level(logging.DEBUG), pytest.raises(UnreachableError) as failed:
        asyncio.run(address.find("Prøvestien"))
    said = str(failed.value) + caplog.text
    assert "Prøvestien" not in said
    assert "Pr%C3%B8vestien" not in said
    assert "geonorge" not in said
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None or failed.value.__suppress_context__
    assert "kartverket_address" in caplog.text


def test_an_item_missing_its_point_is_left_out():
    fake = FakeKartverketHttp()
    fake.drop_point = True
    assert asyncio.run(_address(fake)[0].find("Prøvestien")) == []
