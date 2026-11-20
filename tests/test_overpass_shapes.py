"""The Overpass backend reads the answer Overpass documents, and the fake answers in that same shape.

`fixtures/overpass_shapes.json` holds Overpass's JSON answer for a cafe query with `out center`,
keys and types only. It is taken from Overpass's documented output format, since the one live
call allowed for it failed on 20.11. A node has its point, and a way has its centre.
"""

import asyncio
import json
import pathlib

import pytest

from map_mcp.backends import http, overpass
from map_mcp.fake import FakeOverpassHttp
from map_mcp.interfaces import Nearby

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures/overpass_shapes.json").read_text(encoding="utf-8"))
#: A made-up value for each type in a shape.
VALUES = {"str": "Prøve", "float": 0.01, "int": 1}


def _made_up(shape, element_type):
    if isinstance(shape, dict):
        return {k: element_type if k == "type" else _made_up(v, element_type) for k, v in shape.items()}
    if isinstance(shape, list):
        return [_made_up(item, element_type) for item in shape]
    return VALUES[shape]


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(v) for key, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _name_tag_only(shape):
    """The shape with only the name among an element's tags, the one tag the backend reads."""
    elements = [{**e, "tags": {"name": e["tags"]["name"]}} for e in shape["elements"]]
    return {**shape, "elements": elements}


class _Answers:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __call__(self, _url, _headers, _timeout):
        return http.Response(200, {}, self.body)


class _Clock:
    def __call__(self):
        return 1000.0


def _near(transport):
    backend = overpass.Overpass(transport=transport, limiter=http.Limiter(_Clock()))
    return asyncio.run(backend.nearby("cafe", 0.0, 0.0, 3000))


@pytest.mark.parametrize("element_type", sorted(SHAPES))
def test_an_answer_in_the_documented_shape_gives_a_place(element_type):
    found = _near(_Answers(_made_up(SHAPES[element_type], element_type)))
    assert [(p.name, p.lat, p.lon) for p in found] == [("Prøve", 0.01, 0.01)]


@pytest.mark.parametrize("element_type", sorted(SHAPES))
def test_the_fake_answers_in_the_documented_shape(element_type):
    fake = FakeOverpassHttp([Nearby(name="Prøve Kafé", kind="cafe", lat=0.0, lon=0.0)])
    fake.as_ways = element_type == "way"
    seen = []

    def recording(url, headers, timeout):
        answer = fake(url, headers, timeout)
        seen.append(json.loads(answer.body))
        return answer

    _near(recording)
    assert _shape(seen[0]) == _name_tag_only(SHAPES[element_type])
