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

    Captured via a monkey-patched logger rather than pytest's ``caplog``:
    under the full test suite ``caplog``'s root-handler attachment races
    with the ``perch.logging_setup`` reconfiguration that other tests
    exercise. Replacing the module logger directly is robust against that.
    """
    del qtbot
    import logging as _logging
    from unittest.mock import patch

    backend = MockBackend()
    controller = TrayController(_empty_state())

    captured: list[_logging.LogRecord] = []

    class _Capture(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture(level=_logging.WARNING)
    target_logger = _logging.getLogger("perch.ui.status")
    target_logger.addHandler(handler)
    target_logger.setLevel(_logging.WARNING)
    try:
        with patch("perch.ui.status.log", target_logger):
            wire_backend_status(backend, controller, tray=None)
            backend.backend_error.emit("ipc timeout")
    finally:
        target_logger.removeHandler(handler)

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
    from PySide6.QtGui import QIcon

    from perch.ui.icons import TrayIcons

    backend = MockBackend()
    controller = TrayController(_empty_state())
    icons = TrayIcons(normal=QIcon(), warning=QIcon(), error=QIcon())
    tray = TrayIcon(controller, icons=icons)
    wire_backend_status(backend, controller, tray)
    try:
        backend.backend_disconnected.emit("dropped")
        assert tray.toolTip() == "Perch — backend disconnected"
        backend.backend_connected.emit()
        assert tray.toolTip() == controller.state.header
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
