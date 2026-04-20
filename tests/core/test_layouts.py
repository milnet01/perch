"""Tests for :mod:`perch.core.layouts`."""

from __future__ import annotations

import pytest

from perch.core.actions import PercentGeometry, PresetGeometry
from perch.core.layouts import LayoutValidationError, parse_layouts


def test_parse_minimal_layout() -> None:
    layouts = parse_layouts(
        {"coding": {"description": "Editor + browser"}}
    )
    assert layouts["coding"].name == "coding"
    assert layouts["coding"].description == "Editor + browser"
    assert layouts["coding"].windows == ()


def test_parse_layout_with_windows() -> None:
    layouts = parse_layouts(
        {
            "coding": {
                "description": "Editor + browser",
                "windows": [
                    {
                        "match": {"app_id": "code"},
                        "geometry": {
                            "x": "0%", "y": "0%", "w": "60%", "h": "100%",
                            "monitor": "primary",
                        },
                    },
                    {
                        "match": {"app_id": "firefox"},
                        "geometry": "maximize",
                        "monitor": "HDMI-1",
                    },
                ],
            }
        }
    )
    entries = layouts["coding"].windows
    assert len(entries) == 2
    assert entries[0].match.app_id == "code"
    assert isinstance(entries[0].apply.geometry, PercentGeometry)
    assert entries[0].apply.monitor == "primary"
    assert entries[1].apply.geometry == PresetGeometry(name="maximize")


def test_layout_empty_name_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="must not be empty"):
        parse_layouts({"": {"description": "x"}})


def test_layout_non_table_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="must be a table"):
        parse_layouts({"coding": "not a table"})


def test_layout_unknown_key_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="unknown keys"):
        parse_layouts({"coding": {"description": "x", "bogus": True}})


def test_layout_non_string_description_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="description must be a string"):
        parse_layouts({"coding": {"description": 42}})


def test_layout_windows_must_be_list() -> None:
    with pytest.raises(LayoutValidationError, match="array of tables"):
        parse_layouts({"coding": {"windows": "nope"}})


def test_layout_window_missing_match_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="missing 'match'"):
        parse_layouts(
            {
                "coding": {
                    "windows": [{"geometry": "maximize"}],
                }
            }
        )


def test_layout_window_empty_match_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="empty match"):
        parse_layouts(
            {
                "coding": {
                    "windows": [
                        {"match": {}, "geometry": "maximize"},
                    ],
                }
            }
        )


def test_layout_window_unknown_key_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="unknown keys"):
        parse_layouts(
            {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "x"},
                            "geometry": "maximize",
                            "colour": "blue",
                        }
                    ],
                }
            }
        )


def test_layout_window_contradictory_action_rewrapped() -> None:
    with pytest.raises(LayoutValidationError, match="contradiction"):
        parse_layouts(
            {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "x"},
                            "maximized": True,
                            "geometry": "maximize",
                        }
                    ],
                }
            }
        )
