"""Unit tests for :mod:`perch.backend.x11.outputs`.

The ``list_outputs`` path that actually touches a display is exercised in
``test_live_openbox.py`` under Xvfb (M4.g). The pure math here — refresh
computation and work-area intersection — is what this module tests.
"""

from __future__ import annotations

from perch.backend.types import Geometry, OutputInfo
from perch.backend.x11.outputs import apply_workarea, refresh_mhz


def _out(
    name: str,
    geom: Geometry,
    *,
    connected: bool = True,
    primary: bool = False,
) -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=geom,
        work_area=geom,
        scale=1.0,
        refresh_mhz=60000,
        is_primary=primary,
        is_connected=connected,
    )


# ── refresh_mhz ────────────────────────────────────────────────────────────


def test_refresh_mhz_typical_1920x1080_60hz() -> None:
    # Real numbers from a stock 1920x1080@60 CVT mode.
    got = refresh_mhz(dot_clock=148_500_000, h_total=2200, v_total=1125)
    # 148.5M / (2200*1125) = 60.0 Hz → 60000 mHz
    assert got == 60000


def test_refresh_mhz_144hz_sample() -> None:
    got = refresh_mhz(dot_clock=533_250_000, h_total=2720, v_total=1481)
    # ~132.4 Hz — exact number doesn't matter; just check it rounds sanely.
    assert 130_000 <= got <= 135_000


def test_refresh_mhz_zero_dotclock_returns_zero() -> None:
    # Happens for a CRTC that's off or advertising a "None" mode.
    assert refresh_mhz(dot_clock=0, h_total=2200, v_total=1125) == 0


def test_refresh_mhz_zero_total_returns_zero() -> None:
    assert refresh_mhz(dot_clock=148_500_000, h_total=0, v_total=1125) == 0


# ── apply_workarea ────────────────────────────────────────────────────────


def test_apply_workarea_intersects_each_output_with_root_workarea() -> None:
    outputs = [
        _out("DP-1", Geometry(0, 0, 2560, 1440), primary=True),
        _out("HDMI-1", Geometry(2560, 0, 1920, 1080)),
    ]
    # A panel at the top of the virtual root reserves 40 px of y.
    workarea = Geometry(0, 40, 4480, 1400)
    got = apply_workarea(outputs, workarea)

    assert got[0].work_area == Geometry(0, 40, 2560, 1400)
    # HDMI-1 is 1080 tall; intersected with y=40..1440 and its own
    # y=0..1080 leaves y=40..1080 = 1040 height.
    assert got[1].work_area == Geometry(2560, 40, 1920, 1040)


def test_apply_workarea_leaves_geometry_field_untouched() -> None:
    outputs = [_out("DP-1", Geometry(0, 0, 2560, 1440))]
    got = apply_workarea(outputs, Geometry(0, 40, 2560, 1400))
    assert got[0].geometry == Geometry(0, 0, 2560, 1440)


def test_apply_workarea_skips_disconnected_outputs() -> None:
    outputs = [
        _out("DP-2", Geometry(0, 0, 0, 0), connected=False),
        _out("DP-1", Geometry(0, 0, 2560, 1440), primary=True),
    ]
    got = apply_workarea(outputs, Geometry(0, 40, 2560, 1400))
    assert got[0].work_area == Geometry(0, 0, 0, 0)
    assert got[0].is_connected is False
    assert got[1].work_area.h == 1400


# ── PERC-0047: a workarea that misses an output entirely ───────────────────
# _NET_WORKAREA is a single root-level rect. Plenty of WMs report only the
# primary monitor's area, so a second output can sit wholly outside it. The
# intersection is then empty, and a zero-size work_area makes every snap on
# that output produce a zero-size window. The output's own geometry is the
# honest fallback: no struts are known there, so none are subtracted.


def test_apply_workarea_falls_back_to_geometry_when_disjoint() -> None:
    left = OutputInfo(
        name="DP-1",
        geometry=Geometry(0, 0, 1920, 1080),
        work_area=Geometry(0, 0, 1920, 1080),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=True,
        is_connected=True,
    )
    right = OutputInfo(
        name="DP-2",
        geometry=Geometry(1920, 0, 1920, 1080),
        work_area=Geometry(1920, 0, 1920, 1080),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=False,
        is_connected=True,
    )
    # The WM reports a workarea covering the primary output alone.
    got = apply_workarea([left, right], Geometry(0, 28, 1920, 1052))

    by_name = {o.name: o for o in got}
    assert by_name["DP-1"].work_area == Geometry(0, 28, 1920, 1052)
    # DP-2 does not overlap the reported workarea at all.
    assert by_name["DP-2"].work_area == right.geometry
    assert by_name["DP-2"].work_area.w > 0
    assert by_name["DP-2"].work_area.h > 0
