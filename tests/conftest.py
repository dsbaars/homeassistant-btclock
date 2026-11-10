"""Shared fixtures for BTClock integration tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import aioresponses.core as aioresponses_core
import pytest
from aiohttp import ClientResponse
from aioresponses import aioresponses

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _StreamWriterCompatResponse(ClientResponse):
    """ClientResponse that tolerates aioresponses omitting `stream_writer`.

    aiohttp 3.14 made `stream_writer` a required keyword-only argument of
    `ClientResponse.__init__`; aioresponses 0.7.9 (latest release) does not
    pass it, so every mocked request raises TypeError. aiohttp only reads
    `stream_writer.output_size`, so a stub is enough. Drop this shim once
    aioresponses ships a fix (pnuckowski/aioresponses#289, PR #288).
    """

    def __init__(self, *args: Any, stream_writer: Any = None, **kwargs: Any) -> None:
        if stream_writer is None:
            stream_writer = Mock(output_size=0)
        super().__init__(*args, stream_writer=stream_writer, **kwargs)


_NEEDS_STREAM_WRITER_SHIM = (
    "stream_writer" in inspect.signature(ClientResponse.__init__).parameters
)


@pytest.fixture
def mock_aioresponse():
    """Patch aiohttp so tests can stub BTClock HTTP responses."""
    if not _NEEDS_STREAM_WRITER_SHIM:
        with aioresponses() as m:
            yield m
        return
    with (
        patch.object(aioresponses_core, "ClientResponse", _StreamWriterCompatResponse),
        aioresponses() as m,
    ):
        yield m


@pytest.fixture
def load_fixture():
    """Load a JSON fixture from tests/fixtures/ by filename stem."""

    def _load(name: str) -> Any:
        path = FIXTURES_DIR / f"{name}.json"
        return json.loads(path.read_text())

    return _load
