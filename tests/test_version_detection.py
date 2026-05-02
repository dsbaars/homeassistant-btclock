"""Test firmware variant detection from /api/settings responses."""

from __future__ import annotations

import pytest

from custom_components.btclock.api import detect_variant
from custom_components.btclock.models import ApiVariant


def test_legacy_fixture_detects_as_legacy(load_fixture) -> None:
    assert detect_variant(load_fixture("settings_legacy")) is ApiVariant.LEGACY


def test_v3_4_revb_fixture_detects_as_v3_4(load_fixture) -> None:
    assert detect_variant(load_fixture("settings_v3_4_revb")) is ApiVariant.V3_4


def test_v3_4_reva_fixture_detects_as_v3_4(load_fixture) -> None:
    assert detect_variant(load_fixture("settings_v3_4_reva")) is ApiVariant.V3_4


def test_v3_4_authed_fixture_detects_as_v3_4(load_fixture) -> None:
    assert detect_variant(load_fixture("settings_v3_4_authed")) is ApiVariant.V3_4


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("3.4.0", ApiVariant.V3_4),
        ("v3.4.0", ApiVariant.V3_4),
        ("3.4.1", ApiVariant.V3_4),
        ("3.5.0", ApiVariant.V3_4),
        ("4.0.0", ApiVariant.V4),
        ("4.0.0-beta.1", ApiVariant.V4),
        ("v4.1.2", ApiVariant.V4),
        ("3.3.19", ApiVariant.LEGACY),
        ("3.0.0", ApiVariant.LEGACY),
        ("", ApiVariant.LEGACY),
        ("garbage", ApiVariant.LEGACY),
    ],
)
def test_gitTag_parsing(tag: str, expected: ApiVariant) -> None:
    # Only gitTag present — no other signals that would flip the answer.
    assert detect_variant({"gitTag": tag}) is expected


@pytest.mark.parametrize(
    "rev, expected",
    [
        ("4.0.0", ApiVariant.V4),
        ("4.0.0-beta.1", ApiVariant.V4),
        ("v4.1.0", ApiVariant.V4),
        # `git describe` past-tag form still parses major correctly.
        ("4.0.0-3-gabc1234", ApiVariant.V4),
    ],
)
def test_gitRev_falls_back_when_gitTag_absent(rev: str, expected: ApiVariant) -> None:
    # v4 firmware never fills gitTag — only gitRev.
    assert detect_variant({"gitRev": rev}) is expected


def test_httpAuthPassSet_presence_wins_over_missing_tag() -> None:
    # Untagged 3.4.0 build: gitTag absent, but the new boolean field is present.
    assert detect_variant({"httpAuthPassSet": False}) is ApiVariant.V3_4


def test_legacy_httpAuthPass_string_does_not_trigger_v3_4() -> None:
    # Legacy firmware returns a plaintext `httpAuthPass` string — this must NOT
    # be confused with the new `httpAuthPassSet` boolean.
    assert detect_variant({"httpAuthPass": "hunter2"}) is ApiVariant.LEGACY


def test_lastBuildTime_fallback_post_cutoff() -> None:
    # Build after the 3.4.0 cutoff with no tag and no httpAuthPassSet still
    # resolves to V3_4.
    assert detect_variant({"lastBuildTime": "1744934400"}) is ApiVariant.V3_4


def test_lastBuildTime_fallback_pre_cutoff() -> None:
    assert detect_variant({"lastBuildTime": "1700000000"}) is ApiVariant.LEGACY


def test_empty_settings_defaults_to_legacy() -> None:
    assert detect_variant({}) is ApiVariant.LEGACY


def test_v4_firmware_with_gitRev_detects_as_v4() -> None:
    # v4 firmware fills `gitRev` (`git describe` output) but never `gitTag`.
    # Variant detection must classify it as V4 so the v4-only path-table
    # entries (simulate_zap, factory_reset, …) become available.
    settings = {
        "gitRev": "4.0.0-beta.1",
        "httpAuthPassSet": False,
    }
    assert detect_variant(settings) is ApiVariant.V4
