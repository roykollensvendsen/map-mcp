"""The fake refuses what the real source refuses, so a test cannot pass that the device would fail."""

import asyncio

import pytest

from map_mcp.device import NotSetUpError, SlowDownError, Unconnected, UnreachableError
from map_mcp.fake import READS_PER_MINUTE, WINDOW, FakeSource


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_fake_refuses_a_read_sooner_than_the_device_allows():
    clock = _Clock()
    source = FakeSource(clock=clock)
    for _ in range(READS_PER_MINUTE):
        asyncio.run(source.read())
    with pytest.raises(SlowDownError) as slow:
        asyncio.run(source.read())
    assert slow.value.seconds == WINDOW


def test_the_fake_answers_again_once_the_minute_has_passed():
    clock = _Clock()
    source = FakeSource(clock=clock)
    for _ in range(READS_PER_MINUTE):
        asyncio.run(source.read())
    clock.now = WINDOW
    assert asyncio.run(source.read()).level == 40


def test_a_fake_off_the_network_answers_nothing():
    source = FakeSource()
    source.unreachable = True
    with pytest.raises(UnreachableError):
        asyncio.run(source.read())


def test_an_unconnected_source_says_what_to_do():
    with pytest.raises(NotSetUpError, match="--simulate"):
        asyncio.run(Unconnected().read())
