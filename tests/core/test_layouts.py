"""Tests for :mod:`perch.core.layouts`."""

from __future__ import annotations

import pytest

from perch.core.actions import (
    ApplyAction,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.layouts import (
    Layout,
    LayoutEntry,
    LayoutValidationError,
    parse_layouts,
)
from perch.core.matching import MatchPattern


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


def test_layout_window_invalid_match_rewrapped() -> None:
    """``MatchValidationError`` from inside a layout window surfaces as
    :class:`LayoutValidationError` so callers have a single exception."""
    with pytest.raises(LayoutValidationError, match="not a valid regex"):
        parse_layouts(
            {
                "coding": {
                    "windows": [
                        {
                            "match": {"title": r"[unclosed"},
                            "geometry": "maximize",
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


# ── with_overrides (profile override merging) ──────────────────────────────
def _entry(app_id: str, preset: str) -> LayoutEntry:
    return LayoutEntry(
        match=MatchPattern(app_id=app_id),
        apply=ApplyAction(geometry=PresetGeometry(name=preset)),
    )


def test_with_overrides_empty_is_identity() -> None:
    layout = Layout(name="coding", windows=(_entry("code", "left-half"),))
    assert layout.with_overrides(()) is layout


def test_with_overrides_replaces_matching_base_entry() -> None:
    base = Layout(
        name="coding",
        windows=(
            _entry("code", "left-half"),
            _entry("firefox", "right-half"),
        ),
    )
    override = _entry("code", "maximize")
    merged = base.with_overrides((override,))

    # `code` entry replaced, `firefox` untouched.
    assert merged.windows[0].apply.geometry == PresetGeometry(name="maximize")
    assert merged.windows[1].apply.geometry == PresetGeometry(name="right-half")


def test_with_overrides_appends_unmatched_entries() -> None:
    base = Layout(name="coding", windows=(_entry("code", "left-half"),))
    new_entry = _entry("konsole", "bottom-half")
    merged = base.with_overrides((new_entry,))
    assert len(merged.windows) == 2
    assert merged.windows[1].match.app_id == "konsole"


def test_with_overrides_preserves_name_and_description() -> None:
    base = Layout(
        name="coding",
        description="editor + browser",
        windows=(_entry("code", "left-half"),),
    )
    merged = base.with_overrides((_entry("code", "maximize"),))
    assert merged.name == "coding"
    assert merged.description == "editor + browser"


def test_with_overrides_match_compared_by_signature_not_identity() -> None:
    """Two ``MatchPattern`` s with identical source shape must compare equal
    for override purposes, even though their compiled regexes don't."""
    from perch.core.matching import parse_match

    base_match = parse_match({"app_id": "code", "title": r"main"}, "x")
    override_match = parse_match({"app_id": "code", "title": r"main"}, "y")

    base = Layout(
        name="l",
        windows=(LayoutEntry(
            match=base_match,
            apply=ApplyAction(geometry=PresetGeometry(name="left-half")),
        ),),
    )
    override = LayoutEntry(
        match=override_match,
        apply=ApplyAction(geometry=PresetGeometry(name="maximize")),
    )
    merged = base.with_overrides((override,))
    assert len(merged.windows) == 1
    assert merged.windows[0].apply.geometry == PresetGeometry(name="maximize")
