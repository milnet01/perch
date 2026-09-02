"""Tests for :mod:`perch.core.resolver`.

Covers geometry pixel resolution (percent, absolute, preset), monitor
keyword resolution (``primary`` / ``current`` / index), snap expansion,
and the ``maximized=false + geometry`` unmaximize-first contract.
"""

from __future__ import annotations

import pytest

from perch.backend.types import (
    Geometry,
    OutputInfo,
    WindowInfo,
    WindowState,
    WindowType,
)
from perch.core.actions import (
    AbsoluteGeometry,
    ApplyAction,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.resolver import ResolveError, resolve_action
from perch.core.snaps import SnapPreset


def _w(monitor: str = "DP-1") -> WindowInfo:
    return WindowInfo(
        id="w",
        app_id="firefox",
        wm_class="firefox",
        title="",
        pid=None,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 800, 600),
        monitor=monitor,
        desktop=0,
    )


def _o(
    name: str,
    *,
    x: int = 0,
    y: int = 0,
    w: int = 1920,
    h: int = 1080,
    primary: bool = False,
    connected: bool = True,
) -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=Geometry(x, y, w, h),
        work_area=Geometry(x, y, w, h - 40),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=primary,
        is_connected=connected,
    )


@pytest.fixture
def outputs() -> list[OutputInfo]:
    return [
        _o("DP-1", x=0, y=0, w=2560, h=1440, primary=True),
        _o("HDMI-1", x=2560, y=360, w=1920, h=1080),
    ]


# ── Preset → pixels ───────────────────────────────────────────────────────
def test_maximize_preset_fills_work_area(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize")),
        _w(),
        outputs,
        {},
    )
    assert placement.geometry == Geometry(0, 0, 2560, 1400)  # 1440 - 40 panel


def test_left_half_preset(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="left-half")),
        _w(),
        outputs,
        {},
    )
    assert placement.geometry == Geometry(0, 0, 1280, 1400)


def test_unknown_preset_raises(outputs: list[OutputInfo]) -> None:
    with pytest.raises(ResolveError, match="unknown geometry preset"):
        resolve_action(
            ApplyAction(geometry=PresetGeometry(name="bogus")),
            _w(),
            outputs,
            {},
        )


# ── Percent geometry ──────────────────────────────────────────────────────
def test_percent_geometry_rounds_against_work_area(
    outputs: list[OutputInfo],
) -> None:
    placement = resolve_action(
        ApplyAction(
            geometry=PercentGeometry(x_pct=0.25, y_pct=0.0, w_pct=0.5, h_pct=1.0),
        ),
        _w(),
        outputs,
        {},
    )
    assert placement.geometry == Geometry(640, 0, 1280, 1400)


def test_percent_geometry_targets_named_monitor(
    outputs: list[OutputInfo],
) -> None:
    placement = resolve_action(
        ApplyAction(
            geometry=PercentGeometry(x_pct=0.0, y_pct=0.0, w_pct=1.0, h_pct=1.0),
            monitor="HDMI-1",
        ),
        _w(),
        outputs,
        {},
    )
    # HDMI-1 work area: (2560, 360, 1920, 1040)
    assert placement.monitor == "HDMI-1"
    assert placement.geometry == Geometry(2560, 360, 1920, 1040)


# ── Absolute geometry ─────────────────────────────────────────────────────
def test_absolute_geometry_clamped_to_work_area(
    outputs: list[OutputInfo],
) -> None:
    """A too-big absolute rectangle shrinks to the work area, not off-screen."""
    placement = resolve_action(
        ApplyAction(
            geometry=AbsoluteGeometry(x=10_000, y=10_000, w=500, h=500)
        ),
        _w(),
        outputs,
        {},
    )
    geom = placement.geometry
    assert geom is not None
    # The rectangle is pushed back inside DP-1's work area.
    assert geom.x + geom.w <= 2560
    assert geom.y + geom.h <= 1400


# ── Monitor keywords ──────────────────────────────────────────────────────
def test_monitor_primary(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), monitor="primary"),
        _w(monitor="HDMI-1"),
        outputs,
        {},
    )
    assert placement.monitor == "DP-1"


def test_monitor_current(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), monitor="current"),
        _w(monitor="HDMI-1"),
        outputs,
        {},
    )
    assert placement.monitor == "HDMI-1"


def test_monitor_index_via_profile(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), monitor=1),
        _w(),
        outputs,
        {},
        profile_outputs=["DP-1", "HDMI-1"],
    )
    assert placement.monitor == "HDMI-1"


def test_monitor_index_without_profile_raises(
    outputs: list[OutputInfo],
) -> None:
    with pytest.raises(ResolveError, match="no active profile"):
        resolve_action(
            ApplyAction(geometry=PresetGeometry(name="maximize"), monitor=0),
            _w(),
            outputs,
            {},
        )


def test_monitor_index_out_of_range_raises(
    outputs: list[OutputInfo],
) -> None:
    with pytest.raises(ResolveError, match="exceeds"):
        resolve_action(
            ApplyAction(geometry=PresetGeometry(name="maximize"), monitor=5),
            _w(),
            outputs,
            {},
            profile_outputs=["DP-1", "HDMI-1"],
        )


def test_monitor_disconnected_raises(outputs: list[OutputInfo]) -> None:
    outputs[1] = _o("HDMI-1", x=2560, y=360, w=1920, h=1080, connected=False)
    with pytest.raises(ResolveError, match="not currently connected"):
        resolve_action(
            ApplyAction(geometry=PresetGeometry(name="maximize"), monitor="HDMI-1"),
            _w(),
            outputs,
            {},
        )


def test_monitor_primary_none_connected_raises() -> None:
    outputs = [_o("DP-1", primary=True, connected=False)]
    with pytest.raises(ResolveError, match="no primary output"):
        resolve_action(
            ApplyAction(geometry=PresetGeometry(name="maximize"), monitor="primary"),
            _w(),
            outputs,
            {},
        )



# ── Snap expansion ────────────────────────────────────────────────────────
def test_snap_builtin_name(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(snap="left-half"),
        _w(),
        outputs,
        {},
    )
    assert placement.geometry == Geometry(0, 0, 1280, 1400)


def test_snap_user_overrides_builtin(outputs: list[OutputInfo]) -> None:
    """User snaps with the same name as a built-in shadow it."""
    snaps = {
        "left-half": SnapPreset(
            name="left-half",
            geometry=PercentGeometry(0.0, 0.0, 0.25, 1.0),  # narrower quarter
        )
    }
    placement = resolve_action(
        ApplyAction(snap="left-half"),
        _w(),
        outputs,
        snaps,
    )
    assert placement.geometry == Geometry(0, 0, 640, 1400)


def test_snap_preset_carries_monitor(outputs: list[OutputInfo]) -> None:
    snaps = {
        "right-screen": SnapPreset(
            name="right-screen",
            geometry=PercentGeometry(0.0, 0.0, 1.0, 1.0),
            monitor="HDMI-1",
        )
    }
    placement = resolve_action(
        ApplyAction(snap="right-screen"),
        _w(monitor="DP-1"),
        outputs,
        snaps,
    )
    assert placement.monitor == "HDMI-1"


def test_snap_unknown_raises(outputs: list[OutputInfo]) -> None:
    with pytest.raises(ResolveError, match="unknown snap"):
        resolve_action(
            ApplyAction(snap="no-such-snap"), _w(), outputs, {}
        )


# ── Desktop ────────────────────────────────────────────────────────────────
def test_desktop_integer(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), desktop=2),
        _w(),
        outputs,
        {},
    )
    assert placement.desktop == 2


def test_desktop_current(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), desktop="current"),
        _w(),
        outputs,
        {},
    )
    assert placement.desktop == 0


def test_desktop_all_maps_to_sticky(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(geometry=PresetGeometry(name="maximize"), desktop="all"),
        _w(),
        outputs,
        {},
    )
    assert placement.desktop == -1


# ── Maximize contract ─────────────────────────────────────────────────────
def test_maximized_true_alone(outputs: list[OutputInfo]) -> None:
    placement = resolve_action(
        ApplyAction(maximized=True), _w(), outputs, {}
    )
    assert placement.maximized is True
    assert placement.geometry is None
    assert not placement.unmaximize_first


def test_maximized_false_alone(outputs: list[OutputInfo]) -> None:
    # docs/07 §Apply order step 1 makes the unmaximize unconditional on an
    # explicit ``maximized = false``, so it is carried by unmaximize_first
    # rather than by a post-geometry ``maximized`` of False.
    placement = resolve_action(
        ApplyAction(maximized=False), _w(), outputs, {}
    )
    assert placement.maximized is None
    assert placement.unmaximize_first


def test_maximized_false_with_monitor_only_flags_unmaximize_first(
    outputs: list[OutputInfo],
) -> None:
    """A monitor move carries no geometry and must still unmaximize first.

    This is the case docs/07 §Apply order step 1 exists for: on a backend
    that ignores writes to a maximized window, the move is dropped unless
    the unmaximize precedes it.
    """
    placement = resolve_action(
        ApplyAction(monitor="HDMI-1", maximized=False), _w(), outputs, {}
    )
    assert placement.geometry is None
    assert placement.monitor == "HDMI-1"
    assert placement.unmaximize_first


def test_percent_geometry_is_clamped_into_the_work_area(
    outputs: list[OutputInfo],
) -> None:
    """docs/07 §Geometry resolution: a rule cannot push a window off-screen.

    Percentages are not range-checked at parse time, so the resolver is the
    only place a negative or oversized one can be caught.
    """
    placement = resolve_action(
        ApplyAction(
            geometry=PercentGeometry(
                x_pct=-0.5, y_pct=-0.5, w_pct=0.5, h_pct=0.5
            )
        ),
        _w(),
        outputs,
        {},
    )
    work_area = outputs[0].work_area
    assert placement.geometry is not None
    assert placement.geometry.x >= work_area.x
    assert placement.geometry.y >= work_area.y


def test_oversized_percent_geometry_shrinks_to_the_work_area(
    outputs: list[OutputInfo],
) -> None:
    placement = resolve_action(
        ApplyAction(
            geometry=PercentGeometry(x_pct=0.0, y_pct=0.0, w_pct=5.0, h_pct=5.0)
        ),
        _w(),
        outputs,
        {},
    )
    assert placement.geometry == outputs[0].work_area


def test_maximized_false_with_geometry_flags_unmaximize_first(
    outputs: list[OutputInfo],
) -> None:
    placement = resolve_action(
        ApplyAction(
            geometry=PresetGeometry(name="left-half"), maximized=False
        ),
        _w(),
        outputs,
        {},
    )
    assert placement.unmaximize_first is True
    # When we unmaximize first, the resolver must clear ``maximized`` so the
    # reducer doesn't double-issue ``set_state(NORMAL)``.
    assert placement.maximized is None
    assert placement.geometry == Geometry(0, 0, 1280, 1400)
