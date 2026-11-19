"""map_find, end to end: through the MCP server, the service and a fake Kartverket.

This is the walking skeleton: the one tool that runs the whole way from the first commit.
Every new tool gets a file like this one, named after it (tests/test_every_tool_has_a_test.py).
Every place here is made up, and so are the fake's positions.
"""

import asyncio

from map_mcp.fake import FakeKartverket, made_up
from map_mcp.interfaces import BusyError, NotSetUpError
from map_mcp.server import build_server
from map_mcp.service import BROKE, BUSY_A_MOMENT, NO_QUERY, NOT_SET_UP, UNREACHABLE, MapService


def _call(geocoder, what="Prøvestien 4", *, simulated=False):
    server = build_server(MapService(geocoder), simulated=simulated)
    return asyncio.run(server.call_tool("map_find", {"what": what})).structured_content


def test_one_match_is_said_with_its_municipality():
    answer = _call(FakeKartverket())
    assert answer["say"] == "Prøvestien 4, Prøveby."
    assert (answer["success"], answer["outcome"], answer["simulated"]) == (True, "found", False)
    assert answer["matches"] == [{"name": "Prøvestien 4", "municipality": "Prøveby", "kind": "address"}]


def test_a_town_is_said_as_a_town_and_a_place_with_its_municipality():
    assert _call(FakeKartverket(), "Prøveby")["say"] == "Prøveby, a town."
    assert _call(FakeKartverket(), "Prøvevatnet")["say"] == "Prøvevatnet, a lake in Prøveby."


def test_several_matches_are_read_as_the_top_three():
    """The voice reads three and asks which; a longer list is too long to hear."""
    places = [made_up(f"Lundstien {n}", "Lundby") for n in range(1, 6)]
    answer = _call(FakeKartverket(places), "Lundstien")
    assert answer["say"] == (
        "5 matches; the first three: Lundstien 1, Lundby; Lundstien 2, Lundby; Lundstien 3, Lundby. Which one?"
    )
    assert len(answer["matches"]) == 3


def test_two_matches_are_both_read():
    places = [made_up("Lundstien 1", "Lundby"), made_up("Lundstien 1", "Bekkby")]
    assert _call(FakeKartverket(places), "Lundstien 1")["say"] == (
        "2 matches: Lundstien 1, Lundby; Lundstien 1, Bekkby. Which one?"
    )


def test_nothing_found_is_said_with_what_was_asked():
    answer = _call(FakeKartverket(), "Ingensteds")
    assert (answer["success"], answer["outcome"]) == (False, "not_found")
    assert answer["say"] == "I found no address or place called Ingensteds."


def test_an_empty_search_asks_for_a_name_and_asks_the_service_nothing():
    kartverket = FakeKartverket()
    assert _call(kartverket, "  ")["say"] == NO_QUERY
    assert kartverket.asked == 0


def test_an_answer_never_carries_a_position():
    """A position stays between the backends; the voice and the conversation get words only."""
    answer = _call(FakeKartverket())
    assert all(set(match) == {"name", "municipality", "kind"} for match in answer["matches"])


def test_a_simulated_answer_says_so():
    answer = _call(FakeKartverket(), simulated=True)
    assert answer["simulated"] is True
    assert answer["say"].startswith("Simulated: ")


def test_a_service_off_the_network_is_said_with_what_to_do():
    kartverket = FakeKartverket()
    kartverket.unreachable = True
    assert _call(kartverket) == {"success": False, "outcome": "unreachable", "say": UNREACHABLE, "simulated": False}


def test_a_busy_service_is_said_as_a_wait():
    kartverket = FakeKartverket()
    kartverket.busy_for = 30
    answer = _call(kartverket)
    assert answer["outcome"] == "busy"
    assert answer["say"] == "The address service is busy; try again in 30 seconds."


class _Broken:
    async def find(self, _what):
        msg = "a fault nobody planned for"
        raise RuntimeError(msg)


class _NotSetUp:
    async def find(self, _what):
        raise NotSetUpError


class _Busy:
    async def find(self, _what):
        raise BusyError(0.2)


def test_every_answer_has_a_sentence_to_say_even_when_a_backend_fails():
    """Whatever broke, the voice gets a sentence to read, and never a stack trace."""
    assert _call(_Broken())["say"] == BROKE
    assert _call(_NotSetUp())["say"] == NOT_SET_UP
    assert _call(_Busy())["say"] == BUSY_A_MOMENT


def test_our_own_short_wait_is_said_with_no_number_and_a_service_s_wait_in_seconds():
    """map-mcp's own pacing waits under a second, too short to count aloud; a 429's wait is said."""
    say = _call(_Busy())["say"]
    assert say == BUSY_A_MOMENT
    assert not any(c.isdigit() for c in say)
    kartverket = FakeKartverket()
    kartverket.busy_for = 30
    assert "30 seconds" in _call(kartverket)["say"]
