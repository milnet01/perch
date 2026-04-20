"""Pure geometry math: frame-extents subtraction, monitor-of-window.

These helpers are the parts of the X11 backend that don't need a display —
they take ints and :class:`OutputInfo` lists and produce ints and names.
"""

from __future__ import annotations

from perch.backend.types import Geometry, OutputInfo
from perch.backend.x11.geometry import (
    FrameExtents,
    client_area_from_frame,
    monitor_for_geometry,
)


def _out(
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    primary: bool = False,
) -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=Geometry(x, y, w, h),
        work_area=Geometry(x, y, w, h),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=primary,
        is_connected=True,
    )


# ── client_area_from_frame ────────────────────────────────────────────────


def test_client_area_subtracts_decoration_thickness() -> None:
    got = client_area_from_frame(100, 40, 820, 640, FrameExtents(10, 10, 30, 10))
    assert got == Geometry(x=110, y=70, w=800, h=600)


def test_client_area_with_zero_extents_is_a_noop() -> None:
    got = client_area_from_frame(0, 0, 800, 600, FrameExtents.zero())
    assert got == Geometry(0, 0, 800, 600)


def test_client_area_clamps_negative_dimensions_to_zero() -> None:
    # Pathological: extents exceed the frame. Should not propagate as negative w/h.
    got = client_area_from_frame(0, 0, 10, 10, FrameExtents(20, 20, 20, 20))
    assert got.w == 0 and got.h == 0


# ── monitor_for_geometry ──────────────────────────────────────────────────


def test_monitor_for_geometry_picks_fully_contained_output() -> None:
    outputs = [
        _out("DP-1", 0, 0, 2560, 1440, primary=True),
        _out("HDMI-1", 2560, 0, 1920, 1080),
    ]
    got = monitor_for_geometry(Geometry(100, 100, 800, 600), outputs)
    assert got == "DP-1"


def test_monitor_for_geometry_picks_largest_overlap_when_straddling() -> None:
    outputs = [
        _out("DP-1", 0, 0, 2560, 1440),
        _out("HDMI-1", 2560, 0, 1920, 1080),
    ]
    # Window spans both monitors but most of it sits on DP-1.
    got = monitor_for_geometry(Geometry(2000, 100, 900, 600), outputs)
    assert got == "DP-1"


def test_monitor_for_geometry_tie_breaks_on_primary() -> None:
    outputs = [
        _out("DP-1", 0, 0, 1920, 1080, primary=True),
        _out("HDMI-1", 1920, 0, 1920, 1080),
    ]
    # Rect straddles the seam exactly 50/50 → tie.
    got = monitor_for_geometry(Geometry(1720, 0, 400, 1080), outputs)
    assert got == "DP-1"


def test_monitor_for_geometry_returns_none_when_fully_offscreen() -> None:
    outputs = [_out("DP-1", 0, 0, 1920, 1080, primary=True)]
    got = monitor_for_geometry(Geometry(5000, 5000, 100, 100), outputs)
    assert got is None


def test_monitor_for_geometry_returns_none_with_no_outputs() -> None:
    assert monitor_for_geometry(Geometry(0, 0, 10, 10), []) is None
