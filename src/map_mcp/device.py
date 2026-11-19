"""What the plugin needs from a source, and the ways asking one can fail.

The service talks to this and nothing else. The fake (`fake.py`) and the real adapter both
answer it, so every test runs through the same door the real device does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class DeviceError(Exception):
    """Asking the source failed; each kind below is said to the voice in its own words."""


class UnreachableError(DeviceError):
    """The source did not answer in time."""


class SlowDownError(DeviceError):
    """The source refuses to be asked again so soon."""

    def __init__(self, seconds: float) -> None:
        """Keep how long to wait, so the voice can say it."""
        super().__init__(f"ask again in {seconds:.0f} s")
        self.seconds = seconds


class NotSetUpError(DeviceError):
    """No real source is set up, so nothing was asked."""


@dataclass(frozen=True)
class Reading:
    """What the source says about itself: whether it is on, and its level from 0 to 100."""

    on: bool
    level: int


class Source(Protocol):
    """A source the plugin can read."""

    async def read(self) -> Reading:
        """The source's state now."""
        ...


class Unconnected:
    """The real source, until an adapter for it is written: every read says so."""

    async def read(self) -> Reading:
        """Refuse, naming the next step."""
        msg = "no adapter for a real source is written yet; run with --simulate"
        raise NotSetUpError(msg)
