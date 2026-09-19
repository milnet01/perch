"""Bridge between backend status signals and the tray surface (M7.c).

Connects the three :class:`~perch.backend.base.WindowBackend` status
signals — ``backend_connected``, ``backend_disconnected``,
``backend_error`` — to the :class:`~perch.ui.tray.TrayController` that
drives the tray icon and to the :class:`~perch.ui.tray.TrayIcon` itself
for balloon notifications.

Kept as a plain function so the composition root in :mod:`perch.app`
stays tidy and the bridge is testable against a :class:`MockBackend`
without a real :class:`QSystemTrayIcon` host.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QObject, Slot
from PySide6.QtWidgets import QSystemTrayIcon

if TYPE_CHECKING:
    from perch.backend.base import WindowBackend

    from .tray import TrayController, TrayIcon

log = logging.getLogger(__name__)


_NOTIFICATION_TIMEOUT_MS = 5000


class _StatusBridge(QObject):
    """Receiver for the three backend status signals.

    A QObject child of the controller, so the slots are bound methods of
    a Qt receiver: Qt drops the connections when the controller (and
    with it this bridge) is destroyed, and a backend that outlives the
    tray stops calling into a deleted object. Plain closures carry no
    receiver, so Qt could never disconnect them.
    """

    def __init__(
        self, controller: TrayController, tray: TrayIcon | None
    ) -> None:
        super().__init__(controller)
        self._controller = controller
        self._tray = tray

    @Slot()
    def on_connected(self) -> None:
        current = self._controller.state
        if not current.backend_degraded:
            return
        self._controller.set_state(replace(current, backend_degraded=False))

    @Slot(str)
    def on_disconnected(self, reason: str) -> None:
        log.warning("backend disconnected: %s", reason)
        current = self._controller.state
        if current.backend_degraded:
            return
        self._controller.set_state(replace(current, backend_degraded=True))

    @Slot(str)
    def on_error(self, message: str) -> None:
        log.warning("backend error: %s", message)
        if self._tray is None:
            return
        self._tray.showMessage(
            QCoreApplication.translate("perch.ui.status", "Perch"),
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            _NOTIFICATION_TIMEOUT_MS,
        )


def wire_backend_status(
    backend: WindowBackend,
    controller: TrayController,
    tray: TrayIcon | None = None,
) -> None:
    """Connect backend status signals to the tray surface.

    * ``backend_connected`` → clears ``TrayState.backend_degraded``.
    * ``backend_disconnected`` → sets ``TrayState.backend_degraded`` and
      logs the reason. The degraded state is what the tray shows; there
      is no balloon, because a clean shutdown emits the same signal.
    * ``backend_error`` → surfaces a transient balloon notification when
      a :class:`TrayIcon` is provided. When ``tray`` is ``None`` (tests)
      the message is still logged at WARNING level so the event is
      observable.

    The receiver is parented to ``controller``, so the connections end
    when the controller is destroyed.
    """
    bridge = _StatusBridge(controller, tray)
    backend.backend_connected.connect(bridge.on_connected)
    backend.backend_disconnected.connect(bridge.on_disconnected)
    backend.backend_error.connect(bridge.on_error)


def make_skipped_entries_notifier(
    tray: TrayIcon | None = None,
) -> Callable[[list[str]], None]:
    """Return the reducer's ``notify_skipped`` callback.

    ``docs/09-layouts-profiles.md`` §Apply semantics step 4 requires that
    layout entries skipped for an absent output be listed to the user. The
    reducer collects them and stays free of Qt; the wording and its
    translation live here. With no :class:`TrayIcon` (tests) the list is
    still logged at WARNING so the event is observable.
    """

    def notify(entries: list[str]) -> None:
        body = "\n".join(entries)
        log.warning("layout entries skipped:\n%s", body)
        if tray is None:
            return
        heading = QCoreApplication.translate(
            "perch.ui.status", "Some layout entries were skipped"
        )
        tray.showMessage(
            QCoreApplication.translate("perch.ui.status", "Perch"),
            f"{heading}\n{body}",
            QSystemTrayIcon.MessageIcon.Information,
            _NOTIFICATION_TIMEOUT_MS,
        )

    return notify
