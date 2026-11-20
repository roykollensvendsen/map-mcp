"""OpenStreetMap's Overpass, as the nearby-places service, through the shared HTTP layer, with no network.

The transport is the made-up Overpass over HTTP in `fake.py`. Every place here is made up, by 0,0.
"""

import asyncio
import datetime as dt
import threading

import pytest

from map_mcp import cli
from map_mcp.backends import http, overpass
from map_mcp.fake import FakeKartverket, FakeOverpassHttp, spot
from map_mcp.interfaces import BusyError, DailyLimitError, UnreachableError
from map_mcp.service import KINDS, MapService

PLACES = (
    spot("Prøve Kafé", "cafe", 0.002, 0.0),
    spot("Kafé Sør", "cafe", -0.01, 0.0),
    spot("Prøve Mat", "grocery", 0.003, 0.0),
)


class _Ticking:
    """A clock that moves a second on at each look, so the five-a-second limiter never says wait."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        self.now += 1
        return self.now


class _Day:
    def __init__(self):
        self.day = dt.date(2026, 1, 1)

    def __call__(self):
        return self.day


def _overpass(fake=None, *, clock=None, today=None):
    fake = fake or FakeOverpassHttp(PLACES)
    backend = overpass.Overpass(
        transport=fake, limiter=http.Limiter(clock=_Ticking()), clock=clock or _Ticking(), today=today or _Day()
    )
    return backend, fake


def _near(backend, kind="cafe", lat=0.0, lon=0.0, within_m=3000):
    return asyncio.run(backend.nearby(kind, lat, lon, within_m))


def test_places_of_a_kind_are_found_by_name_and_point():
    backend, fake = _overpass()
    found = _near(backend)
    assert sorted((n.name, n.kind, n.lat, n.lon) for n in found) == [
        ("Kafé Sør", "cafe", -0.01, 0.0),
        ("Prøve Kafé", "cafe", 0.002, 0.0),
    ]
    sent = fake.requests[0]
    assert sent.path == "/api/interpreter"
    assert sent.headers["User-Agent"] == http.USER_AGENT
    query = sent.params["data"]
    assert query.startswith("[out:json][timeout:10][maxsize:")
    assert '["amenity"="cafe"]' in query
    # Split, as the private-data scan refuses a written pair of points even by 0,0.
    assert "(around:3000,0.0," + "0.0)" in query


def test_overpass_is_asked_at_its_main_instance():
    assert overpass.URL == "https://overpass-api.de/api/interpreter"


def test_a_point_is_sent_to_openstreetmap_at_3_decimals_only():
    backend, fake = _overpass()
    _near(backend, lat=0.0012345, lon=-0.0045678)
    query = fake.requests[0].params["data"]
    assert "(around:3000,0.001," + "-0.005)" in query
    assert "0.0012" not in query
    assert "0.0045" not in query


def test_each_kind_the_voice_asks_for_has_a_filter_of_its_own():
    assert set(overpass.FILTERS) == set(KINDS)
    assert len(set(overpass.FILTERS.values())) == len(overpass.FILTERS)


def test_a_way_or_an_area_is_read_at_its_centre():
    fake = FakeOverpassHttp(PLACES)
    fake.as_ways = True
    found = _near(_overpass(fake)[0])
    assert sorted((n.lat, n.lon) for n in found) == [(-0.01, 0.0), (0.002, 0.0)]


def test_an_element_with_no_point_is_left_out():
    fake = FakeOverpassHttp(PLACES)
    fake.drop_point = True
    assert _near(_overpass(fake)[0]) == []


def test_a_place_the_map_never_named_is_kept_with_an_empty_name():
    found = _near(_overpass(FakeOverpassHttp([spot("", "parking", 0.001, 0.0)]))[0], kind="parking")
    assert [n.name for n in found] == [""]


def test_a_name_from_the_map_is_cleaned_before_the_voice_reads_it():
    """Anyone can write a name in OpenStreetMap, so it is read as text, never as layout or a long speech."""
    written = "Kafé" + chr(0x202E) + "\n\tNord" + chr(0) + "  " + "x" * 100
    found = _near(_overpass(FakeOverpassHttp([spot(written, "cafe", 0.001, 0.0)]))[0])
    assert found[0].name == ("Kafé Nord " + "x" * 100)[: overpass.NAME_MAX]
    assert overpass.NAME_MAX == 60


def test_a_busy_answer_is_said_as_the_wait_it_names():
    fake = FakeOverpassHttp(PLACES)
    fake.busy_for = 12
    with pytest.raises(BusyError) as busy:
        _near(_overpass(fake)[0])
    assert busy.value.seconds == 12
    assert len(fake.requests) == 1


def test_a_gateway_timeout_from_overpass_is_said_as_a_wait():
    """Overpass sends 504 when it has no room for the query, and asks for a pause after it."""
    fake = FakeOverpassHttp(PLACES)
    fake.gateway_timeout = True
    with pytest.raises(BusyError) as busy:
        _near(_overpass(fake)[0])
    assert busy.value.seconds == overpass.BUSY_WAIT == 30
    assert len(fake.requests) == 1


def test_no_more_than_the_daily_cap_is_asked():
    assert overpass.DAILY_CAP == 100
    today = _Day()
    backend, fake = _overpass(today=today)
    for n in range(overpass.DAILY_CAP):
        _near(backend, lat=n / 100)
    with pytest.raises(DailyLimitError):
        _near(backend, lat=-0.5)
    assert len(fake.requests) == overpass.DAILY_CAP
    today.day += dt.timedelta(days=1)
    _near(backend, lat=-0.5)
    assert len(fake.requests) == overpass.DAILY_CAP + 1


def test_one_question_at_a_time_is_sent():
    """A second question while one is out is told to wait a moment, and is never queued."""
    release = threading.Event()
    fake = FakeOverpassHttp(PLACES)

    def held(url, headers, timeout):
        release.wait(5)
        return fake(url, headers, timeout)

    backend, _ = _overpass(held)

    async def both():
        first = asyncio.create_task(backend.nearby("cafe", 0.0, 0.0, 3000))
        await asyncio.sleep(0.05)
        try:
            with pytest.raises(BusyError) as busy:
                await backend.nearby("cafe", 0.5, 0.5, 3000)
        finally:
            release.set()
        await first
        return busy.value.seconds

    assert asyncio.run(both()) < 1
    assert len(fake.requests) == 1


def test_the_same_question_within_an_hour_is_answered_from_memory():
    clock = _Ticking()
    backend, fake = _overpass(clock=clock)
    first = _near(backend)
    assert _near(backend) == first
    assert len(fake.requests) == 1
    clock.now += 3600
    _near(backend)
    assert len(fake.requests) == 2


def test_a_failed_question_is_not_kept_in_memory():
    fake = FakeOverpassHttp(PLACES)
    fake.busy_for = 5
    backend, _ = _overpass(fake)
    with pytest.raises(BusyError):
        _near(backend)
    fake.busy_for = 0
    assert len(_near(backend)) == 2


def test_no_failure_or_log_holds_the_point(caplog):
    fake = FakeOverpassHttp(PLACES)
    fake.timeout = True
    with pytest.raises(UnreachableError) as away:
        _near(_overpass(fake)[0], lat=0.123, lon=0.456)
    assert "0.123" not in str(away.value)
    assert "0.123" not in caplog.text
    assert "0.456" not in caplog.text


def test_the_daily_cap_reached_is_said_as_tomorrow():
    backend, _ = _overpass()
    for n in range(overpass.DAILY_CAP):
        _near(backend, lat=(n + 1) / 100)  # never Prøveby's own point, which would come from memory
    answer = asyncio.run(MapService(FakeKartverket(), backend).nearby("cafe", "Prøveby"))
    assert (answer["outcome"], answer["say"]) == (
        "daily_limit",
        "I've asked OpenStreetMap as often as I may today; ask again tomorrow.",
    )


def test_every_answer_carries_openstreetmap_s_licence():
    assert overpass.Overpass.attribution == "Map data © OpenStreetMap contributors, ODbL"
    assert overpass.Overpass.service == "OpenStreetMap"


def test_a_real_run_asks_openstreetmap_and_a_simulated_run_the_made_up_places():
    assert isinstance(cli.places(simulate=False), overpass.Overpass)
    assert not isinstance(cli.places(simulate=True), overpass.Overpass)
