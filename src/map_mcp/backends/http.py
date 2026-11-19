"""The one way the backends reach a web service.

- Every request carries `USER_AGENT`: the plugin and its version, and no name, email or host.
- Each service has a `Limiter`. Asked sooner than it allows, it says how long to wait, and the
  voice says that. Nothing here sleeps or retries.
- A 429 is a wait. A 400 or a 422 is the service refusing the request. Anything else not a 200
  with JSON is the service failing.
- Every failure is caught here and raised as the plugin's own error, `from None`. Its text and
  the log name the backend, the kind of failure and the status only, never the URL, which holds
  what was searched for.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from map_mcp.interfaces import BusyError, QueryError, UnreachableError

#: The plugin's version, as pyproject.toml has it; a test keeps the two the same.
VERSION = "0.1.0"
USER_AGENT = f"map-mcp/{VERSION}"
#: How long one request may take before the voice is told the service isn't answering.
TIMEOUT = 8.0
#: The least time between two requests to one service: at most five a second.
MIN_INTERVAL = 0.2
#: HTTP's numbers for a request the service refuses: the address search sends 400, the
#: place-name search 422.
REFUSED = (400, 422)
#: The wait said for a 429 that names none.
DEFAULT_WAIT = 60.0

log = logging.getLogger("map_mcp.backends")


@dataclass(frozen=True)
class Response:
    """What a service answered: its status, its headers (names in lower case) and its body."""

    status: int
    headers: dict[str, str]
    body: bytes


#: Sends one GET: the URL, the request headers and the timeout in seconds.
Transport = Callable[[str, dict[str, str], float], Response]


def urllib_transport(url: str, headers: dict[str, str], timeout: float) -> Response:
    """Send one GET with the standard library; an HTTP error status is an answer, not a failure."""
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - the backends' own https URLs
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return Response(answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read())
    except urllib.error.HTTPError as refused:
        return Response(refused.code, {k.lower(): v for k, v in refused.headers.items()}, refused.read())


class Limiter:
    """One service's rate: at most one request every `MIN_INTERVAL` seconds."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Start with no request made; `clock` lets a test move time on."""
        self._clock = clock
        self._last: float | None = None

    def take(self) -> None:
        """Count one request, or say how long to wait when it comes too soon."""
        now = self._clock()
        # RULE: a service is asked at most five times a second
        if self._last is not None and now - self._last < MIN_INTERVAL:
            raise BusyError(MIN_INTERVAL - (now - self._last))
        self._last = now


async def get_json(
    backend: str,
    url: str,
    params: dict[str, str],
    *,
    transport: Transport,
    limiter: Limiter,
) -> Any:  # noqa: ANN401 - each backend reads its own service's shape
    """GET `url` with `params`, as `backend`, and return the parsed JSON body."""
    limiter.take()
    full = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        answer = await asyncio.to_thread(transport, full, headers, TIMEOUT)
    except Exception as broke:  # noqa: BLE001 - any failure to reach the service is the same to the voice
        _failed(backend, type(broke).__name__, None)
        # RULE: an error from a backend never carries the request
        msg = f"{backend} did not answer"
        raise UnreachableError(msg) from None
    # RULE: a busy answer is said as a wait
    if answer.status == 429:  # noqa: PLR2004 - HTTP's own number for too many requests
        _failed(backend, "busy", answer.status)
        raise BusyError(_retry_after(answer.headers))
    # RULE: an unprocessable search is a refusal not a failure
    if answer.status in REFUSED:
        _failed(backend, "refused", answer.status)
        msg = f"{backend} refused the request"
        raise QueryError(msg)
    if answer.status != 200:  # noqa: PLR2004
        _failed(backend, "status", answer.status)
        msg = f"{backend} answered {answer.status}"
        raise UnreachableError(msg)
    try:
        return json.loads(answer.body)
    except ValueError:
        _failed(backend, "not_json", answer.status)
        msg = f"{backend} answered with something that is not JSON"
        raise UnreachableError(msg) from None


def _retry_after(headers: dict[str, str]) -> float:
    """The wait a 429 names in seconds, or a minute when it names none or a date."""
    try:
        return max(1.0, float(headers["retry-after"]))
    except (KeyError, ValueError):
        return DEFAULT_WAIT


def _failed(backend: str, kind: str, status: int | None) -> None:
    """Log a failure by backend, kind and status only: never the URL or what was searched."""
    log.warning("%s failed: %s, status %s", backend, kind, status)
