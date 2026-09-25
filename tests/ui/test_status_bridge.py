"""Tests for the backend-status → tray bridge (M7.c).

Verifies that ``wire_backend_status`` translates the three backend
status signals into tray-state mutations and balloon notifications, per
:file:`docs/08-ui.md` §Notifications and §Icon states.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from perch.backend.mock import MockBackend
from perch.ui.status import (
    make_skipped_entries_notifier,
    wire_backend_status,
)
from perch.ui.tray import TrayController, TrayIcon, TrayState

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _empty_state() -> TrayState:
    return TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=(),
    )


class _RecordingTray:
    """Stand-in for :class:`TrayIcon` capturing ``showMessage`` calls."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def showMessage(
        self, title: str, message: str, *_args: object, **_kwargs: object
    ) -> None:
        self.messages.append((title, message))


def test_backend_connected_clears_degraded_flag(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    initial = TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=(),
        backend_degraded=True,
    )
    controller = TrayController(initial)
    wire_backend_status(backend, controller, tray=None)

    backend.backend_connected.emit()

    assert controller.state.backend_degraded is False


def test_backend_connected_is_noop_when_not_degraded(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    controller = TrayController(_empty_state())
    wire_backend_status(backend, controller, tray=None)

    emissions = 0

    def _count() -> None:
        nonlocal emissions
        emissions += 1

    controller.state_changed.connect(_count)
    backend.backend_connected.emit()
    assert emissions == 0


def test_backend_disconnected_sets_degraded_flag(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    controller = TrayController(_empty_state())
    wire_backend_status(backend, controller, tray=None)

    backend.backend_disconnected.emit("transport closed")

    assert controller.state.backend_degraded is True


def test_backend_disconnected_is_noop_when_already_degraded(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    initial = TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=(),
        backend_degraded=True,
    )
    controller = TrayController(initial)
    wire_backend_status(backend, controller, tray=None)

    emissions = 0

    def _count() -> None:
        nonlocal emissions
        emissions += 1

    controller.state_changed.connect(_count)
    backend.backend_disconnected.emit("still down")
    assert emissions == 0


def test_backend_error_shows_tray_notification(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    controller = TrayController(_empty_state())
    recorder = _RecordingTray()
    # Cast only for type-check-ability; _RecordingTray duck-types the
    # showMessage method we care about.
    wire_backend_status(
        backend, controller, tray=recorder  # type: ignore[arg-type]
    )

    backend.backend_error.emit("hotkey unavailable: Meta+Q")

    assert recorder.messages == [("Perch", "hotkey unavailable: Meta+Q")]


def test_backend_error_without_tray_still_logs(qtbot: QtBot) -> None:
    """A backend_error without a tray still hits the module logger.

    Captured by a handler on the module's own logger rather than pytest's
    ``caplog``, which listens on the root logger and so hears nothing once
    ``configure_logging`` has stopped ``perch`` propagating.
    """
    del qtbot
    import logging as _logging

    backend = MockBackend()
    controller = TrayController(_empty_state())

    captured: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture(level=_logging.WARNING)
    target_logger = _logging.getLogger("perch.ui.status")
    target_logger.addHandler(handler)
    level = target_logger.level
    target_logger.setLevel(_logging.WARNING)
    try:
        wire_backend_status(backend, controller, tray=None)
        backend.backend_error.emit("ipc timeout")
    finally:
        target_logger.removeHandler(handler)
        target_logger.setLevel(level)

    assert any("ipc timeout" in rec.getMessage() for rec in captured)


def test_status_bridge_round_trip_restores_normal_tooltip(qtbot: QtBot) -> None:
    del qtbot
    backend = MockBackend()
    controller = TrayController(_empty_state())
    wire_backend_status(backend, controller, tray=None)

    backend.backend_disconnected.emit("stopped")
    assert controller.state.tooltip == "Perch — backend disconnected"

    backend.backend_connected.emit()
    assert controller.state.tooltip == controller.state.header


def test_tray_icon_swaps_to_warning_when_backend_disconnects(qtbot: QtBot) -> None:
    """End-to-end: real TrayIcon wired to a MockBackend flips to warning."""
    del qtbot
    from PySide6.QtGui import QColor, QIcon, QPixmap

    from perch.ui.icons import TrayIcons

    def _solid(colour: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(colour))
        return QIcon(pixmap)

    backend = MockBackend()
    controller = TrayController(_empty_state())
    # Distinct icons: null ones all look alike, hiding a wrong swap.
    icons = TrayIcons(normal=_solid("green"), warning=_solid("orange"), error=_solid("red"))
    tray = TrayIcon(controller, icons=icons)
    wire_backend_status(backend, controller, tray)
    try:
        backend.backend_disconnected.emit("dropped")
        assert tray.toolTip() == "Perch — backend disconnected"
        assert tray.icon().cacheKey() == icons.warning.cacheKey()
        backend.backend_connected.emit()
        assert tray.toolTip() == controller.state.header
        assert tray.icon().cacheKey() == icons.normal.cacheKey()
    finally:
        tray.hide()


# ── Skipped layout entries (docs/09 §Apply semantics step 4) ──────────────
def test_skipped_entries_notifier_lists_them_in_one_message() -> None:
    tray = _RecordingTray()
    notify = make_skipped_entries_notifier(tray)  # type: ignore[arg-type]

    notify(["app:code: output 'DP-9' is not currently connected"])

    assert len(tray.messages) == 1
    _title, body = tray.messages[0]
    assert "DP-9" in body


def test_skipped_entries_notifier_without_a_tray_does_not_raise() -> None:
    make_skipped_entries_notifier(None)(["app:code: nowhere"])


def test_backend_outliving_the_controller_does_not_raise(
    qtbot: QtBot,
) -> None:
    """PERC-0058: plain closures cannot be auto-disconnected by Qt, so a
    backend signal after the controller died hit a deleted C++ object."""
    import shiboken6

    del qtbot
    backend = MockBackend()
    controller = TrayController(_empty_state())
    wire_backend_status(backend, controller)
    shiboken6.delete(controller)
    errors: list[BaseException] = []
    import sys

    old_hook = sys.excepthook
    sys.excepthook = lambda _t, exc, _tb: errors.append(exc)
    try:
        backend.backend_disconnected.emit("gone")
        backend.backend_connected.emit()
        backend.backend_error.emit("boom")
    finally:
        sys.excepthook = old_hook
    assert errors == []
