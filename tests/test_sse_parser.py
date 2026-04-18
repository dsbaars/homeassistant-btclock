"""Test the SSE frame parser in isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.btclock.sse import _iter_events


class _FakeContent:
    """Minimal aiohttp.ClientResponse.content stand-in that yields bytes."""

    def __init__(self, raw: bytes) -> None:
        self._lines = raw.splitlines(keepends=True)

    def __aiter__(self):
        self._iter = iter(self._lines)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as err:
            raise StopAsyncIteration from err


class _FakeResponse:
    def __init__(self, raw: bytes) -> None:
        self.content = _FakeContent(raw)


@pytest.fixture
def sample_stream() -> bytes:
    path = Path(__file__).parent / "fixtures" / "events_sample.txt"
    # The HTTP spec says SSE frames use \n — read as bytes and normalise.
    return path.read_text().encode("utf-8").replace(b"\r\n", b"\n")


async def test_parses_welcome_and_two_status_frames(sample_stream: bytes) -> None:
    resp = _FakeResponse(sample_stream)
    events = [(name, raw) async for name, raw in _iter_events(resp)]

    names = [name for name, _ in events]
    assert names == ["welcome", "status", "status"]

    import json

    first_status = json.loads(events[1][1])
    second_status = json.loads(events[2][1])
    assert first_status["currentScreen"] == 0
    assert second_status["currentScreen"] == 3


async def test_ignores_comment_lines() -> None:
    raw = b': keepalive\n\nevent: status\ndata: {"x":1}\n\n'
    resp = _FakeResponse(raw)
    events = [(name, data) async for name, data in _iter_events(resp)]
    assert events == [("status", '{"x":1}')]


async def test_multiline_data_joins_with_newlines() -> None:
    raw = b"event: status\ndata: line1\ndata: line2\n\n"
    resp = _FakeResponse(raw)
    events = [(name, data) async for name, data in _iter_events(resp)]
    assert events == [("status", "line1\nline2")]


async def test_unnamed_event_defaults_to_message() -> None:
    raw = b"data: hello\n\n"
    resp = _FakeResponse(raw)
    events = [(name, data) async for name, data in _iter_events(resp)]
    assert events == [("message", "hello")]
