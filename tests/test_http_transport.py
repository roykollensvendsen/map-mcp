"""The standard-library transport, with urlopen stood in for, so no test reaches the network."""

import email.message
import io
import urllib.error
import urllib.request

from map_mcp.backends import http


class _Answer:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._body


def _headers(**pairs):
    headers = email.message.Message()
    for name, value in pairs.items():
        headers[name.replace("_", "-")] = value
    return headers


def test_an_answer_comes_back_with_its_status_its_body_and_its_headers_in_lower_case(monkeypatch):
    sent = {}

    def urlopen(request, timeout):
        sent.update(url=request.full_url, agent=request.get_header("User-agent"), timeout=timeout)
        return _Answer(200, _headers(Content_Type="application/json"), b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    answer = http.urllib_transport("https://example.invalid/sok?sok=x", {"User-Agent": http.USER_AGENT}, 8.0)
    assert (answer.status, answer.headers, answer.body) == (200, {"content-type": "application/json"}, b"{}")
    assert sent == {"url": "https://example.invalid/sok?sok=x", "agent": http.USER_AGENT, "timeout": 8.0}


def test_an_http_error_status_is_an_answer_not_a_failure(monkeypatch):
    """The standard library raises on a 429 or a 500; the layer above decides what each means."""

    def urlopen(request, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(request.full_url, 429, "busy", _headers(Retry_After="30"), io.BytesIO(b""))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    answer = http.urllib_transport("https://example.invalid/sok", {}, 8.0)
    assert (answer.status, answer.headers["retry-after"]) == (429, "30")
