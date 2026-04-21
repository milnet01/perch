"""Unit tests for the pure decoders in :mod:`perch.backend.hyprland.backend`."""

from __future__ import annotations

import pytest

from perch.backend.hyprland.backend import (
    HyprlandBackend,
    _decode_client,
    _decode_monitor,
    _parse_version,
)
from perch.backend.types import WindowState


def test_parse_version_handles_clean_tag() -> None:
    assert _parse_version("v0.40.0") == (0, 40, 0)
    assert _parse_version("0.41.2") == (0, 41, 2)


def test_parse_version_handles_dirty_tag() -> None:
    assert _parse_version("v0.41.2-4-g1234abc") == (0, 41, 2)


def test_parse_version_returns_none_for_garbage() -> None:
    assert _parse_version("unknown") is None
    assert _parse_version("") is None


def test_decode_client_normal_toplevel() -> None:
    entry = {
        "address": "0x55a001",
        "at": [120, 80],
        "size": [1024, 768],
        "class": "firefox",
        "initialClass": "Firefox",
        "title": "Mozilla Firefox",
        "pid": 12345,
        "monitor": "DP-1",
        "workspace": {"id": 3, "name": "3"},
        "fullscreen": False,
    }
    info = _decode_client(entry)
    assert info.id == "0x55a001"
    assert info.app_id == "firefox"
    assert info.wm_class == "firefox"
    assert info.title == "Mozilla Firefox"
    assert info.pid == 12345
    assert info.geometry.x == 120
    assert info.geometry.w == 1024
    assert info.state is WindowState.NORMAL
    assert info.desktop == 2
    assert info.monitor == "DP-1"


def test_decode_client_special_workspace_maps_to_minimised() -> None:
    entry = {
        "address": "0x55a002",
        "at": [0, 0],
        "size": [100, 100],
        "class": "app",
        "workspace": {"id": -99, "name": "special"},
    }
    info = _decode_client(entry)
    assert info.state is WindowState.MINIMIZED


def test_decode_client_fullscreen_takes_priority_over_workspace_state() -> None:
    entry = {
        "address": "0x55a003",
        "at": [0, 0],
        "size": [100, 100],
        "class": "app",
        "workspace": {"id": 1, "name": "1"},
        "fullscreen": True,
    }
    info = _decode_client(entry)
    assert info.state is WindowState.FULLSCREEN


def test_decode_client_pid_zero_becomes_none() -> None:
    entry = {
        "address": "0x55a004",
        "at": [0, 0],
        "size": [0, 0],
        "class": "app",
        "pid": 0,
        "workspace": {"id": 1, "name": "1"},
    }
    info = _decode_client(entry)
    assert info.pid is None


def test_decode_monitor_subtracts_reserved_margins_for_work_area() -> None:
    entry = {
        "name": "DP-1",
        "x": 0,
        "y": 0,
        "width": 2560,
        "height": 1440,
        "reserved": [10, 20, 30, 40],  # left, top, right, bottom
        "scale": 1.5,
        "refreshRate": 144.0,
        "focused": True,
    }
    out = _decode_monitor(entry)
    assert out.geometry.w == 2560
    assert out.work_area.x == 10
    assert out.work_area.y == 20
    assert out.work_area.w == 2560 - 10 - 30
    assert out.work_area.h == 1440 - 20 - 40
    assert out.scale == 1.5
    assert out.refresh_mhz == 144000
    assert out.is_primary is True


def test_decode_monitor_handles_missing_reserved() -> None:
    entry = {
        "name": "HDMI-1",
        "x": 2560,
        "y": 0,
        "width": 1920,
        "height": 1080,
    }
    out = _decode_monitor(entry)
    assert out.work_area == out.geometry


def test_is_available_requires_both_signature_and_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert HyprlandBackend.is_available() is False

    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc123")
    # hyprctl-on-PATH is flaky across CI runners — patch ``shutil.which``
    # globally; the backend imports it via ``import shutil`` so the patch
    # reaches the module-level lookup.
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/hyprctl")
    assert HyprlandBackend.is_available() is True

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert HyprlandBackend.is_available() is False


def test_capabilities_match_docs_06() -> None:
    caps = HyprlandBackend().capabilities
    assert caps.can_register_hotkeys is False  # Hyprland owns hotkeys
    assert caps.can_preplace_windows is False
    assert caps.can_set_position is True
    assert caps.can_set_desktop is True
