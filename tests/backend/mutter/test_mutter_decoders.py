"""Unit tests for the pure decoders + error translator in
:mod:`perch.backend.mutter.backend`."""

from __future__ import annotations

import pytest

from perch.backend import (
    BackendError,
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
)
from perch.backend.mutter.backend import (
    MutterBackend,
    _decode_output,
    _decode_window,
    _raise_for_error,
)
from perch.backend.types import WindowState, WindowType


def test_decode_window_builds_full_shape() -> None:
    entry = {
        "id": "1234",
        "app_id": "Firefox",
        "wm_class": "Firefox",
        "title": "Mozilla Firefox",
        "pid": 4321,
        "type": "normal",
        "state": "normal",
        "x": 100,
        "y": 200,
        "w": 800,
        "h": 600,
        "monitor": "DP-1",
        "desktop": 2,
    }
    info = _decode_window(entry)
    assert info is not None
    assert info.id == "1234"
    assert info.app_id == "firefox"  # lowercased
    assert info.type is WindowType.NORMAL
    assert info.state is WindowState.NORMAL
    assert info.geometry.x == 100
    assert info.desktop == 2


def test_decode_window_coerces_unknown_type_to_normal() -> None:
    entry = {
        "id": "1", "x": 0, "y": 0, "w": 100, "h": 100,
        "type": "gnome-panel-thing",
    }
    info = _decode_window(entry)
    assert info is not None
    assert info.type is WindowType.NORMAL


def test_decode_window_coerces_unknown_state_to_normal() -> None:
    entry = {
        "id": "1", "x": 0, "y": 0, "w": 100, "h": 100,
        "state": "floating",
    }
    info = _decode_window(entry)
    assert info is not None
    assert info.state is WindowState.NORMAL


def test_decode_window_zero_pid_becomes_none() -> None:
    entry = {"id": "1", "x": 0, "y": 0, "w": 100, "h": 100, "pid": 0}
    info = _decode_window(entry)
    assert info is not None
    assert info.pid is None


def test_decode_window_rejects_non_dict() -> None:
    assert _decode_window("not a dict") is None


def test_decode_window_rejects_missing_geometry() -> None:
    # Missing ``x``/``y``/``w``/``h`` → None rather than synthesising 0s.
    assert _decode_window({"id": "1"}) is None


def test_decode_output_subtracts_work_area_from_payload() -> None:
    entry = {
        "name": "DP-1",
        "x": 0, "y": 0, "w": 2560, "h": 1440,
        "work_area": {"x": 0, "y": 32, "w": 2560, "h": 1408},
        "scale": 2.0,
        "refresh_mhz": 144000,
        "is_primary": True,
    }
    out = _decode_output(entry)
    assert out is not None
    assert out.geometry.h == 1440
    assert out.work_area.y == 32
    assert out.work_area.h == 1408
    assert out.scale == 2.0


def test_decode_output_falls_back_when_work_area_missing() -> None:
    entry = {"name": "DP-1", "x": 0, "y": 0, "w": 1920, "h": 1080}
    out = _decode_output(entry)
    assert out is not None
    assert out.work_area == out.geometry


def test_raise_for_error_passes_through_success() -> None:
    _raise_for_error({"ok": True})
    _raise_for_error("plain string reply")  # non-dict → no-op
    _raise_for_error(None)


def test_raise_for_error_unknown_window() -> None:
    with pytest.raises(UnknownWindow):
        _raise_for_error(
            {"ok": False, "error": "unknown_window", "message": "no such window"},
            wid="99",
        )


def test_raise_for_error_unknown_output() -> None:
    with pytest.raises(UnknownOutput):
        _raise_for_error(
            {"ok": False, "error": "unknown_output", "message": "no such output"},
            monitor="NONE-0",
        )


def test_raise_for_error_unsupported() -> None:
    with pytest.raises(BackendUnsupported):
        _raise_for_error({"ok": False, "error": "unsupported", "message": "no schema"})


def test_raise_for_error_unmapped_kind_raises_backend_error() -> None:
    with pytest.raises(BackendError):
        _raise_for_error({"ok": False, "error": "something_else", "message": "???"})


def test_is_available_requires_gnome_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert MutterBackend.is_available() is False

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert MutterBackend.is_available() is True


def test_is_available_rejects_x11_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert MutterBackend.is_available() is False


def test_capabilities_match_docs_06() -> None:
    caps = MutterBackend().capabilities
    assert caps.can_set_position is True
    assert caps.can_register_hotkeys is True
    assert caps.can_preplace_windows is False
