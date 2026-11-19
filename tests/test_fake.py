"""The fake Kartverket refuses what the real one refuses, so a test cannot pass that the service would fail."""

import asyncio

import pytest

from map_mcp.fake import MADE_UP, FakeKartverket, made_up
from map_mcp.interfaces import BusyError, NotSetUpError, QueryError, Unconnected, UnreachableError


def test_the_fake_refuses_an_empty_search_as_the_address_service_does():
    """Kartverket's search needs a search word; a blank one is a refused request, not an empty list."""
    with pytest.raises(QueryError):
        asyncio.run(FakeKartverket().find(" "))


def test_the_fake_finds_by_any_part_of_a_name_whatever_its_case():
    found = asyncio.run(FakeKartverket().find("prøvesti"))
    assert [place.name for place in found] == ["Prøvestien 4"]


def test_the_fake_keeps_its_own_order():
    """The service ranks its matches; the fake's order stands for that ranking."""
    places = [made_up("Lundstien 2", "Lundby"), made_up("Lundstien 1", "Lundby")]
    assert [p.name for p in asyncio.run(FakeKartverket(places).find("Lundstien"))] == ["Lundstien 2", "Lundstien 1"]


def test_the_fake_s_places_are_made_up_and_near_nowhere():
    """Its positions sit by 0,0, in the sea off Africa, so none can be a real home."""
    assert all(abs(place.lat) < 1 and abs(place.lon) < 1 for place in MADE_UP)


def test_a_fake_off_the_network_answers_nothing():
    kartverket = FakeKartverket()
    kartverket.unreachable = True
    with pytest.raises(UnreachableError):
        asyncio.run(kartverket.find("Prøveby"))


def test_a_busy_fake_says_how_long_to_wait():
    kartverket = FakeKartverket()
    kartverket.busy_for = 12
    with pytest.raises(BusyError) as busy:
        asyncio.run(kartverket.find("Prøveby"))
    assert busy.value.seconds == 12


def test_an_unconnected_geocoder_says_what_to_do():
    with pytest.raises(NotSetUpError, match="--simulate"):
        asyncio.run(Unconnected().find("Prøveby"))
