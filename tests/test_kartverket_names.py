"""Kartverket's place-name search, through the shared HTTP layer, with no network.

The transport is the made-up Kartverket over HTTP in `fake.py`. Every place here is made up.
"""

import asyncio

import pytest

from map_mcp.backends import http
from map_mcp.backends.kartverket_names import KartverketNames
from map_mcp.fake import FakeKartverketHttp, made_up
from map_mcp.interfaces import QueryError


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _names(fake=None):
    fake = fake or FakeKartverketHttp()
    return KartverketNames(transport=fake, limiter=http.Limiter(clock=_Clock())), fake


def test_a_place_is_found_with_its_kind_in_words_and_its_point_as_latitude_and_longitude():
    """The service gives east and north; asked for 4258, east is the longitude and north the latitude."""
    names, fake = _names()
    places = asyncio.run(names.find("Prøvevatnet"))
    assert [(p.name, p.municipality, p.kind) for p in places] == [("Prøvevatnet", "Prøveby", "lake")]
    assert (places[0].lat, places[0].lon) == (0.03, 0.01)
    sent = fake.requests[0]
    assert sent.path == "/stedsnavn/v1/navn"
    assert (sent.params["sok"], sent.params["utkoordsys"]) == ("Prøvevatnet", "4258")
    assert sent.headers["User-Agent"] == http.USER_AGENT


def test_a_town_is_said_as_a_town():
    places = asyncio.run(_names()[0].find("Prøveby"))
    assert [(p.name, p.kind) for p in places] == [("Prøveby", "town")]


def test_a_kind_without_a_word_of_its_own_is_said_as_a_place():
    fake = FakeKartverketHttp([made_up("Prøvehaugen", "Prøveby", "Haug", 0.02, 0.02)])
    places = asyncio.run(_names(fake)[0].find("Prøvehaugen"))
    assert [p.kind for p in places] == ["place"]


def test_a_place_in_no_municipality_is_kept_with_none_named():
    """Places at sea lie in no municipality; the voice can still say where they are by name."""
    fake = FakeKartverketHttp([made_up("Prøveskjæret", "", "Skjær", 0.0, 0.01)])
    places = asyncio.run(_names(fake)[0].find("Prøveskjæret"))
    assert [(p.name, p.municipality) for p in places] == [("Prøveskjæret", "")]


def test_an_item_in_another_coordinate_system_is_left_out():
    """A point in metres read as degrees would put a place far out at sea, so it is dropped."""
    fake = FakeKartverketHttp()
    fake.names_koordsys = 25833
    assert asyncio.run(_names(fake)[0].find("Prøvevatnet")) == []


def test_a_blank_search_is_refused_by_the_service():
    with pytest.raises(QueryError):
        asyncio.run(_names()[0].find(""))
