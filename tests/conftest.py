"""Shared fixtures for BTClock integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from aioresponses import aioresponses

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/btclock in every test."""
    yield


@pytest.fixture
def mock_aioresponse():
    """Patch aiohttp so tests can stub BTClock HTTP responses."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def load_fixture():
    """Load a JSON fixture from tests/fixtures/ by filename stem."""

    def _load(name: str) -> Any:
        path = FIXTURES_DIR / f"{name}.json"
        return json.loads(path.read_text())

    return _load
