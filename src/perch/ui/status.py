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

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QSystemTrayIcon

if TYPE_CHECKING:
    from perch.backend.base import WindowBackend

    from .tray import TrayController, TrayIcon

log = logging.getLogger(__name__)


_NOTIFICATION_TIMEOUT_MS = 5000


def wire_backend_status(
    backend: WindowBackend,
    controller: TrayController,
    tray: TrayIcon | None = None,
) -> None:
    """Connect backend status signals to the tray surface.

    * ``backend_connected`` → clears ``TrayState.backend_degraded``.
    * ``backend_disconnected`` → sets ``TrayState.backend_degraded`` and
      logs the reason.
    * ``backend_error`` → surfaces a transient balloon notification when
      a :class:`TrayIcon` is provided. When ``tray`` is ``None`` (tests)
      the message is still logged at WARNING level so the event is
      observable.

    Safe to call once; each signal accepts an unbounded number of slots
    so re-wiring on a backend swap is the caller's responsibility (drop
    the old backend and stop receiving its events by letting it
    deallocate).
    """

    def on_connected() -> None:
        current = controller.state
        if not current.backend_degraded:
            return
        controller.set_state(replace(current, backend_degraded=False))

    def on_disconnected(reason: str) -> None:
        log.warning("backend disconnected: %s", reason)
        current = controller.state
        if current.backend_degraded:
            return
        controller.set_state(replace(current, backend_degraded=True))

    def on_error(message: str) -> None:
        log.warning("backend error: %s", message)
        if tray is None:
            return
        tray.showMessage(
            QCoreApplication.translate("perch.ui.status", "Perch"),
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            _NOTIFICATION_TIMEOUT_MS,
        )

    backend.backend_connected.connect(on_connected)
    backend.backend_disconnected.connect(on_disconnected)
    backend.backend_error.connect(on_error)


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
