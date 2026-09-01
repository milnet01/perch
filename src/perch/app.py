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
import contextlib
import logging
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__, autostart, paths
from .backend import BackendError, BackendUnavailable, WindowBackend, select
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
    OpenUrl,
    Quit,
    ReapplyRules,
    ShowAbout,
    SnapFocused,
    TogglePause,
)
from .ui.onboarding import appindicator_guidance, run_setup_wizard
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
    # Shared with the wizard's tray health-check row so the two cannot
    # drift; the helper keeps this string's ``perch.app`` context.
    box.setText(appindicator_guidance())
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


def _select_backend() -> WindowBackend:
    """Pick a backend for the current session.

    Probes via :func:`perch.backend.select`. Falls back to
    :class:`MockBackend` when no real transport is detected — that
    keeps headless dev boxes (and CI smoke runs) usable without a
    compositor, at the cost of an inert Windows pane. A log line makes
    the fallback explicit so users debugging "my windows aren't showing
    up" can see the chosen backend at startup.
    """
    try:
        cls = select()
        backend = cls()
        log.info("backend: selected %s", cls.__name__)
        return backend
    except BackendUnavailable as exc:
        log.warning(
            "backend: no real transport detected (%s); falling back to MockBackend",
            exc,
        )
        return MockBackend()


# Background tasks launched from _handle_intent. Python's GC can reclaim
# the Task object otherwise and the coroutine silently stops (this is the
# RUF006 asyncio footgun). A module-level set keeps them alive until the
# done-callback prunes them.
_intent_tasks: set[asyncio.Task[None]] = set()


def _spawn(coro: Coroutine[Any, Any, None]) -> None:
    """Schedule ``coro`` and retain a strong reference until it finishes."""
    task: asyncio.Task[None] = asyncio.create_task(coro)
    _intent_tasks.add(task)
    task.add_done_callback(_on_intent_task_done)


def _on_intent_task_done(task: asyncio.Task[None]) -> None:
    """Prune the task, and log anything it raised.

    Without retrieving the exception, asyncio reports it on the ROOT logger,
    which ``configure_logging`` never touches — so it goes to stderr and never
    reaches ``perch.log``, the file a user attaches to a bug report. A menu
    action that silently did nothing is exactly the symptom that hides.
    """
    _intent_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("intent task failed: %s", exc, exc_info=exc)


async def _cancel_intent_tasks() -> None:
    """Cancel and await every in-flight intent task.

    ``docs/01-architecture.md`` §Teardown order makes this step 2, before
    ``backend.stop()`` — otherwise an ActivateLayout still mid-await can issue
    a geometry write against a transport that has already been torn down.
    """
    pending = [t for t in _intent_tasks if not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _handle_intent(
    intent: Intent,
    *,
    close_event: asyncio.Event,
    reducer: Reducer,
    open_dialog: Callable[[str | None], None] | None = None,
    quit_app: Callable[[], None] | None = None,
) -> None:
    """Translate a UI intent into core work.

    Kept as a plain function (rather than a controller method) so tests
    can exercise the intent→core translation without a QApplication.
    """
    match intent:
        case Quit():
            # Only trip the close_event; ``main()`` drains its async
            # cleanup in its finally block and then calls app.quit()
            # itself as the last step. Calling app.quit() here stops
            # the qasync loop (which uses Qt's event loop as its
            # engine) before the finally can run, producing the
            # "Event loop stopped before Future completed" traceback.
            _ = quit_app  # retained so existing callers keep working
            close_event.set()
        case TogglePause():
            reducer.toggle_pause()
        case ReapplyRules():
            _spawn(reducer.reapply())
        case ActivateLayout(name):
            _spawn(reducer.activate_layout(name))
        case SnapFocused(preset):
            _spawn(_snap_active_window(reducer, preset))
        case OpenConfigDialog(section):
            if open_dialog is not None:
                open_dialog(section)
            else:
                log.info("open config dialog: section=%r (no dialog wired)", section)
        case OpenConfigFolder():
            _open_in_file_manager(paths.config_dir())
        case OpenUrl(url):
            # Under Flatpak Qt routes this through the OpenURI portal, so
            # no network or browser permission is needed in the manifest.
            if not QDesktopServices.openUrl(QUrl(url)):
                log.warning("could not open %s in a browser", url)
        case ShowAbout():
            _show_about_dialog()


def _show_about_dialog() -> None:
    """Render a simple About dialog: version, license, project URL."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    box = QMessageBox()
    box.setWindowTitle(
        QCoreApplication.translate("perch.app", "About Perch")
    )
    box.setIcon(QMessageBox.Icon.Information)
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(
        QCoreApplication.translate(
            "perch.app",
            "<h3>Perch {version}</h3>"
            "<p>Persistent, compositor-aware window geometry "
            "manager for Linux desktops.</p>"
            "<p>License: GPL-3.0-or-later<br>"
            "Home: <a href=\"https://github.com/milnet01/perch\">"
            "github.com/milnet01/perch</a></p>",
        ).format(version=__version__)
    )
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


async def _snap_active_window(reducer: Reducer, preset: str) -> None:
    """Query the active window and apply ``preset`` to it.

    Uses the reducer's already-live references (backend + config) so
    we pick up the user's current ``[snaps]`` table. Failure modes
    are logged at WARNING and swallowed — the tray menu can't surface
    a modal, so a silent no-op is the least-surprising behaviour.
    """
    from perch.backend.base import BackendError, BackendUnsupported
    from perch.core.actions import ApplyAction, PresetGeometry
    from perch.core.resolver import ResolveError, resolve_action

    backend = reducer.backend
    try:
        info = await backend.get_active_window()
    except BackendUnsupported:
        log.warning(
            "snap focused: backend %s does not report focus — use the "
            "Windows pane's Apply preset button instead",
            type(backend).__name__,
        )
        return
    except BackendError as exc:
        log.warning("snap focused: get_active_window failed: %s", exc)
        return
    if info is None:
        log.info(
            "snap focused: no focused normal window; ignoring (tried %r)",
            preset,
        )
        return

    try:
        outputs = await backend.list_outputs()
    except BackendError as exc:
        log.warning("snap focused: list_outputs failed: %s", exc)
        return

    action = ApplyAction(geometry=PresetGeometry(preset))
    try:
        placement = resolve_action(
            action, info, outputs, reducer.config.snaps
        )
    except ResolveError as exc:
        log.warning(
            "snap focused: cannot resolve preset %r: %s", preset, exc
        )
        return
    if placement.geometry is None or placement.monitor is None:
        log.warning(
            "snap focused: preset %r resolved to an empty placement", preset
        )
        return
    try:
        await backend.set_geometry(
            info.id, placement.geometry, placement.monitor
        )
    except BackendError as exc:
        log.warning(
            "snap focused: backend rejected set_geometry: %s", exc
        )


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


async def main(
    *,
    have_sni_host: bool | None = None,
    gnome_wayland: bool | None = None,
) -> int:
    """Run Perch. Returns the process exit code.

    Loads config, chooses a backend via :func:`perch.backend.select`,
    shows the tray icon (when an SNI host is available or the session
    is GNOME-Wayland and we surface the hint), and wires the reducer.

    ``have_sni_host`` and ``gnome_wayland`` are probed synchronously in
    :func:`perch.__main__.cli` before the asyncio loop starts —
    sdbus's sync-read API refuses to run with an active loop attached.
    Callers can override both for tests (e.g. to simulate a negative
    SNI probe on GNOME Wayland); ``None`` probes live.
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

    # Perch is a tray app — closing the Preferences dialog must not
    # terminate the process. Qt's default ``quitOnLastWindowClosed``
    # treats a ``QSystemTrayIcon`` as "not a window" and fires
    # ``aboutToQuit`` the moment the user clicks ✕ on the dialog,
    # which races the async teardown in ``main()``'s finally block
    # ("Event loop stopped before Future completed"). Opting out here
    # makes the tray icon + asyncio-loop the authoritative lifetime
    # owners; the dialog close button only hides the dialog.
    app.setQuitOnLastWindowClosed(False)

    # Reconcile autostart with the current ``start_at_login`` value.
    # Runs before we start the backend so any side-effects (portal
    # permission dialog on Flatpak) don't interleave with tray bring-up.
    autostart.sync_from_config(config)

    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)

    # Install SIGINT / SIGTERM handlers so Ctrl+C at the terminal
    # triggers the same clean-shutdown path as the tray Quit intent —
    # without this, asyncio.run raises ``KeyboardInterrupt`` mid-await
    # and prints a traceback. Handlers only trip ``close_event``;
    # calling ``app.quit()`` here would stop the qasync loop before
    # ``main()``'s finally block can run its async teardown.
    def _handle_sigint() -> None:
        log.info("signal received; shutting down")
        close_event.set()

    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        # Windows' ProactorEventLoop doesn't implement add_signal_handler;
        # qasync on Linux does. Suppressing the error keeps this portable.
        loop.add_signal_handler(signal.SIGINT, _handle_sigint)
        loop.add_signal_handler(signal.SIGTERM, _handle_sigint)

    # SNI / GNOME probes land here as arguments — the sync D-Bus reads
    # that underpin them happen in ``__main__.cli`` before the asyncio
    # loop starts. A negative probe on GNOME Wayland surfaces the
    # AppIndicator hint; on other desktops we still create the tray
    # because the watcher probe can miss transient / older hosts and
    # the fallthrough is just "icon never becomes visible".
    have_host = sni_host_available() if have_sni_host is None else have_sni_host
    gnome = is_gnome_wayland() if gnome_wayland is None else gnome_wayland
    awaiting_extension = False
    if not have_host:
        if gnome:
            awaiting_extension = True
        else:
            log.warning(
                "no StatusNotifierHost detected; tray icon may be invisible"
            )

    # Backend selection — probe the current session via ``select()`` and
    # fall back to :class:`MockBackend` when no real transport is available
    # (covers headless dev boxes and ``PERCH_BACKEND=mock``). It runs here,
    # ahead of tray bring-up, because the wizard's Compositor row needs it.
    backend = _select_backend()

    # First run gets the setup wizard, on every desktop and independent of
    # the tray condition above. Its tray health-check row already covers
    # the no-tray case, so the standalone AppIndicator hint is skipped this
    # launch — no double notification. Later launches keep that hint as the
    # recurring safety net for a session that still has no tray host.
    # See ``docs/08-ui.md`` §First-run setup wizard.
    wizard_outcome = None
    if not config.general.onboarding_completed:
        wizard_outcome = run_setup_wizard(
            config, backend, None, have_host=have_host, gnome=gnome
        )
        config = wizard_outcome.config
    elif awaiting_extension:
        _maybe_show_appindicator_hint(app)

    tray_state = _initial_tray_state(
        config, awaiting_extension=awaiting_extension
    )
    controller = TrayController(tray_state)

    icons = load_tray_icons()
    tray = TrayIcon(controller, icons=icons)
    tray.show()

    # Wire status signals before start() so a synchronous
    # backend_connected from start() still updates the tray.
    wire_backend_status(backend, controller, tray)
    try:
        await backend.start()
    except BackendError as exc:
        # docs/01-architecture.md §Startup step 4: "If none match, log an error
        # and run in UI-only mode". start() is a documented raiser on three
        # backends — the ordinary trigger is a second Perch failing to take the
        # bus name — and unguarded it exited with a traceback with the tray
        # already on screen.
        log.error(
            "backend %s failed to start (%s); continuing in UI-only mode",
            type(backend).__name__,
            exc,
        )
        with contextlib.suppress(Exception):
            await backend.stop()
        backend = MockBackend()
        wire_backend_status(backend, controller, tray)
        await backend.start()
    state_store = StateStore(paths.state_dir() / "state.json")
    try:
        state_store.load()
    except Exception:
        # load() is contracted to degrade to an empty store rather than raise,
        # but a store that somehow does raise must not take startup with it:
        # the user loses restore-on-open, not the application.
        log.exception("state.json could not be loaded; starting with empty state")
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
        dialog = ConfigDialog(
            fresh_config,
            paths.config_file(),
            backend=backend,
            state_store=state_store,
        )
        if section is not None:
            dialog.select_section(section)
        def _on_saved() -> None:
            fresh = load_or_create()
            controller.set_state(_initial_tray_state(fresh))
            # Toggle autostart in sync with the just-saved config so the
            # "Start at login" checkbox has immediate effect — no restart
            # needed.
            autostart.sync_from_config(fresh)
            # Re-apply the theme so a light↔dark flip on Apply takes
            # effect live. Qt propagates the new palette to every
            # top-level widget, so open dialogs re-paint without a
            # reconstruction. ``"auto"`` re-probes the platform colour
            # scheme.
            apply_theme(app, fresh.general.theme)

        dialog.saved.connect(_on_saved)
        dialog_ref[0] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    # "Show me what else Perch can do" on the wizard's last page. Deferred
    # to here because ``open_dialog`` does not exist while the wizard runs.
    if wizard_outcome is not None and wizard_outcome.show_config_dialog:
        open_dialog(None)

    controller.intent.connect(
        lambda intent: _handle_intent(
            intent,
            close_event=close_event,
            reducer=reducer,
            open_dialog=open_dialog,
            quit_app=app.quit,
        )
    )

    try:
        await close_event.wait()
    finally:
        # docs/01-architecture.md §Teardown order: cancel background tasks and
        # gather (step 2) before stopping the backend (step 3).
        await _cancel_intent_tasks()
        # Each stop is independent. reducer.stop() flushes state.json, which
        # raises OSError on a full or read-only $XDG_STATE_HOME — and that must
        # not leave the KWin script loaded and the bus name held.
        try:
            await reducer.stop()
        except Exception:
            log.exception("reducer shutdown failed; continuing to stop backend")
        try:
            await backend.stop()
        except Exception:
            log.exception("backend shutdown failed")

    # Async cleanup is done — now tell Qt to wind down. ``app.quit()``
    # stops the qasync loop, which ``asyncio.run`` then closes cleanly.
    # This is the only place that calls ``app.quit()``; putting it in
    # the Quit-intent handler or the SIGINT handler would stop the
    # loop mid-finally (qasync: "Event loop stopped before Future
    # completed").
    app.quit()
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
