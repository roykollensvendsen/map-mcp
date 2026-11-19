"""Each backend reads the answer Kartverket really sends, and the fake answers in that same shape.

`fixtures/kartverket_shapes.json` holds one live answer per service, recorded on 19.11 with the
backends' own parameters, keys and types only, never a value. A key the backend expects that the
service does not send would drop every place without a word, so the shape is checked here.
"""

import asyncio
import json
import pathlib

import pytest

from map_mcp.backends import http
from map_mcp.backends.kartverket_address import KartverketAddress
from map_mcp.backends.kartverket_names import KartverketNames
from map_mcp.fake import FakeKartverketHttp

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures/kartverket_shapes.json").read_text(encoding="utf-8"))
#: A made-up value for each type in a shape.
VALUES = {"str": "Prøve", "float": 0.01, "int": 1, "bool": True}
BACKENDS = {"address": (KartverketAddress, "Prøvestien"), "names": (KartverketNames, "Prøvevatnet")}


def _made_up(shape):
    if isinstance(shape, dict):
        return {key: _made_up(value) for key, value in shape.items()}
    if isinstance(shape, list):
        return [_made_up(item) for item in shape]
    return VALUES[shape]


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(v) for key, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


class _Answers:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __call__(self, _url, _headers, _timeout):
        return http.Response(200, {}, self.body)


class _Clock:
    def __call__(self):
        return 1000.0


@pytest.mark.parametrize("service", sorted(BACKENDS))
def test_an_answer_in_the_live_shape_gives_a_place(service):
    backend, _ = BACKENDS[service]
    found = asyncio.run(
        backend(transport=_Answers(_made_up(SHAPES[service])), limiter=http.Limiter(_Clock())).find("x")
    )
    assert len(found) == 1


@pytest.mark.parametrize("service", sorted(BACKENDS))
def test_the_fake_answers_in_the_live_shape(service):
    backend, what = BACKENDS[service]
    fake = FakeKartverketHttp()
    seen = []

    def recording(url, headers, timeout):
        answer = fake(url, headers, timeout)
        seen.append(json.loads(answer.body))
        return answer

    asyncio.run(backend(transport=recording, limiter=http.Limiter(_Clock())).find(what))
    assert _shape(seen[0]) == SHAPES[service]
