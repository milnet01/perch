"""Unit tests for the pure decoders in :mod:`perch.backend.sway.backend`.

These don't touch the i3-IPC socket — the functions under test consume an
``i3ipc.Con``-shaped stub and build the core :mod:`perch.backend.types`
dataclasses. End-to-end proof against a live Sway is the stub's STATUS.md
future work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from perch.backend.sway.backend import (
    SwayBackend,
    _decode_window,
    _is_managed,
)
from perch.backend.types import WindowState, WindowType


@dataclass
class _Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


class _Con:
    """Duck-typed stand-in for an ``i3ipc.Con``."""

    def __init__(
        self,
        *,
        id: int = 42,
        type: str = "con",
        pid: int | None = 1234,
        name: str = "Firefox",
        app_id: str | None = None,
        window_class: str = "",
        rect: _Rect | None = None,
        fullscreen_mode: int = 0,
        scratchpad_state: str = "none",
        parent: _Con | None = None,
        num: int = -1,
        output_name: str = "",
    ) -> None:
        self.id = id
        self.type = type
        self.pid = pid
        self.name = name
        self.app_id = app_id
        self.window_class = window_class
        self.rect = rect or _Rect(10, 20, 800, 600)
        self.fullscreen_mode = fullscreen_mode
        self.scratchpad_state = scratchpad_state
        self.parent = parent
        self.num = num
        self._output_name = output_name

    def __getattr__(self, name: str) -> Any:
        # Sway's ``_Con`` exposes these lazily. The decoder uses getattr
        # with defaults, so an AttributeError would be incorrect.
        if name == "name" and self.type == "output":
            return self._output_name
        raise AttributeError(name)


def _workspace(num: int, parent: _Con | None = None) -> _Con:
    return _Con(type="workspace", num=num, parent=parent, name=f"{num}")


def _output(name: str, parent: _Con | None = None) -> _Con:
    out = _Con(type="output", parent=parent, output_name=name)
    out.name = name  # direct attribute so getattr works
    return out


# ── Duck-typed stub helpers ───────────────────────────────────────────────
# mypy sees ``_Con`` as ``object``; the decoders accept any i3ipc.Con-shape
# via duck-typing. Cast once at the call site to keep the --strict checker
# happy without littering every assertion with type: ignore.


def _as_con(stub: _Con) -> Any:
    return cast(Any, stub)


def test_is_managed_accepts_toplevel_cons_with_pids() -> None:
    assert _is_managed(_as_con(_Con(type="con", pid=1234)))
    assert _is_managed(_as_con(_Con(type="floating_con", pid=999)))


def test_is_managed_rejects_pidless_cons() -> None:
    assert not _is_managed(_as_con(_Con(type="con", pid=None)))


def test_is_managed_rejects_workspace_and_output_nodes() -> None:
    assert not _is_managed(_as_con(_Con(type="workspace")))
    assert not _is_managed(_as_con(_Con(type="output")))


def test_decode_window_normal_toplevel() -> None:
    out = _output("DP-1")
    ws = _workspace(2, parent=out)
    con = _Con(
        id=100,
        rect=_Rect(x=50, y=60, width=1024, height=768),
        name="Mozilla Firefox",
        app_id="firefox",
        parent=ws,
    )
    info = _decode_window(_as_con(con))
    assert info.id == "100"
    assert info.app_id == "firefox"
    assert info.title == "Mozilla Firefox"
    assert info.type is WindowType.NORMAL
    assert info.state is WindowState.NORMAL
    assert info.geometry.x == 50
    assert info.geometry.w == 1024
    assert info.monitor == "DP-1"
    assert info.desktop == 1  # Sway num 2 → desktop index 1


def test_decode_window_falls_back_to_window_class_for_xwayland() -> None:
    con = _Con(app_id=None, window_class="Firefox")  # X11 client on Sway
    info = _decode_window(_as_con(con))
    assert info.app_id == "firefox"
    assert info.wm_class == "Firefox"


def test_decode_window_fullscreen_mode_maps_to_state() -> None:
    con = _Con(fullscreen_mode=1)
    info = _decode_window(_as_con(con))
    assert info.state is WindowState.FULLSCREEN


def test_decode_window_scratchpad_maps_to_minimised() -> None:
    con = _Con(scratchpad_state="fresh")
    info = _decode_window(_as_con(con))
    assert info.state is WindowState.MINIMIZED


def test_decode_window_named_only_workspace_reports_desktop_zero() -> None:
    # Named-only workspaces have ``num == -1``; we report desktop 0.
    out = _output("HDMI-1")
    ws = _workspace(-1, parent=out)
    con = _Con(parent=ws)
    info = _decode_window(_as_con(con))
    assert info.desktop == 0
    assert info.monitor == "HDMI-1"


def test_is_available_tracks_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SWAYSOCK", raising=False)
    assert SwayBackend.is_available() is False
    monkeypatch.setenv("SWAYSOCK", "/run/user/1000/sway-ipc.sock")
    assert SwayBackend.is_available() is True


def test_is_available_ignores_empty_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWAYSOCK", "")
    assert SwayBackend.is_available() is False


def test_capabilities_match_docs_06() -> None:
    caps = SwayBackend().capabilities
    assert caps.can_set_position is False  # tiling-first, floating-only
    assert caps.can_register_hotkeys is False  # Sway owns hotkeys
    assert caps.can_preplace_windows is False
    assert caps.can_set_size is True
    assert caps.can_set_desktop is True
