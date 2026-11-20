"""map_nearby, end to end: through the MCP server, the service, a fake Kartverket and fake places.

"near" is found the way map_find finds it, and the places around it come from the fake. Every
place here is made up, and so are the fake's positions, which sit by 0,0 in the sea.
"""

import asyncio
import re

import pytest

from map_mcp.fake import FakeKartverket, FakeNearby, spot
from map_mcp.interfaces import BusyError
from map_mcp.server import build_server
from map_mcp.service import BROKE, HERE_UNKNOWN, KINDS, NEARBY_NOT_SET_UP, MapService

#: A pair of decimals with three places or more, however they are set apart (design §10, n1).
COORDINATES = re.compile(r"\d{1,3}\.\d{3,}\s*°?\s*[NSEW]?\s*[,\s]\s*\d{1,3}\.\d{3,}")


def _call(places=None, *, what="grocery", near="Prøveby", within_km=None, simulated=False):
    service = MapService(FakeKartverket(), places if places is not None else FakeNearby())
    arguments = {"what": what, "near": near}
    if within_km is not None:
        arguments["within_km"] = within_km
    server = build_server(service, simulated=simulated)
    return asyncio.run(server.call_tool("map_nearby", arguments)).structured_content


def test_the_nearest_three_are_said_by_name_and_distance():
    answer = _call()
    assert answer["say"] == (
        "The nearest groceries to Prøveby: Prøve Mat, 330 m; Butikk Nord, 1.1 km; Lager Sør, 2.2 km."
    )
    assert (answer["success"], answer["outcome"]) == (True, "found")
    assert [n["name"] for n in answer["nearby"]] == ["Prøve Mat", "Butikk Nord", "Lager Sør"]


def test_one_place_found_is_said_on_its_own():
    answer = _call(what="charging")
    assert answer["say"] == "The nearest charger to Prøveby is Prøve Lading, 560 m away."


def test_none_within_reach_is_said_with_the_distance_looked():
    """A toilet 4 km off is past the 3 km a toilet is looked for."""
    answer = _call(what="toilet")
    assert answer["say"] == "None within 3 km of Prøveby."
    assert (answer["success"], answer["outcome"]) == (True, "none_near")


def test_a_kind_off_the_list_is_refused_with_the_list_read_out():
    answer = _call(what="castle")
    assert answer["outcome"] == "unknown_kind"
    assert answer["say"] == (
        "I can look for a shop, grocery, charging, fuel, parking, toilet, cafe or bus stop. Which one?"
    )


def test_the_list_of_kinds_is_closed_and_each_has_its_reach():
    """The design's closed list; "path" was dropped, and the reach is 3 km or 15 km by kind."""
    assert {kind: reach for kind, (_, _, reach) in KINDS.items()} == {
        "shop": 3,
        "grocery": 15,
        "charging": 15,
        "fuel": 15,
        "parking": 3,
        "toilet": 3,
        "cafe": 3,
        "bus stop": 3,
    }


def test_a_reach_past_the_kind_s_own_is_refused_with_the_fix():
    answer = _call(what="cafe", within_km=10)
    assert answer["outcome"] == "too_far"
    assert answer["say"] == "I look at most 3 km out for a cafe; ask for 3 km or less."


def test_a_shorter_reach_leaves_out_what_lies_past_it():
    answer = _call(within_km=1.5)
    assert answer["say"] == "The nearest groceries to Prøveby: Prøve Mat, 330 m; Butikk Nord, 1.1 km."


def test_here_is_not_known_yet_and_the_voice_says_to_name_a_place():
    assert _call(near="here")["say"] == HERE_UNKNOWN


def test_a_near_that_is_found_nowhere_is_said():
    assert _call(near="Ingensteds")["say"] == "I found no address or place called Ingensteds."


def test_every_answer_names_where_its_places_come_from():
    answer = _call()
    assert answer["attribution"] == FakeNearby().attribution


def test_a_busy_service_for_nearby_places_is_said_as_a_wait():
    busy = FakeNearby()
    busy.busy_for = 30
    assert _call(busy)["say"] == "OpenStreetMap is busy; try again in 30 seconds."


def test_an_unreachable_service_for_nearby_places_is_said():
    away = FakeNearby()
    away.unreachable = True
    assert _call(away)["say"] == "OpenStreetMap isn't answering. Try again in a minute."


class _Broken(FakeNearby):
    """A places service whose own code breaks, as it would on an answer of a shape it does not know."""

    async def nearby(self, kind, lat, lon, within_m):  # noqa: ARG002 - the interface's own signature
        raise KeyError(kind)


def test_a_broken_places_service_still_gives_a_sentence_to_say():
    answer = _call(_Broken())
    assert (answer["outcome"], answer["say"]) == ("broke", BROKE)


def test_no_nearby_places_service_set_up_is_said():
    """A real run has none until the OpenStreetMap backend is built, and says so."""
    server = build_server(MapService(FakeKartverket()))
    answer = asyncio.run(server.call_tool("map_nearby", {"what": "grocery", "near": "Prøveby"})).structured_content
    assert answer["say"] == NEARBY_NOT_SET_UP


def test_a_place_with_no_name_is_said_as_one_with_no_name():
    places = FakeNearby([spot("", "parking", 0.002, 0.0)])
    assert _call(places, what="parking")["say"] == (
        "The nearest parking place to Prøveby is one with no name, 220 m away."
    )


@pytest.mark.parametrize("what", [*sorted(KINDS), "castle"])
def test_no_answer_ever_holds_a_position(what):
    """Positions travel between the backends only; a spoken answer never carries one."""
    answer = _call(what=what)
    assert not COORDINATES.search(answer["say"]), answer["say"]
    assert all(set(near) == {"name", "metres"} for near in answer.get("nearby", []))


@pytest.mark.parametrize(
    "said",
    ["0.12" + "3, 0.45" + "6", "0.123 0.456", "0.123 N 0.456 E", "0.123° 0.456°"],
)
def test_the_position_check_catches_each_way_a_pair_is_written(said):
    # The comma pair is split, as in test_private_data_scan.py, so no file holds one whole.
    assert COORDINATES.search(said)


@pytest.mark.parametrize("said", ["About 4.2 km by car, 9 minutes.", "Prøve Mat, 330 m; Butikk Nord, 1.1 km."])
def test_the_position_check_lets_distances_pass(said):
    assert not COORDINATES.search(said)


def test_the_fake_refuses_when_told_to_be_busy():
    busy = FakeNearby()
    busy.busy_for = 5
    with pytest.raises(BusyError):
        asyncio.run(busy.nearby("grocery", 0.0, 0.0, 1000))
