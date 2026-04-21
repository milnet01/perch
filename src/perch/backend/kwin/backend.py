"""``KWinBackend`` — the concrete :class:`WindowBackend` for Plasma 6 Wayland.

Progressive build-out. M5.d lands the skeleton:

* Transport lifecycle: ``start`` acquires the session-bus name, exports the
  :class:`PerchKWin1` service, loads the bundled JS script, and awaits the
  script's ``ScriptReady`` notification.
* :attr:`capabilities` matches ``docs/05-backend-kwin.md``.
* Enumeration queries (``list_windows`` / ``list_outputs`` / ``get_window`` /
  ``current_desktop`` / ``desktop_count``) round-trip through the
  long-poll dispatcher.
* Event routing: the backend is its own :class:`~service.EventSink`,
  translating JSON payloads into :mod:`perch.backend.types` dataclasses
  and emitting the standard :class:`WindowBackend` Qt signals.

Commands (``set_geometry`` / ``set_state`` / ``close_window``) and hotkey
registration land in M5.e / M5.f. Until then they raise
:class:`BackendUnsupported` / :class:`BackendDisconnected`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from perch.backend.base import (
    BackendDisconnected,
    BackendError,
    BackendUnavailable,
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
)
from perch.backend.types import (
    Capabilities,
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
)
from perch.logging_privacy import redact_payload, summarize_keys

from . import PLUGIN_ID, SERVICE_NAME
from .hotkeys import (
    HotkeyBusyError,
    HotkeyParseError,
    HotkeyProvider,
    choose_provider,
)
from .install import ensure_installed
from .protocol import (
    CommandError,
    decode_output_entry,
    decode_window_info,
    op_batch,
    op_close_window,
    op_query_active_window,
    op_query_current_desktop,
    op_query_desktop_count,
    op_query_outputs,
    op_query_window,
    op_query_windows,
    op_set_desktop,
    op_set_frame_geometry,
    op_set_full_screen,
    op_set_maximize_mode,
    op_set_minimized,
    unwrap_ok,
)
from .scripting import (
    KWIN_SCRIPTING_OBJ,
    KWIN_SERVICE,
    KWinScript,
    KWinScripting,
    install_and_run_script,
    unload_script_if_loaded,
)
from .service import PerchKWin1

log = logging.getLogger("perch.backend.kwin")


#: How long we'll wait for the JS script's ``ScriptReady`` ping after calling
#: ``run()``. Matches the ceiling used in the M2.5 spike.
SCRIPT_READY_TIMEOUT_S = 5.0

#: Default timeout for a single ``execute`` round-trip (query or command).
#: A query that takes longer than this on a non-stressed KWin is almost
#: always a symptom of a dead script rather than a slow one.
COMMAND_TIMEOUT_S = 5.0


_BusSetup = Callable[[str], Awaitable[None]]
_ScriptingFactory = Callable[[], Awaitable["KWinScripting"]]
_ScriptInstaller = Callable[[], Path]


_CAPABILITIES = Capabilities(
    can_set_position=True,
    can_set_size=True,
    can_set_monitor=True,
    can_set_desktop=True,
    can_set_state=True,
    can_enumerate_windows=True,
    can_observe_geometry=True,
    can_observe_outputs=True,
    can_register_hotkeys=True,
    can_preplace_windows=True,
    notes=(
        "KWin scripting on Plasma >= 6 via bundled script + "
        "GlobalShortcuts portal (KGlobalAccel fallback when the portal "
        "is unavailable). Pre-paint placement is best-effort; occasional "
        "first-frame flicker is possible but usually imperceptible."
    ),
)


class KWinBackend(WindowBackend):
    """KWin / Plasma 6 Wayland backend.

    Instantiable with no arguments for production use; tests can pass
    ``bus_setup`` / ``scripting_factory`` / ``script_installer`` overrides
    to swap out the pieces that need a live session bus.
    """

    def __init__(
        self,
        *,
        plugin_id: str = PLUGIN_ID,
        bus_setup: _BusSetup | None = None,
        scripting_factory: _ScriptingFactory | None = None,
        script_installer: _ScriptInstaller | None = None,
        hotkey_provider: HotkeyProvider | None = None,
    ) -> None:
        super().__init__()
        self._plugin_id = plugin_id
        self._bus_setup = bus_setup or _default_bus_setup
        self._scripting_factory = scripting_factory or _default_scripting_factory
        self._script_installer = script_installer or ensure_installed
        self._hotkey_provider: HotkeyProvider | None = hotkey_provider

        self._service: PerchKWin1 | None = None
        self._scripting: KWinScripting | None = None
        self._per_script: KWinScript | None = None
        self._script_id: int | None = None
        self._connected: bool = False

        # Keyed by WindowId. Rebuilt on every query; also mutated by event
        # handlers so get_window() can return fresh state without a
        # round-trip for each call.
        self._windows: dict[WindowId, WindowInfo] = {}
        # Cache of known outputs so on_outputs_changed can diff and emit
        # proper output_added / output_removed / output_changed signals.
        self._outputs: dict[OutputName, OutputInfo] = {}
        # Background tasks we spawn from sync event handlers — held so the
        # asyncio runtime doesn't GC them mid-flight.
        self._bg_tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def is_available(cls) -> bool:
        """Cheap env probe: are we in a KDE/Plasma Wayland session?

        Mirrors the :func:`_probe_session_env` heuristic without raising —
        we want :func:`perch.backend.select` to be able to ask "should I
        pick KWin?" without side-effects on the D-Bus session.
        """
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        if session_type and session_type != "wayland":
            return False
        if current_desktop and "KDE" not in current_desktop:
            return False
        # With no env at all we can't be sure; report unavailable so select()
        # falls through rather than attempting a bus round-trip speculatively.
        return "KDE" in current_desktop

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        _probe_session_env()
        try:
            await self._bus_setup(SERVICE_NAME)
        except Exception as exc:
            raise BackendUnavailable(f"could not acquire {SERVICE_NAME}: {exc}") from exc

        self._service = PerchKWin1(self)
        await self._service.export()

        self._scripting = await self._scripting_factory()
        # Defensive: if Perch crashed previously, the same plugin id may still
        # be registered. Unload now so loadScript can bind a fresh instance.
        await unload_script_if_loaded(self._scripting, self._plugin_id)

        main_js = self._script_installer()
        self._script_id, self._per_script = await install_and_run_script(
            self._scripting, main_js, self._plugin_id
        )

        try:
            await asyncio.wait_for(
                self._service.script_ready.wait(),
                timeout=SCRIPT_READY_TIMEOUT_S,
            )
        except TimeoutError as exc:
            raise BackendUnavailable(
                f"KWin script did not signal ScriptReady within {SCRIPT_READY_TIMEOUT_S}s"
            ) from exc

        if self._hotkey_provider is None:
            self._hotkey_provider = await choose_provider(self._emit_hotkey_fired)
        else:
            # Caller-supplied provider (tests, or a user swapping in a
            # custom implementation). Wire our on_fired sink either way —
            # a second start() on an already-started provider is allowed
            # and simply re-binds the callback.
            await self._hotkey_provider.start(self._emit_hotkey_fired)

        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False

        if self._hotkey_provider is not None:
            try:
                await self._hotkey_provider.stop()
            except Exception as exc:
                log.debug("hotkey provider stop: %s", exc)
            self._hotkey_provider = None

        if self._service is not None:
            # Must invalidate before unloading so orphan PollCommand handlers
            # don't consume the next command queued for a future instance.
            self._service.invalidate_polls()

        if self._scripting is not None:
            await unload_script_if_loaded(self._scripting, self._plugin_id)

        if self._service is not None:
            self._service.reset_completion_state()

        self._windows.clear()
        self._service = None
        self._scripting = None
        self._per_script = None
        self._script_id = None
        self.backend_disconnected.emit("stopped")

    # ── Capabilities ──────────────────────────────────────────────────────

    @property
    def capabilities(self) -> Capabilities:
        return _CAPABILITIES

    # ── Enumeration ────────────────────────────────────────────────────────

    async def list_windows(self) -> list[WindowInfo]:
        self._require_connected()
        assert self._service is not None
        result = await self._service.execute(op_query_windows(), timeout=COMMAND_TIMEOUT_S)
        unwrap_ok(result)
        payloads = result.get("windows")
        if not isinstance(payloads, list):
            return []
        infos: list[WindowInfo] = []
        for entry in payloads:
            if not isinstance(entry, dict):
                continue
            try:
                info = decode_window_info(entry)
            except (KeyError, ValueError, TypeError) as exc:
                log.debug(
                    "list_windows: skipping malformed entry (%s): %s",
                    summarize_keys(entry),
                    exc,
                )
                continue
            infos.append(info)
            self._windows[info.id] = info
        return infos

    async def get_window(self, wid: WindowId) -> WindowInfo:
        self._require_connected()
        assert self._service is not None
        try:
            result = await self._service.execute(
                op_query_window(wid), timeout=COMMAND_TIMEOUT_S
            )
        except CommandError as exc:
            # Shouldn't happen at this layer — execute returns the dict as-is;
            # but if a future sdbus change wraps it we surface UnknownWindow.
            if exc.kind == "unknown_window":
                raise UnknownWindow(wid) from exc
            raise
        if not result.get("ok"):
            if result.get("error") == "unknown_window":
                raise UnknownWindow(wid)
            raise BackendError(f"get_window failed: {result!r}")
        payload = result.get("window")
        if not isinstance(payload, dict):
            raise BackendError(f"get_window malformed response: {result!r}")
        info = decode_window_info(payload)
        self._windows[info.id] = info
        return info

    async def get_active_window(self) -> WindowInfo | None:
        """Query KWin for the currently-focused normal window.

        Returns ``None`` when the JS side reports ``workspace.activeWindow``
        as null or a non-``normalWindow`` (e.g. focus on the desktop, a
        menu, a tooltip).
        """
        self._require_connected()
        assert self._service is not None
        result = await self._service.execute(
            op_query_active_window(), timeout=COMMAND_TIMEOUT_S
        )
        unwrap_ok(result)
        payload = result.get("window")
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise BackendError(
                f"get_active_window malformed response: {result!r}"
            )
        info = decode_window_info(payload)
        self._windows[info.id] = info
        return info

    async def list_outputs(self) -> list[OutputInfo]:
        self._require_connected()
        assert self._service is not None
        result = await self._service.execute(op_query_outputs(), timeout=COMMAND_TIMEOUT_S)
        unwrap_ok(result)
        raw = result.get("outputs")
        if not isinstance(raw, list):
            return []
        outputs: list[OutputInfo] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                continue
            decoded = decode_output_entry(entry)
            outputs.append(
                OutputInfo(
                    name=decoded["name"],
                    geometry=decoded["geometry"],
                    # Plasma 6 doesn't expose per-output work-area via the
                    # scripting API; we default to the full geometry.
                    # docs/05-backend-kwin.md §Outputs.
                    work_area=decoded["geometry"],
                    scale=decoded["scale"],
                    refresh_mhz=decoded["refresh_mhz"],
                    # KWin's notion of "primary" is not reliably exposed by
                    # the scripting API; first-listed output is the de-facto
                    # primary on every Plasma configuration I've seen.
                    is_primary=(i == 0),
                    is_connected=True,
                )
            )
        self._outputs = {o.name: o for o in outputs}
        return outputs

    async def current_desktop(self) -> DesktopIndex:
        self._require_connected()
        assert self._service is not None
        result = await self._service.execute(
            op_query_current_desktop(), timeout=COMMAND_TIMEOUT_S
        )
        unwrap_ok(result)
        raw = result.get("desktop")
        if isinstance(raw, int):
            return raw
        return 0

    async def desktop_count(self) -> int:
        self._require_connected()
        assert self._service is not None
        result = await self._service.execute(
            op_query_desktop_count(), timeout=COMMAND_TIMEOUT_S
        )
        unwrap_ok(result)
        raw = result.get("count")
        if isinstance(raw, int) and raw > 0:
            return raw
        return 1

    # ── Commands ───────────────────────────────────────────────────────────

    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        self._require_connected()
        assert self._service is not None
        if monitor is not None and monitor not in self._outputs:
            # Hit the wire once in case the cache is stale before we raise.
            await self.list_outputs()
            if monitor not in self._outputs:
                raise UnknownOutput(monitor)

        ops: list[dict[str, Any]] = []
        if desktop is not None:
            ops.append(op_set_desktop(wid, desktop))
        ops.append(
            op_set_frame_geometry(wid, geom, output=monitor, preplace=True)
        )

        payload = op_batch(ops) if len(ops) > 1 else ops[0]
        try:
            result = await self._service.execute(payload, timeout=COMMAND_TIMEOUT_S)
        except CommandError as exc:
            self._translate_error(wid, exc.kind, monitor=monitor)
            raise
        if not result.get("ok"):
            self._translate_error(
                wid,
                str(result.get("error", "")),
                monitor=monitor,
                batch=result.get("batch"),
            )
            # _translate_error raises if it can; fall through if not mapped.
            raise BackendError(f"set_geometry failed: {result!r}")

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        self._require_connected()
        assert self._service is not None
        ops: list[dict[str, Any]] = []
        if state is WindowState.FULLSCREEN:
            # Fullscreen supersedes everything.
            ops = [
                op_set_minimized(wid, False),
                op_set_full_screen(wid, True),
            ]
        elif state is WindowState.MAXIMIZED:
            ops = [
                op_set_minimized(wid, False),
                op_set_full_screen(wid, False),
                op_set_maximize_mode(wid, vertical=True, horizontal=True),
            ]
        elif state is WindowState.MINIMIZED:
            ops = [op_set_minimized(wid, True)]
        elif state is WindowState.NORMAL:
            ops = [
                op_set_full_screen(wid, False),
                op_set_minimized(wid, False),
                op_set_maximize_mode(wid, vertical=False, horizontal=False),
            ]
        else:  # pragma: no cover — enum exhausted above
            raise BackendUnsupported(f"unknown window state: {state!r}")

        payload = op_batch(ops) if len(ops) > 1 else ops[0]
        try:
            result = await self._service.execute(payload, timeout=COMMAND_TIMEOUT_S)
        except CommandError as exc:
            self._translate_error(wid, exc.kind)
            raise
        if not result.get("ok"):
            self._translate_error(wid, str(result.get("error", "")), batch=result.get("batch"))
            raise BackendError(f"set_state failed: {result!r}")

    async def close_window(self, wid: WindowId) -> None:
        self._require_connected()
        assert self._service is not None
        try:
            result = await self._service.execute(
                op_close_window(wid), timeout=COMMAND_TIMEOUT_S
            )
        except CommandError as exc:
            self._translate_error(wid, exc.kind)
            raise
        if not result.get("ok"):
            self._translate_error(wid, str(result.get("error", "")))
            raise BackendError(f"close_window failed: {result!r}")

    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        self._require_connected()
        if self._hotkey_provider is None:
            raise BackendUnsupported("no hotkey provider available")
        try:
            await self._hotkey_provider.register(callback_id, accel)
        except HotkeyParseError as exc:
            self.backend_error.emit(f"hotkey unavailable: {exc}")
            raise
        except HotkeyBusyError as exc:
            # Per docs/03: non-fatal hotkey conflicts become a backend_error
            # signal *and* re-raise so the caller can redisplay their UI.
            self.backend_error.emit(f"hotkey unavailable: {exc}")
            raise

    async def unregister_hotkey(self, callback_id: str) -> None:
        self._require_connected()
        if self._hotkey_provider is None:
            return
        await self._hotkey_provider.unregister(callback_id)

    def _emit_hotkey_fired(self, callback_id: str) -> None:
        """Sink for the hotkey provider's ``on_fired`` callback."""
        self.hotkey_fired.emit(callback_id)

    # ── Error translation ─────────────────────────────────────────────────

    def _translate_error(
        self,
        wid: WindowId,
        kind: str,
        *,
        monitor: OutputName | None = None,
        batch: Any = None,
    ) -> None:
        """Raise the right backend-taxonomy exception for a script error kind.

        Called from every command site; each caller re-raises a generic
        BackendError if nothing matches so we never swallow an unknown code.
        When a batched op fails, ``batch`` carries the per-op results so we
        can surface the first failure rather than the top-level 'ok' flag.
        """
        if isinstance(batch, list):
            for sub in batch:
                if isinstance(sub, dict) and not sub.get("ok"):
                    self._translate_error(
                        wid, str(sub.get("error", "")), monitor=monitor
                    )
                    # If the sub-error wasn't mappable, keep trying the rest.
        if kind == "unknown_window":
            raise UnknownWindow(wid)
        if kind == "unknown_output":
            raise UnknownOutput(monitor or "")

    # ── EventSink: service → Qt signals ────────────────────────────────────

    def on_window_added(self, payload: dict[str, Any]) -> None:
        try:
            info = decode_window_info(payload)
        except (KeyError, ValueError, TypeError) as exc:
            log.warning(
                "WindowAdded: malformed payload %r: %s",
                redact_payload(payload),
                exc,
            )
            return
        self._windows[info.id] = info
        self.window_opened.emit(info)
        self.geometry_changed.emit(info.id, info.geometry, info.monitor, info.desktop)

    def on_window_removed(self, payload: dict[str, Any]) -> None:
        wid = payload.get("id")
        if not isinstance(wid, str):
            return
        self._windows.pop(wid, None)
        self.window_closed.emit(wid)

    def on_window_geometry_changed(self, payload: dict[str, Any]) -> None:
        try:
            info = decode_window_info(payload)
        except (KeyError, ValueError, TypeError) as exc:
            log.debug(
                "WindowGeometryChanged: malformed payload %r: %s",
                redact_payload(payload),
                exc,
            )
            return
        previous = self._windows.get(info.id)
        self._windows[info.id] = info
        if (
            previous is None
            or previous.geometry != info.geometry
            or previous.monitor != info.monitor
            or previous.desktop != info.desktop
        ):
            self.geometry_changed.emit(info.id, info.geometry, info.monitor, info.desktop)

    def on_window_properties_changed(self, payload: dict[str, Any]) -> None:
        try:
            info = decode_window_info(payload)
        except (KeyError, ValueError, TypeError) as exc:
            log.debug(
                "WindowPropertiesChanged: malformed payload %r: %s",
                redact_payload(payload),
                exc,
            )
            return
        self._windows[info.id] = info
        self.window_changed.emit(info)

    def on_outputs_changed(self) -> None:
        # We can't do a D-Bus round-trip synchronously from the sink; spawn
        # a task that re-queries + diffs + emits the proper per-output
        # signals. The D-Bus call that got us here returns immediately.
        task = asyncio.create_task(self._reconcile_outputs())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _reconcile_outputs(self) -> None:
        prev = dict(self._outputs)  # snapshot before list_outputs rewrites it
        try:
            fresh = await self.list_outputs()
        except (BackendError, CommandError) as exc:
            log.warning("outputs reconciliation failed: %s", exc)
            return
        fresh_map = {o.name: o for o in fresh}
        for name, info in fresh_map.items():
            if name not in prev:
                self.output_added.emit(info)
            elif prev[name] != info:
                self.output_changed.emit(info)
        for name in prev.keys() - fresh_map.keys():
            self.output_removed.emit(name)

    def on_script_ready(self, payload: dict[str, Any]) -> None:
        version = payload.get("version")
        log.info("KWin script ready (version=%r)", version)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self._connected or self._service is None:
            raise BackendDisconnected(
                "KWinBackend is not connected; call start() first"
            )


# ── Dependency-injection indirection (for tests) ───────────────────────────


async def _default_bus_setup(service_name: str) -> None:
    """Open the session bus and claim ``service_name``.

    Idempotent within a single process: if a previous ``start()`` already
    acquired the name and we haven't exited, ``request_default_bus_name``
    raises :class:`SdBusRequestNameExistsError` — we treat that as success
    rather than fighting for a name we already own.
    """
    import contextlib

    from sdbus import (
        request_default_bus_name_async,
        sd_bus_open_user,
        set_default_bus,
    )
    from sdbus.sd_bus_internals import SdBusRequestNameExistsError

    set_default_bus(sd_bus_open_user())
    # Idempotent: if we already own the name from a previous start() in
    # this process, sdbus raises SdBusRequestNameExistsError — that's
    # success, not failure.
    with contextlib.suppress(SdBusRequestNameExistsError):
        await request_default_bus_name_async(service_name)


async def _default_scripting_factory() -> KWinScripting:
    return KWinScripting.new_proxy(KWIN_SERVICE, KWIN_SCRIPTING_OBJ)


# ── Environment probe ──────────────────────────────────────────────────────


def _probe_session_env() -> None:
    """Raise :class:`BackendUnavailable` if this is clearly not Plasma 6 Wayland.

    Heuristic — the compositor's D-Bus services are the only authoritative
    signal, but testing them means talking to the bus first, which is
    exactly what we want to avoid when a dev is just running ``pytest`` on
    a non-KDE machine. We fall back to the environment:

    * ``XDG_SESSION_TYPE`` == ``wayland``
    * ``XDG_CURRENT_DESKTOP`` contains ``KDE``

    If either is clearly violated we raise; otherwise we proceed optimistically
    and the bus probe will handle the rest.
    """
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if session_type and session_type != "wayland":
        raise BackendUnavailable(
            f"KWinBackend requires a Wayland session (XDG_SESSION_TYPE={session_type!r})"
        )
    if current_desktop and "KDE" not in current_desktop.upper():
        raise BackendUnavailable(
            f"KWinBackend requires a KDE/Plasma desktop "
            f"(XDG_CURRENT_DESKTOP={current_desktop!r})"
        )


__all__ = [
    "COMMAND_TIMEOUT_S",
    "SCRIPT_READY_TIMEOUT_S",
    "KWinBackend",
]
