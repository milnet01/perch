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
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import paths
from .backend.mock import MockBackend
from .config import Config, load_or_create
from .core.reducer import Reducer
from .core.state import AppState
from .core.state_store import StateStore
from .i18n import install_translators
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
from .ui.tray import TrayController, TrayIcon, TrayState

log = logging.getLogger(__name__)


def _load_tray_icon() -> QIcon:
    """Load the shipped Perch icon if the data file is on disk.

    Falls back to an empty ``QIcon`` (Qt draws a default placeholder). The
    icon-theme-based path lands in M7's polish pass alongside the symbolic
    variants — for M3 we ship the scalable SVG next to the package.
    """
    candidates = [
        Path(__file__).resolve().parents[2]
        / "data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg",
    ]
    for path in candidates:
        if path.is_file():
            return QIcon(str(path))
    return QIcon()


def _maybe_show_appindicator_hint(parent: QCoreApplication | None) -> None:
    """First-run warning for GNOME Wayland users without the extension.

    Gated per ``docs/08-ui.md`` §Tray on GNOME Wayland — shown only when
    the SNI probe is negative AND the session is GNOME on Wayland. Other
    desktops with a negative probe just log a warning; they don't get a
    dialog because there's no standard install path to point them at.
    """
    del parent
    box = QMessageBox()
    box.setWindowTitle("Perch — tray icon unavailable")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(
        "GNOME Wayland doesn't show tray icons by default. Please install "
        "the <b>AppIndicator and KStatusNotifierItem Support</b> GNOME "
        "extension to see Perch in your top bar."
    )
    box.setInformativeText(
        "Perch will continue running in the background; the config dialog "
        "is still reachable from <code>perch --settings</code>."
    )
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def _initial_tray_state(config: Config) -> TrayState:
    return TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=tuple(config.layouts.keys()),
        user_snaps=tuple(config.snaps.values()),
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
        case OpenConfigDialog():
            log.info("open config dialog (stub — lands in M3.b)")
        case OpenConfigFolder():
            _open_in_file_manager(paths.config_dir())
        case ShowAbout():
            log.info("about dialog (stub — lands in M3.b)")


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

    install_translators(app)

    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)

    tray_state = _initial_tray_state(config)
    controller = TrayController(tray_state)

    # Probe before creating the tray; a negative probe on GNOME Wayland
    # surfaces the AppIndicator hint. On other desktops we still create
    # the tray — there's frequently a host that the watcher check can't
    # see (older Xfce builds, transient watcher gaps) and the fallthrough
    # is just "icon never becomes visible", which is no worse than
    # suppressing it.
    have_host = sni_host_available()
    if not have_host:
        if is_gnome_wayland():
            _maybe_show_appindicator_hint(app)
        else:
            log.warning(
                "no StatusNotifierHost detected; tray icon may be invisible"
            )

    icon = _load_tray_icon()
    tray = TrayIcon(controller, icon=icon)
    tray.show()

    # Backend + reducer. MockBackend keeps M3 self-contained; swapping to
    # a real backend only requires editing this block.
    backend = MockBackend()
    await backend.start()
    state_store = StateStore(paths.state_dir() / "state.json")
    state_store.load()
    reducer = Reducer(backend=backend, config=config, state_store=state_store)
    reducer.bind_signals()
    await reducer.start()

    controller.intent.connect(
        lambda intent: _handle_intent(
            intent, close_event=close_event, reducer=reducer
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
