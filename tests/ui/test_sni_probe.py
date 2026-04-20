"""SNI-host probe tests.

``sni_host_available`` accepts a probe callable for testability — the
production call path runs the real sdbus probe. These tests inject
fakes via that seam, covering the success path and every failure-classification
branch in the outer wrapper.
"""

from __future__ import annotations

import pytest

from perch.ui import sni_probe


def test_returns_true_when_probe_reports_host_registered() -> None:
    assert sni_probe.sni_host_available(lambda: True) is True


def test_returns_false_when_probe_reports_no_host() -> None:
    assert sni_probe.sni_host_available(lambda: False) is False


def test_returns_false_on_transport_exception() -> None:
    def boom() -> bool:
        raise RuntimeError("bus unreachable")

    assert sni_probe.sni_host_available(boom) is False


def test_returns_false_on_unknown_property_exception() -> None:
    # Some sdbus errors subclass Exception directly (DbusUnknownPropertyError
    # etc.). The wrapper must catch the broad Exception bucket, not just
    # specific sdbus subclasses.
    class _DbusError(Exception):
        pass

    def boom() -> bool:
        raise _DbusError("UnknownProperty")

    assert sni_probe.sni_host_available(boom) is False


def test_is_gnome_wayland_true_for_gnome_wayland(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert sni_probe.is_gnome_wayland() is True


def test_is_gnome_wayland_accepts_colon_separated_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ubuntu sets XDG_CURRENT_DESKTOP=ubuntu:GNOME
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert sni_probe.is_gnome_wayland() is True


def test_is_gnome_wayland_false_for_plasma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert sni_probe.is_gnome_wayland() is False


def test_is_gnome_wayland_false_for_gnome_x11(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert sni_probe.is_gnome_wayland() is False


def test_is_gnome_wayland_false_with_unset_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert sni_probe.is_gnome_wayland() is False
