"""Tests for :mod:`perch.core.snaps`."""

from __future__ import annotations

import pytest

from perch.core.actions import PercentGeometry
from perch.core.snaps import SnapValidationError, parse_snaps


def test_parse_snap_with_hotkey_and_monitor() -> None:
    snaps = parse_snaps(
        {
            "center-60": {
                "geometry": {
                    "x": "20%", "y": "20%", "w": "60%", "h": "60%",
                    "monitor": "current",
                },
                "hotkey": "Meta+C",
            }
        }
    )
    preset = snaps["center-60"]
    assert preset.name == "center-60"
    assert isinstance(preset.geometry, PercentGeometry)
    assert preset.monitor == "current"
    assert preset.hotkey == "Meta+C"


def test_parse_snap_without_monitor() -> None:
    snaps = parse_snaps(
        {
            "quarter": {
                "geometry": {"x": "0%", "y": "0%", "w": "25%", "h": "25%"}
            }
        }
    )
    assert snaps["quarter"].monitor is None
    assert snaps["quarter"].hotkey is None


def test_parse_snaps_missing_geometry_rejected() -> None:
    with pytest.raises(SnapValidationError, match="missing 'geometry'"):
        parse_snaps({"bad": {"hotkey": "Meta+B"}})


def test_parse_snaps_geometry_as_string_rejected() -> None:
    """Snap presets must be concrete geometries, not preset references."""
    with pytest.raises(SnapValidationError, match="concrete geometry"):
        parse_snaps({"alias": {"geometry": "maximize"}})


def test_parse_snaps_invalid_geometry_rejected() -> None:
    with pytest.raises(SnapValidationError, match=r"all integers.*percent"):
        parse_snaps(
            {
                "mixed": {
                    "geometry": {
                        "x": 0, "y": "0%", "w": 100, "h": 100,
                    }
                }
            }
        )


def test_parse_snaps_non_string_hotkey_rejected() -> None:
    with pytest.raises(SnapValidationError, match="hotkey must be a string"):
        parse_snaps(
            {
                "x": {
                    "geometry": {
                        "x": "0%", "y": "0%", "w": "100%", "h": "100%",
                    },
                    "hotkey": 42,
                }
            }
        )


def test_parse_snaps_unknown_key_rejected() -> None:
    with pytest.raises(SnapValidationError, match="unknown keys"):
        parse_snaps(
            {
                "x": {
                    "geometry": {
                        "x": "0%", "y": "0%", "w": "100%", "h": "100%",
                    },
                    "extra": True,
                }
            }
        )


def test_parse_snaps_empty_hotkey_rejected() -> None:
    with pytest.raises(SnapValidationError, match="must not be empty"):
        parse_snaps(
            {
                "x": {
                    "geometry": {
                        "x": "0%", "y": "0%", "w": "100%", "h": "100%",
                    },
                    "hotkey": "",
                }
            }
        )


def test_parse_snaps_empty_returns_empty() -> None:
    assert parse_snaps({}) == {}
