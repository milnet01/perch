"""Tray icon + dynamic menu.

Menu structure follows ``docs/08-ui.md`` §Menu structure. The module is
split into three responsibilities so the Qt-heavy pieces stay testable:

* :class:`TrayState` — the snapshot of reducer state the menu reads from.
  A frozen dataclass keeps tests declarative.
* :func:`build_tray_menu` — pure function: state → ``QMenu`` + actions
  wired to a ``TrayController``. Tested without a running tray host.
* :class:`TrayController` — emits :class:`~perch.ui.intents.Intent` values
  as a Qt signal. The core subscribes and translates intents into reducer
  work. Action triggers call controller methods which emit the signal;
  tests invoke those methods directly instead of simulating clicks.
* :class:`TrayIcon` — thin ``QSystemTrayIcon`` shell that listens to
  :meth:`TrayController.state_changed` and calls ``setContextMenu`` with a
  freshly-built menu. ``QMenu.aboutToShow`` is not used (QTBUG-55911 leaves
  it unemitted for tray-attached menus on Linux).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QT_TR_NOOP, QCoreApplication, QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from perch.core.snaps import SnapPreset

from .intents import (
    ActivateLayout,
    Intent,
    OpenConfigDialog,
    OpenConfigFolder,
    Quit,
    ReapplyRules,
    ShowAbout,
    SnapFocused,
    TogglePauseRestore,
)

# ``pyside6-lupdate`` only extracts strings from literal
# ``QCoreApplication.translate("…", "…")`` or ``self.tr(…)`` calls and
# from ``QT_TR_NOOP("…")`` markers — a Python-level wrapper breaks
# extraction. The inline form in :func:`build_tray_menu` is verbose but
# is the idiomatic Qt-Linguist-compatible pattern.

if TYPE_CHECKING:
    from perch.backend.types import WindowInfo

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrayState:
    """Read-only snapshot of the state the tray menu needs."""

    active_profile: str | None
    active_layout: str | None
    available_layouts: tuple[str, ...]
    user_snaps: tuple[SnapPreset, ...] = ()
    windows: tuple[WindowInfo, ...] = ()
    pause_restore: bool = False
    backend_degraded: bool = False

    @property
    def header(self) -> str:
        prof = self.active_profile or QCoreApplication.translate(
            "perch.ui.tray", "idle"
        )
        layout = self.active_layout or QCoreApplication.translate(
            "perch.ui.tray", "no layout"
        )
        return f"Perch — {prof} / {layout}"


# Built-in snap presets — ``(preset_id, source_language_label)``. Labels
# are marked with ``QT_TR_NOOP`` so lupdate extracts them; the actual
# translate call happens at menu-build time against the same context.
# ``cast`` to ``str`` because PySide6's ``QT_TR_NOOP`` typing stub
# returns ``object`` even though the runtime value is the input string.
BUILTIN_SNAP_MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("maximize", cast(str, QT_TR_NOOP("Maximize on this monitor"))),
    ("left-half", cast(str, QT_TR_NOOP("Left half"))),
    ("right-half", cast(str, QT_TR_NOOP("Right half"))),
    ("top-left", cast(str, QT_TR_NOOP("Top-left quarter"))),
    ("top-right", cast(str, QT_TR_NOOP("Top-right quarter"))),
    ("bottom-left", cast(str, QT_TR_NOOP("Bottom-left quarter"))),
    ("bottom-right", cast(str, QT_TR_NOOP("Bottom-right quarter"))),
    ("center-60", cast(str, QT_TR_NOOP("Centre (60%)"))),
)


class TrayController(QObject):
    """State owner + intent emitter for the tray.

    The tray icon, menu builder and first-run dialog all talk to this
    controller rather than to the core directly. The core subscribes to
    :attr:`intent` once and translates each emitted value into reducer
    or backend work.
    """

    intent = Signal(object)           # perch.ui.intents.Intent
    state_changed = Signal()

    def __init__(self, state: TrayState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state

    @property
    def state(self) -> TrayState:
        return self._state

    def set_state(self, state: TrayState) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit()

    # ── Slots the menu actions fire ────────────────────────────────────────
    def emit_intent(self, intent: Intent) -> None:
        """Public re-emit hook used both by action triggers and by tests."""
        log.debug("tray intent: %r", intent)
        self.intent.emit(intent)


def build_tray_menu(
    state: TrayState,
    controller: TrayController,
    parent: QWidget | None = None,
) -> QMenu:
    """Build a fresh ``QMenu`` reflecting ``state``.

    Pure in the sense that given the same (state, controller) the result
    has identical text, ordering and action wiring. Callers are expected
    to throw the previous menu away and ``setContextMenu(new_menu)``.

    ``parent`` must be a ``QWidget`` (or None) because ``QMenu`` inherits
    from ``QWidget`` — the ``QSystemTrayIcon`` that owns the menu is a
    ``QObject``, so callers from :class:`TrayIcon` pass ``None`` and keep
    the menu alive via a strong instance attribute.
    """
    menu = QMenu(parent)

    header = menu.addAction(state.header)
    header.setEnabled(False)
    menu.addSeparator()

    # Layouts submenu ------------------------------------------------------
    layouts_menu = menu.addMenu(
        QCoreApplication.translate("perch.ui.tray", "Layouts")
    )
    none_action = layouts_menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "(none)")
    )
    none_action.setCheckable(True)
    none_action.setChecked(state.active_layout is None)
    none_action.triggered.connect(
        lambda _checked=False: controller.emit_intent(ActivateLayout(None))
    )
    for name in state.available_layouts:
        act = layouts_menu.addAction(name)
        act.setCheckable(True)
        act.setChecked(state.active_layout == name)
        act.triggered.connect(
            lambda _checked=False, _n=name: controller.emit_intent(
                ActivateLayout(_n)
            )
        )

    # Snap focused submenu -------------------------------------------------
    snap_menu = menu.addMenu(
        QCoreApplication.translate("perch.ui.tray", "Snap focused window")
    )
    for preset_id, label in BUILTIN_SNAP_MENU_ITEMS:
        # ``label`` is a ``QT_TR_NOOP``-marked literal extracted above;
        # translate at display time against the same context lupdate
        # records for the NOOP marker.
        act = snap_menu.addAction(
            QCoreApplication.translate("perch.ui.tray", label)
        )
        act.triggered.connect(
            lambda _checked=False, _p=preset_id: controller.emit_intent(
                SnapFocused(_p)
            )
        )
    if state.user_snaps:
        snap_menu.addSeparator()
        for preset in state.user_snaps:
            act = snap_menu.addAction(preset.name)
            act.triggered.connect(
                lambda _checked=False, _p=preset.name: controller.emit_intent(
                    SnapFocused(_p)
                )
            )

    menu.addSeparator()

    # Pause restore + reapply --------------------------------------------
    pause_action = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "Pause restore")
    )
    pause_action.setCheckable(True)
    pause_action.setChecked(state.pause_restore)
    pause_action.triggered.connect(
        lambda _checked=False: controller.emit_intent(TogglePauseRestore())
    )

    reapply = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "Reapply rules now")
    )
    reapply.triggered.connect(
        lambda _checked=False: controller.emit_intent(ReapplyRules())
    )

    menu.addSeparator()

    # Config + folder ------------------------------------------------------
    configure = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "Configure Perch…")
    )
    configure.triggered.connect(
        lambda _checked=False: controller.emit_intent(OpenConfigDialog(None))
    )
    folder = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "Open config folder")
    )
    folder.triggered.connect(
        lambda _checked=False: controller.emit_intent(OpenConfigFolder())
    )

    menu.addSeparator()

    about = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "About Perch")
    )
    about.triggered.connect(
        lambda _checked=False: controller.emit_intent(ShowAbout())
    )
    quit_action = menu.addAction(
        QCoreApplication.translate("perch.ui.tray", "Quit Perch")
    )
    quit_action.triggered.connect(
        lambda _checked=False: controller.emit_intent(Quit())
    )

    return menu


class TrayIcon(QSystemTrayIcon):
    """Thin ``QSystemTrayIcon`` shell driven by a :class:`TrayController`.

    The icon subscribes to the controller's ``state_changed`` signal and
    rebuilds its context menu each time. Activation (left/middle/right-
    click) is routed through :meth:`_on_activated` so tests can call it
    directly without simulating a real tray host — see
    ``docs/08-ui.md`` §Menu structure.
    """

    def __init__(
        self,
        controller: TrayController,
        icon: QIcon | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if icon is not None:
            self.setIcon(icon)
        self._controller = controller
        self._menu_actions: list[QAction] = []  # keep refs alive for Qt
        self._rebuild_menu()
        controller.state_changed.connect(self._rebuild_menu)
        self.activated.connect(self._on_activated)
        self._update_tooltip()

    def _rebuild_menu(self) -> None:
        # parent=None because QSystemTrayIcon is a QObject, not a QWidget,
        # and QMenu requires a QWidget parent.
        menu = build_tray_menu(self._controller.state, self._controller, None)
        self.setContextMenu(menu)
        # Keep a strong ref; QSystemTrayIcon does not take ownership of
        # the menu on every platform.
        self._menu = menu
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        state = self._controller.state
        if state.backend_degraded:
            self.setToolTip("Perch — backend disconnected")
        else:
            self.setToolTip(state.header)

    def _on_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        """Handle tray-icon activation.

        * Left / right click → show the context menu. Qt does this for us
          when a ``contextMenu`` is set; the hook is here so subclasses or
          tests can override if needed.
        * Middle click → toggle pause restore (the "escape hatch" per
          docs/08-ui.md §Menu structure).
        """
        if reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self._controller.emit_intent(TogglePauseRestore())
