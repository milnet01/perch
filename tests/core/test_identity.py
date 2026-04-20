"""Tests for :mod:`perch.core.identity`."""

from __future__ import annotations

from perch.backend.types import Geometry, WindowInfo, WindowState, WindowType
from perch.core.identity import compute_identity


def _w(app_id: str = "", wm_class: str = "") -> WindowInfo:
    return WindowInfo(
        id="w",
        app_id=app_id,
        wm_class=wm_class,
        title="",
        pid=None,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 0, 0),
        monitor="DP-1",
        desktop=0,
    )


def test_identity_prefers_app_id() -> None:
    assert compute_identity(_w(app_id="firefox", wm_class="Firefox")) == "app:firefox"


def test_identity_falls_back_to_wm_class() -> None:
    assert compute_identity(_w(wm_class="Signal")) == "app:Signal"


def test_identity_unknown_when_both_empty() -> None:
    assert compute_identity(_w()) == "app:unknown"
