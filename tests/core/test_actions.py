"""Tests for :mod:`perch.core.actions` — the apply-action parser."""

from __future__ import annotations

import pytest

from perch.core.actions import (
    AbsoluteGeometry,
    ActionValidationError,
    PercentGeometry,
    PresetGeometry,
    parse_action,
)


# ── Empty / shape ──────────────────────────────────────────────────────────
def test_empty_apply_rejected() -> None:
    with pytest.raises(ActionValidationError, match="no effect"):
        parse_action({}, "x")


def test_non_table_rejected() -> None:
    with pytest.raises(ActionValidationError, match="must be a table"):
        parse_action("maximize", "x")


def test_unknown_key_rejected() -> None:
    with pytest.raises(ActionValidationError, match="unknown keys"):
        parse_action({"maximise": True}, "x")  # nope — British spelling


# ── Geometry: preset string ────────────────────────────────────────────────
def test_preset_geometry_from_string() -> None:
    a = parse_action({"geometry": "left-half"}, "x")
    assert a.geometry == PresetGeometry(name="left-half")


def test_empty_preset_name_rejected() -> None:
    with pytest.raises(ActionValidationError, match="preset name must not be empty"):
        parse_action({"geometry": "   "}, "x")


# ── Geometry: absolute ─────────────────────────────────────────────────────
def test_absolute_geometry() -> None:
    a = parse_action(
        {
            "geometry": {"x": 10, "y": 20, "w": 800, "h": 600},
        },
        "x",
    )
    assert a.geometry == AbsoluteGeometry(10, 20, 800, 600)


def test_absolute_geometry_accepts_monitor_inside() -> None:
    a = parse_action(
        {
            "geometry": {
                "x": 10, "y": 20, "w": 800, "h": 600,
                "monitor": "DP-1",
            }
        },
        "x",
    )
    assert a.geometry == AbsoluteGeometry(10, 20, 800, 600)
    assert a.monitor == "DP-1"


# ── Geometry: percent ──────────────────────────────────────────────────────
def test_percent_geometry() -> None:
    a = parse_action(
        {
            "geometry": {"x": "0%", "y": "0%", "w": "60%", "h": "70%"},
        },
        "x",
    )
    assert isinstance(a.geometry, PercentGeometry)
    assert a.geometry.w_pct == pytest.approx(0.6)


def test_percent_with_space_and_decimal() -> None:
    a = parse_action(
        {"geometry": {"x": "0%", "y": "0%", "w": "12.5 %", "h": "87.5%"}},
        "x",
    )
    assert isinstance(a.geometry, PercentGeometry)
    assert a.geometry.w_pct == pytest.approx(0.125)
    assert a.geometry.h_pct == pytest.approx(0.875)


# ── Geometry: rejections ───────────────────────────────────────────────────
def test_mixed_int_and_percent_rejected() -> None:
    with pytest.raises(
        ActionValidationError,
        match=r"all integers.*all percent strings",
    ):
        parse_action(
            {"geometry": {"x": 0, "y": "0%", "w": 800, "h": 600}},
            "x",
        )


def test_missing_geometry_field_rejected() -> None:
    with pytest.raises(ActionValidationError, match="missing 'h'"):
        parse_action({"geometry": {"x": 0, "y": 0, "w": 800}}, "x")


def test_geometry_unknown_key_rejected() -> None:
    with pytest.raises(ActionValidationError, match="unknown keys"):
        parse_action(
            {"geometry": {"x": 0, "y": 0, "w": 1, "h": 1, "z": 99}},
            "x",
        )


def test_geometry_invalid_shape_rejected() -> None:
    with pytest.raises(ActionValidationError, match=r"preset name .* or a table"):
        parse_action({"geometry": 42}, "x")


# ── Monitor handling ───────────────────────────────────────────────────────
def test_monitor_at_apply_level() -> None:
    a = parse_action(
        {"geometry": "maximize", "monitor": "HDMI-1"}, "x"
    )
    assert a.monitor == "HDMI-1"


def test_monitor_integer_index() -> None:
    a = parse_action({"geometry": "maximize", "monitor": 1}, "x")
    assert a.monitor == 1


def test_monitor_negative_index_rejected() -> None:
    with pytest.raises(ActionValidationError, match="non-negative"):
        parse_action({"geometry": "maximize", "monitor": -1}, "x")


def test_monitor_bool_rejected() -> None:
    with pytest.raises(ActionValidationError):
        parse_action({"geometry": "maximize", "monitor": True}, "x")


def test_monitor_in_both_places_conflict_rejected() -> None:
    with pytest.raises(ActionValidationError, match="specified both"):
        parse_action(
            {
                "geometry": {
                    "x": 0, "y": 0, "w": 1, "h": 1,
                    "monitor": "DP-1",
                },
                "monitor": "HDMI-1",
            },
            "x",
        )


def test_monitor_in_both_places_agreement_allowed() -> None:
    """Redundant-but-agreeing specification is accepted."""
    a = parse_action(
        {
            "geometry": {
                "x": 0, "y": 0, "w": 100, "h": 100,
                "monitor": "DP-1",
            },
            "monitor": "DP-1",
        },
        "x",
    )
    assert a.monitor == "DP-1"


# ── Maximized ──────────────────────────────────────────────────────────────
def test_maximized_true_standalone() -> None:
    a = parse_action({"maximized": True}, "x")
    assert a.maximized is True
    assert a.geometry is None


def test_maximized_false_standalone_allowed() -> None:
    """``maximized = false`` alone is a legitimate unmaximize command."""
    a = parse_action({"maximized": False}, "x")
    assert a.maximized is False
    assert a.geometry is None


def test_maximized_false_with_geometry_allowed() -> None:
    a = parse_action(
        {"maximized": False, "geometry": "left-half"}, "x"
    )
    assert a.maximized is False
    assert a.geometry == PresetGeometry(name="left-half")


def test_maximized_true_with_geometry_rejected() -> None:
    with pytest.raises(ActionValidationError, match="contradiction"):
        parse_action(
            {"maximized": True, "geometry": "left-half"}, "x"
        )


def test_maximized_true_with_snap_rejected() -> None:
    with pytest.raises(ActionValidationError, match="contradiction"):
        parse_action(
            {"maximized": True, "snap": "center-60"}, "x"
        )


def test_geometry_and_snap_are_mutually_exclusive() -> None:
    with pytest.raises(ActionValidationError, match="mutually exclusive"):
        parse_action(
            {"geometry": "left-half", "snap": "center-60"}, "x"
        )


def test_non_bool_maximized_rejected() -> None:
    with pytest.raises(ActionValidationError, match="must be a boolean"):
        parse_action({"maximized": "yes"}, "x")


# ── Desktop ────────────────────────────────────────────────────────────────
def test_desktop_integer() -> None:
    a = parse_action({"geometry": "maximize", "desktop": 2}, "x")
    assert a.desktop == 2


def test_desktop_string_current() -> None:
    a = parse_action({"geometry": "maximize", "desktop": "current"}, "x")
    assert a.desktop == "current"


def test_desktop_string_invalid_rejected() -> None:
    with pytest.raises(ActionValidationError, match="'current' or 'all'"):
        parse_action({"geometry": "maximize", "desktop": "maybe"}, "x")


def test_desktop_negative_rejected() -> None:
    with pytest.raises(ActionValidationError, match="non-negative"):
        parse_action({"geometry": "maximize", "desktop": -1}, "x")


def test_desktop_only_is_valid_effect() -> None:
    """Just setting desktop is a legitimate action — move to another desktop."""
    a = parse_action({"desktop": 1}, "x")
    assert a.desktop == 1


# ── Snap ───────────────────────────────────────────────────────────────────
def test_snap_alone() -> None:
    a = parse_action({"snap": "center-60"}, "x")
    assert a.snap == "center-60"


def test_empty_snap_rejected() -> None:
    with pytest.raises(ActionValidationError, match="must not be empty"):
        parse_action({"snap": ""}, "x")
