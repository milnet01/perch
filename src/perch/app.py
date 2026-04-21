"""Top-level ``main()`` coroutine.

Implements the canonical event-loop bootstrap from
``docs/01-architecture.md`` §Event loop bootstrap — ``QApplication`` inside
the CLI wrapper (before ``QEventLoop`` is constructed by ``asyncio.run``),
``aboutToQuit → asyncio.Event`` handshake, ``await close_event`` as the
idle point.

M3 wires the UI end-to-end: SNI probe → tray icon + controller → MockBackend
→ reducer (real backends land in M4/M5). Intents emitted by the tray drive
reducer work via :meth:`_handle_intent`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from . import paths
from .backend.mock import MockBackend
from .config import Config, load_or_create
from .core.reducer import Reducer
from .core.state import AppState
from .core.state_store import StateStore
from .i18n import install_translators
from .ui.dialog import ConfigDialog
from .ui.icons import load_tray_icons
from .ui.intents import (
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
from .ui.sni_probe import is_gnome_wayland, sni_host_available
from .ui.status import wire_backend_status
from .ui.theming import apply_theme
from .ui.tray import TrayController, TrayIcon, TrayState

log = logging.getLogger(__name__)


def _maybe_show_appindicator_hint(parent: QCoreApplication | None) -> None:
    """First-run warning for GNOME Wayland users without the extension.

    Gated per ``docs/08-ui.md`` §Tray on GNOME Wayland — shown only when
    the SNI probe is negative AND the session is GNOME on Wayland. Other
    desktops with a negative probe just log a warning; they don't get a
    dialog because there's no standard install path to point them at.
    """
    del parent
    ctx = "perch.app"
    box = QMessageBox()
    box.setWindowTitle(
        QCoreApplication.translate(ctx, "Perch — tray icon unavailable")
    )
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(
        QCoreApplication.translate(
            ctx,
            "GNOME Wayland doesn't show tray icons by default. Please install "
            "the <b>AppIndicator and KStatusNotifierItem Support</b> GNOME "
            "extension to see Perch in your top bar.",
        )
    )
    box.setInformativeText(
        QCoreApplication.translate(
            ctx,
            "Perch will continue running in the background; the config dialog "
            "is still reachable from <code>perch --settings</code>.",
        )
    )
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def _initial_tray_state(
    config: Config, *, awaiting_extension: bool = False
) -> TrayState:
    return TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=tuple(config.layouts.keys()),
        user_snaps=tuple(config.snaps.values()),
        awaiting_extension=awaiting_extension,
    )


# Background tasks launched from _handle_intent. Python's GC can reclaim
# the Task object otherwise and the coroutine silently stops (this is the
# RUF006 asyncio footgun). A module-level set keeps them alive until the
# done-callback prunes them.
_intent_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Coroutine[Any, Any, None]) -> None:
    """Schedule ``coro`` and retain a strong reference until it finishes."""
    task: asyncio.Task[None] = asyncio.create_task(coro)
    _intent_tasks.add(task)
    task.add_done_callback(_intent_tasks.discard)


def _handle_intent(
    intent: Intent,
    *,
    close_event: asyncio.Event,
    reducer: Reducer,
    open_dialog: Callable[[str | None], None] | None = None,
) -> None:
    """Translate a UI intent into core work.

    Kept as a plain function (rather than a controller method) so tests
    can exercise the intent→core translation without a QApplication.
    """
    match intent:
        case Quit():
            close_event.set()
        case TogglePauseRestore():
            # Reducer-level pause flag lands with the real backend wiring
            # in M4; for M3 we log so the tray integration is verifiable.
            log.info("pause-restore toggled (stub — reducer flag in M4)")
        case ReapplyRules():
            _spawn(reducer.recompute_topology())
        case ActivateLayout(name):
            _spawn(reducer.activate_layout(name))
        case SnapFocused(preset):
            log.info("snap focused: %s (routed in M4)", preset)
        case OpenConfigDialog(section):
            if open_dialog is not None:
                open_dialog(section)
            else:
                log.info("open config dialog: section=%r (no dialog wired)", section)
        case OpenConfigFolder():
            _open_in_file_manager(paths.config_dir())
        case ShowAbout():
            log.info("about dialog (stub — lands in a follow-up milestone)")


def _open_in_file_manager(directory: Path) -> None:
    """Open ``directory`` in the user's file manager (``xdg-open``)."""
    paths.ensure_dir(directory)
    try:
        subprocess.Popen(
            ["xdg-open", str(directory)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        log.warning("xdg-open not found; cannot open %s", directory)


async def main() -> int:
    """Run Perch. Returns the process exit code.

    M3 scope: load config, show tray icon (when an SNI host is available
    or the session is GNOME-Wayland and we surface the hint), wire a
    :class:`MockBackend` through the reducer, and let the tray drive
    intents. Real backends (X11 in M4, KWin in M5) swap MockBackend out
    without touching this file.
    """
    config: Config = load_or_create()
    state = AppState(config=config)
    log.info(
        "perch started: schema_version=%s, %d rules, %d layouts, %d profiles",
        state.config.schema_version,
        len(state.config.rules),
        len(state.config.layouts),
        len(state.config.profiles),
    )

    app = QApplication.instance()
    assert app is not None, "QApplication must exist before main() runs"
    assert isinstance(app, QApplication), "main() requires a QApplication"

    install_translators(app)
    apply_theme(app, config.general.theme)

    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)

    # Probe before creating the tray; a negative probe on GNOME Wayland
    # surfaces the AppIndicator hint. On other desktops we still create
    # the tray — there's frequently a host that the watcher check can't
    # see (older Xfce builds, transient watcher gaps) and the fallthrough
    # is just "icon never becomes visible", which is no worse than
    # suppressing it.
    have_host = sni_host_available()
    awaiting_extension = False
    if not have_host:
        if is_gnome_wayland():
            awaiting_extension = True
            _maybe_show_appindicator_hint(app)
        else:
            log.warning(
                "no StatusNotifierHost detected; tray icon may be invisible"
            )

    tray_state = _initial_tray_state(
        config, awaiting_extension=awaiting_extension
    )
    controller = TrayController(tray_state)

    icons = load_tray_icons()
    tray = TrayIcon(controller, icons=icons)
    tray.show()

    # Backend + reducer. MockBackend keeps M3 self-contained; swapping to
    # a real backend only requires editing this block.
    backend = MockBackend()
    # Wire status signals before start() so a synchronous
    # backend_connected from start() still updates the tray.
    wire_backend_status(backend, controller, tray)
    await backend.start()
    state_store = StateStore(paths.state_dir() / "state.json")
    state_store.load()
    reducer = Reducer(backend=backend, config=config, state_store=state_store)
    reducer.bind_signals()
    await reducer.start()

    # Dialog lifetime is tied to ``main()`` so the C++ object stays alive
    # across multiple opens. It is ``None`` until first-opened and then
    # reused — re-opening the dialog reconstructs a fresh one so the
    # working copy starts clean from disk each time.
    dialog_ref: list[ConfigDialog | None] = [None]

    def open_dialog(section: str | None) -> None:
        current = dialog_ref[0]
        if current is not None:
            current.close()
            current.deleteLater()
        # Reload config so a just-saved file is re-parsed, and rebuild
        # the state snapshot the dialog edits.
        fresh_config = load_or_create()
        dialog = ConfigDialog(fresh_config, paths.config_file())
        if section is not None:
            dialog.select_section(section)
        dialog.saved.connect(
            lambda: controller.set_state(_initial_tray_state(load_or_create()))
        )
        dialog_ref[0] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    controller.intent.connect(
        lambda intent: _handle_intent(
            intent,
            close_event=close_event,
            reducer=reducer,
            open_dialog=open_dialog,
        )
    )

    try:
        await close_event.wait()
    finally:
        await reducer.stop()
        await backend.stop()

    return 0


def allow_headless_bootstrap() -> None:
    """Set ``QT_QPA_PLATFORM=offscreen`` when no display is available.

    Used by the ``perch --version`` fast path (keeps CI green without a
    display) and by tests. No-op when ``DISPLAY`` / ``WAYLAND_DISPLAY``
    are already set or the variable is pre-configured.
    """
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


# Back-compat alias for the M1 tests that import the module-level main.
if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(main()))
