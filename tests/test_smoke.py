"""Smoke test — confirms the test harness can load the integration manifest."""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).parents[1] / "custom_components" / "btclock" / "manifest.json"


def test_manifest_has_domain() -> None:
    data = json.loads(MANIFEST.read_text())
    assert data["domain"] == "btclock"
