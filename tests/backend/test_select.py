"""Unit tests for :func:`perch.backend.select`.

The function is env-only: it reads ``PERCH_BACKEND`` / ``XDG_*`` /
``SWAYSOCK`` / ``HYPRLAND_INSTANCE_SIGNATURE`` / ``DISPLAY`` and returns a
backend class. No I/O.
"""

from __future__ import annotations

import pytest

from perch.backend import BackendUnavailable, select
from perch.backend.hyprland import HyprlandBackend
from perch.backend.kwin import KWinBackend
from perch.backend.mock import MockBackend
from perch.backend.mutter import MutterBackend
from perch.backend.sway import SwayBackend
from perch.backend.x11 import X11Backend


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env var :func:`select` inspects so tests compose cleanly."""
    for name in (
        "PERCH_BACKEND",
        "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP",
        "SWAYSOCK",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "XDG_RUNTIME_DIR",
        "DISPLAY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_override_argument_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert select(override="mock") is MockBackend


def test_perch_backend_env_var_overrides_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("PERCH_BACKEND", "mock")
    assert select() is MockBackend


def test_select_raises_backend_unavailable_on_unknown_name() -> None:
    with pytest.raises(BackendUnavailable):
        select(override="no-such-backend")


def test_select_prefers_kwin_on_plasma_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert select() is KWinBackend


def test_select_prefers_mutter_on_gnome_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert select() is MutterBackend


def test_select_prefers_sway_when_swaysock_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWAYSOCK", "/run/user/1000/sway-ipc.sock")
    assert select() is SwayBackend


def test_select_prefers_hyprland_when_signature_and_binary_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "abc123")
    # HyprlandBackend.is_available() also checks for hyprctl on PATH. Patch
    # shutil.which globally so the test doesn't depend on the host having hyprctl.
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/hyprctl")
    assert select() is HyprlandBackend


def test_select_falls_through_to_x11_when_only_display_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    assert select() is X11Backend


def test_select_raises_backend_unavailable_when_nothing_detectable() -> None:
    # No env set (fixture scrubs everything). Every probe returns False.
    with pytest.raises(BackendUnavailable):
        select()
