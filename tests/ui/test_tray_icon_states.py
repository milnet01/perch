"""Tests for the tray-state icon / tooltip resolution (M7.a).

Covers the ``TrayIconState`` derivation, tooltip strings pinned by
:file:`docs/08-ui.md` §Icon states, and the :class:`TrayIcon` icon swap
that happens on every ``state_changed`` emission.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon

from perch.ui.icons import TrayIcons, load_tray_icons
from perch.ui.tray import (
    TrayController,
    TrayIcon,
    TrayIconState,
    TrayState,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _state(**overrides: object) -> TrayState:
    base: dict[str, object] = {
        "active_profile": None,
        "active_layout": None,
        "available_layouts": (),
    }
    base.update(overrides)
    return TrayState(**base)  # type: ignore[arg-type]


# ── TrayState.icon_state ────────────────────────────────────────────────


def test_icon_state_defaults_to_normal() -> None:
    assert _state().icon_state is TrayIconState.NORMAL


def test_icon_state_backend_degraded_is_warning() -> None:
    assert _state(backend_degraded=True).icon_state is TrayIconState.WARNING


def test_icon_state_awaiting_extension_is_warning() -> None:
    assert _state(awaiting_extension=True).icon_state is TrayIconState.WARNING


def test_icon_state_compositor_missing_is_error() -> None:
    assert _state(compositor_missing=True).icon_state is TrayIconState.ERROR


def test_icon_state_error_wins_over_warning() -> None:
    combined = _state(compositor_missing=True, backend_degraded=True)
    assert combined.icon_state is TrayIconState.ERROR


# ── TrayState.tooltip ───────────────────────────────────────────────────


def test_tooltip_defaults_to_header() -> None:
    state = _state(active_profile="docked", active_layout="coding")
    assert state.tooltip == "Perch — docked / coding"


def test_tooltip_backend_degraded_matches_docs() -> None:
    assert _state(backend_degraded=True).tooltip == "Perch — backend disconnected"


def test_tooltip_awaiting_extension_matches_docs() -> None:
    assert _state(awaiting_extension=True).tooltip == (
        "Perch — install the GNOME Shell extension to enable window management"
    )


def test_tooltip_compositor_missing_matches_docs() -> None:
    assert (
        _state(compositor_missing=True).tooltip
        == "Perch — no compatible compositor detected"
    )


# ── load_tray_icons() ───────────────────────────────────────────────────


def test_load_tray_icons_returns_non_null_bundle(qtbot: QtBot) -> None:
    """The bundled SVGs exist in the dev checkout, so every icon loads.

    ``qtbot`` only exists to force a live ``QApplication`` — ``QIcon`` can
    be constructed without a running app but emits a harmless warning
    on some Qt builds.
    """
    del qtbot
    icons = load_tray_icons()
    assert not icons.normal.isNull()
    assert not icons.warning.isNull()
    assert not icons.error.isNull()


# ── TrayIcon icon swap on state change ──────────────────────────────────


def _distinct_icons() -> TrayIcons:
    """Build a bundle whose three icons are distinct enough to ``is``-compare."""
    return TrayIcons(normal=QIcon(), warning=QIcon(), error=QIcon())


def test_tray_icon_starts_in_normal_state(qtbot: QtBot) -> None:
    del qtbot
    icons = _distinct_icons()
    controller = TrayController(_state())
    tray = TrayIcon(controller, icons=icons)
    try:
        assert tray.toolTip() == controller.state.tooltip
    finally:
        tray.hide()


def test_tray_icon_swaps_to_warning_on_backend_degraded(qtbot: QtBot) -> None:
    del qtbot
    icons = _distinct_icons()
    controller = TrayController(_state())
    tray = TrayIcon(controller, icons=icons)
    try:
        controller.set_state(_state(backend_degraded=True))
        assert tray.toolTip() == "Perch — backend disconnected"
    finally:
        tray.hide()


def test_tray_icon_swaps_to_error_on_compositor_missing(qtbot: QtBot) -> None:
    del qtbot
    icons = _distinct_icons()
    controller = TrayController(_state())
    tray = TrayIcon(controller, icons=icons)
    try:
        controller.set_state(_state(compositor_missing=True))
        assert tray.toolTip() == "Perch — no compatible compositor detected"
    finally:
        tray.hide()


def test_tray_icon_handles_missing_icons_bundle(qtbot: QtBot) -> None:
    """Constructing without ``icons`` is a supported test shortcut."""
    del qtbot
    controller = TrayController(_state())
    tray = TrayIcon(controller, icons=None)
    try:
        controller.set_state(_state(backend_degraded=True))
        # No crash; Qt draws a default placeholder icon.
        assert tray.toolTip() == "Perch — backend disconnected"
    finally:
        tray.hide()
