"""``HyprlandBackend`` — :class:`WindowBackend` over ``hyprctl -j`` + ``.socket2.sock``.

Authoritative design: ``docs/06-backend-stubs.md`` §Hyprland.

Key design points:

* **Queries** shell out to ``hyprctl -j <query>`` (JSON output). More robust
  than parsing the plain-text query socket; Hyprland's IPC text format has
  shifted in minor releases.
* **Events** come from the ``.socket2.sock`` asyncio stream, one
  ``EVENT_NAME>>DATA\n`` line at a time, wrapped in a defensive try/except
  + ``log.debug`` for unknown events. Phase 2 research found at least one
  field-order shift around Hyprland 0.40, so defensive parsing is
  mandatory, not optional.
* **Minimum version:** Hyprland ≥ 0.40. ``start()`` invokes
  ``hyprctl version -j`` and refuses to proceed below that floor — unknown
  wire-format events are worse than a clean "unsupported" message.
* Like Sway: geometry applies cleanly only to floating windows; MAXIMIZED
  has no equivalent and raises ``BackendUnsupported``; hotkeys live in
  the user's Hyprland config.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Coroutine
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
    WindowType,
)
from perch.logging_privacy import summarize_keys

log = logging.getLogger("perch.backend.hyprland")

#: Minimum Hyprland version we support. Below this, ``start()`` raises
#: :class:`BackendUnavailable`. Rationale: the ``.socket2.sock`` event
#: format shifted around 0.40; anything below gets rejected rather than
#: dispatched to unknown-shape events.
MIN_HYPRLAND_VERSION = (0, 40, 0)

HYPRLAND_SIGNATURE_ENV = "HYPRLAND_INSTANCE_SIGNATURE"
HYPRLAND_RUNTIME_DIR_ENV = "XDG_RUNTIME_DIR"


_CAPABILITIES = Capabilities(
    can_set_position=True,
    can_set_size=True,
    can_set_monitor=True,
    can_set_desktop=True,
    can_set_state=True,
    can_enumerate_windows=True,
    can_observe_geometry=True,
    can_observe_outputs=True,
    can_register_hotkeys=False,
    can_preplace_windows=False,
    notes=(
        "Hyprland ≥ 0.40 via `hyprctl -j` queries + `.socket2.sock` event "
        "stream. Event parsing is defensive — unknown events are logged "
        "and skipped. Like Sway, geometry applies cleanly only to floating "
        "windows; MAXIMIZED is unsupported (core substitutes work-area "
        "geometry). Hotkeys go through the user's Hyprland config."
    ),
)


def _signature() -> str | None:
    sig = os.environ.get(HYPRLAND_SIGNATURE_ENV)
    return sig if sig else None


def _socket_paths() -> tuple[Path, Path] | None:
    """Return ``(.socket.sock, .socket2.sock)`` if the env is plausible.

    Hyprland since 0.39.x puts its runtime sockets under
    ``$XDG_RUNTIME_DIR/hypr/$HIS/``. Older versions used ``/tmp/hypr/$HIS``;
    we check both so ``is_available`` stays honest across versions.
    """
    sig = _signature()
    if sig is None:
        return None
    runtime = os.environ.get(HYPRLAND_RUNTIME_DIR_ENV)
    candidates: list[Path] = []
    if runtime:
        candidates.append(Path(runtime) / "hypr" / sig)
    candidates.append(Path("/tmp") / "hypr" / sig)
    for base in candidates:
        cmd = base / ".socket.sock"
        evt = base / ".socket2.sock"
        if cmd.exists() and evt.exists():
            return (cmd, evt)
    return None


def _parse_version(raw: str) -> tuple[int, int, int] | None:
    """Extract ``(major, minor, patch)`` from a Hyprland version string.

    ``hyprctl version -j`` returns a ``tag`` like ``"v0.40.0"`` or
    ``"v0.41.2-4-g1234abc"``; ``version`` is a human string. We parse the
    first ``vMAJOR.MINOR.PATCH`` we find. Returns ``None`` if nothing matches.
    """
    import re

    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", raw)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


class HyprlandBackend(WindowBackend):
    """Hyprland backend over ``hyprctl -j`` + ``.socket2.sock``.

    Cheap to construct. ``start()`` verifies the compositor version, primes
    the window/output caches, and spawns the event-loop task that reads
    ``.socket2.sock`` line by line.
    """

    def __init__(self) -> None:
        super().__init__()
        self._connected: bool = False
        self._windows: dict[WindowId, WindowInfo] = {}
        self._outputs: dict[OutputName, OutputInfo] = {}
        self._current_workspace: DesktopIndex = 0
        self._desktop_count: int = 1
        self._event_task: asyncio.Task[None] | None = None
        self._event_reader: asyncio.StreamReader | None = None
        self._event_writer: asyncio.StreamWriter | None = None
        # Background tasks spawned from the sync event dispatcher. Held in
        # a set so the asyncio runtime doesn't GC them mid-flight; the
        # done-callback discards them on completion.
        self._bg_tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def is_available(cls) -> bool:
        if _signature() is None:
            return False
        return shutil.which("hyprctl") is not None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        if shutil.which("hyprctl") is None:
            raise BackendUnavailable("hyprctl not found on PATH")
        paths = _socket_paths()
        if paths is None:
            raise BackendUnavailable(
                "Hyprland IPC sockets not found; "
                f"check {HYPRLAND_SIGNATURE_ENV} and {HYPRLAND_RUNTIME_DIR_ENV}"
            )
        _, evt_sock = paths  # cmd socket not used by the stub; queries go via hyprctl

        version = await self._probe_version()
        if version is not None and version < MIN_HYPRLAND_VERSION:
            v = ".".join(str(x) for x in version)
            minv = ".".join(str(x) for x in MIN_HYPRLAND_VERSION)
            raise BackendUnavailable(
                f"Hyprland {v} is below the minimum supported {minv}"
            )

        # Prime caches.
        await self.list_outputs()
        await self.list_windows()
        await self._refresh_workspaces()

        # Open the event stream.
        try:
            self._event_reader, self._event_writer = await asyncio.open_unix_connection(
                path=str(evt_sock)
            )
        except OSError as exc:
            raise BackendUnavailable(
                f"cannot open Hyprland event socket {evt_sock}: {exc}"
            ) from exc
        self._event_task = asyncio.create_task(self._event_loop())

        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False
        if self._event_task is not None:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass  # we issued the cancel; expected
            except Exception as exc:  # pragma: no cover — live-only path
                log.warning("hyprland event task shutdown raised: %s", exc)
            self._event_task = None
        if self._event_writer is not None:
            try:
                self._event_writer.close()
                await self._event_writer.wait_closed()
            except Exception as exc:  # pragma: no cover — tear-down
                log.debug("hyprland event writer close: %s", exc)
            self._event_writer = None
        self._event_reader = None
        self._windows.clear()
        self._outputs.clear()
        self.backend_disconnected.emit("stopped")

    @property
    def capabilities(self) -> Capabilities:
        return _CAPABILITIES

    # ── Queries ────────────────────────────────────────────────────────────

    async def list_windows(self) -> list[WindowInfo]:
        self._require_connected_or_priming()
        raw = await self._run_hyprctl_json("clients")
        if not isinstance(raw, list):
            return []
        infos: list[WindowInfo] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                info = _decode_client(entry)
            except (KeyError, TypeError, ValueError) as exc:
                log.debug(
                    "list_windows: skipping malformed client (%s): %s",
                    summarize_keys(entry),
                    exc,
                )
                continue
            infos.append(info)
        self._windows = {i.id: i for i in infos}
        return infos

    async def get_window(self, wid: WindowId) -> WindowInfo:
        self._require_connected_or_priming()
        if wid not in self._windows:
            await self.list_windows()
        try:
            return self._windows[wid]
        except KeyError:
            raise UnknownWindow(f"no Hyprland window with id {wid!r}") from None

    async def list_outputs(self) -> list[OutputInfo]:
        self._require_connected_or_priming()
        raw = await self._run_hyprctl_json("monitors")
        if not isinstance(raw, list):
            return []
        outs: list[OutputInfo] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                outs.append(_decode_monitor(entry))
            except (KeyError, TypeError, ValueError) as exc:
                log.debug(
                    "list_outputs: skipping malformed monitor (%s): %s",
                    summarize_keys(entry),
                    exc,
                )
                continue
        self._outputs = {o.name: o for o in outs}
        return outs

    async def current_desktop(self) -> DesktopIndex:
        self._require_connected_or_priming()
        await self._refresh_workspaces()
        return self._current_workspace

    async def desktop_count(self) -> int:
        self._require_connected_or_priming()
        await self._refresh_workspaces()
        return max(1, self._desktop_count)

    async def _refresh_workspaces(self) -> None:
        raw = await self._run_hyprctl_json("workspaces")
        if isinstance(raw, list):
            # Hyprland's workspace ids are 1-based and sparse; our
            # DesktopIndex is 0-based and dense. We report the count as the
            # number of active workspaces and translate the active id
            # (reported by ``hyprctl activeworkspace -j``) separately.
            self._desktop_count = max(1, len(raw))
        active = await self._run_hyprctl_json("activeworkspace")
        if isinstance(active, dict):
            wid = active.get("id")
            if isinstance(wid, int) and wid > 0:
                self._current_workspace = wid - 1

    # ── Commands ───────────────────────────────────────────────────────────

    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        self._require_connected()
        if wid not in self._windows:
            await self.list_windows()
        if wid not in self._windows:
            raise UnknownWindow(f"no Hyprland window with id {wid!r}")

        if monitor is not None:
            if monitor not in self._outputs:
                await self.list_outputs()
            if monitor not in self._outputs:
                raise UnknownOutput(f"no Hyprland output named {monitor!r}")

        # hyprctl window-address selector: ``address:0x...``.
        addr = f"address:{wid}"

        if desktop is not None:
            await self._run_hyprctl_dispatch(
                f"movetoworkspacesilent {desktop + 1},{addr}"
            )
        if monitor is not None:
            await self._run_hyprctl_dispatch(f"movewindow mon:{monitor},{addr}")

        # Absolute movement + resize. Like Sway, these only apply cleanly
        # on floating windows; tiled windows snap back to their container.
        await self._run_hyprctl_dispatch(f"moveactive exact {geom.x} {geom.y},{addr}")
        await self._run_hyprctl_dispatch(f"resizeactive exact {geom.w} {geom.h},{addr}")

        await self.list_windows()

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        self._require_connected()
        if wid not in self._windows:
            await self.list_windows()
        if wid not in self._windows:
            raise UnknownWindow(f"no Hyprland window with id {wid!r}")

        addr = f"address:{wid}"

        if state is WindowState.MAXIMIZED:
            raise BackendUnsupported(
                "Hyprland has no MAXIMIZED equivalent; core substitutes work-area geometry"
            )
        if state is WindowState.FULLSCREEN:
            # ``fullscreen 1`` is the "maximize-style" fullscreen (no bar
            # hidden). The ``fullscreen 2`` variant hides the bar; we pick
            # 1 because Perch's "fullscreen" concept matches maximized-area.
            await self._run_hyprctl_dispatch(f"fullscreen 1,{addr}")
            return
        if state is WindowState.MINIMIZED:
            # Hyprland doesn't have "minimise"; the closest idiom is to
            # move the window to the special (scratchpad) workspace.
            await self._run_hyprctl_dispatch(f"movetoworkspacesilent special,{addr}")
            return
        if state is WindowState.NORMAL:
            # Best-effort: clear fullscreen. There is no "un-minimise" that
            # maps back to the previous workspace from the special one;
            # callers typically pair NORMAL with a set_geometry() that
            # names the target workspace.
            await self._run_hyprctl_dispatch(f"fullscreen 0,{addr}")
            return
        raise BackendUnsupported(f"unknown window state: {state!r}")  # pragma: no cover

    async def close_window(self, wid: WindowId) -> None:
        self._require_connected()
        if wid not in self._windows:
            await self.list_windows()
        if wid not in self._windows:
            raise UnknownWindow(f"no Hyprland window with id {wid!r}")
        await self._run_hyprctl_dispatch(f"closewindow address:{wid}")

    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        raise BackendUnsupported(
            "Hyprland owns hotkeys via its config; bind keys to 'exec perch ...' "
            "in your Hyprland config instead."
        )

    async def unregister_hotkey(self, callback_id: str) -> None:
        # Match register_hotkey's "unsupported" story but allow the core to
        # call us during shutdown without raising.
        return

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _run_hyprctl_json(self, query: str) -> Any:
        """Run ``hyprctl -j <query>`` and return the decoded JSON."""
        proc = await asyncio.create_subprocess_exec(
            "hyprctl",
            "-j",
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace")
            raise BackendError(
                f"hyprctl {query!r} failed (rc={proc.returncode}): {err}"
            )
        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError as exc:
            raise BackendError(
                f"hyprctl {query!r} returned invalid JSON: {stdout!r}"
            ) from exc

    async def _run_hyprctl_dispatch(self, payload: str) -> None:
        """Run ``hyprctl dispatch <payload>``; raise on a non-zero / error reply."""
        proc = await asyncio.create_subprocess_exec(
            "hyprctl",
            "dispatch",
            payload,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode(errors="replace").strip()
        if proc.returncode != 0:
            raise BackendError(
                f"hyprctl dispatch {payload!r} failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace')}"
            )
        # Hyprland's dispatch replies with "ok" on success; anything else is
        # a runtime error (e.g. unknown dispatcher, address not found).
        if out and out.lower() != "ok":
            raise BackendError(f"hyprctl dispatch {payload!r} returned {out!r}")

    async def _probe_version(self) -> tuple[int, int, int] | None:
        """Return the Hyprland version tuple, or ``None`` if it can't be parsed."""
        raw = await self._run_hyprctl_json("version")
        if not isinstance(raw, dict):
            return None
        tag = str(raw.get("tag") or raw.get("version") or "")
        return _parse_version(tag)

    async def _event_loop(self) -> None:
        """Read ``.socket2.sock`` line by line until the connection drops.

        Each line is ``EVENT_NAME>>DATA\\n``. Unknown event names are
        logged at DEBUG and skipped — Phase 2 research established that the
        event list grows across minor releases and brittle parsing is a
        reliability hazard.
        """
        assert self._event_reader is not None
        reader = self._event_reader
        try:
            while self._connected:
                line = await reader.readline()
                if not line:
                    break
                try:
                    self._dispatch_event_line(line.decode(errors="replace").rstrip("\n"))
                except Exception as exc:  # defensive: never crash the reader loop
                    # Redact the raw event line: Hyprland's ``socket2``
                    # includes the active window title verbatim, which
                    # would otherwise land in the log.
                    event_name = (
                        line.decode(errors="replace").split(">>", 1)[0].rstrip("\n")
                        if b">>" in line
                        else "<malformed>"
                    )
                    log.debug("event dispatch failed for %r: %s", event_name, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover — live-only path
            log.warning("hyprland event loop ended unexpectedly: %s", exc)

    def _dispatch_event_line(self, line: str) -> None:
        """Translate one ``EVENT>>DATA`` line into Qt signal emissions.

        We deliberately dispatch a **small** set of well-known events; new
        ones added by upstream Hyprland are logged and ignored. See
        ``docs/06-backend-stubs.md`` §Hyprland.
        """
        if ">>" not in line:
            return
        name, _, data = line.partition(">>")
        if name in ("openwindow", "closewindow", "movewindow", "windowtitle",
                    "activewindow", "activewindowv2", "fullscreen",
                    "changefloatingmode"):
            # Re-query rather than parsing every event's field layout. The
            # event format has shifted between Hyprland minor releases; a
            # single ``hyprctl -j clients`` round-trip is stable and cheap.
            self._spawn_bg(self._on_window_event(name, data))
        elif name in ("monitoradded", "monitorremoved", "configreloaded"):
            self._spawn_bg(self._on_output_event(name, data))
        elif name in ("workspace", "createworkspace", "destroyworkspace"):
            self._spawn_bg(self._refresh_workspaces())
        else:
            # Log the event name only; ``data`` may contain the window
            # title (``windowtitle`` and ``activewindowv2`` emit it).
            del data
            log.debug("unhandled Hyprland event %r", name)

    def _spawn_bg(self, coro: Coroutine[Any, Any, None]) -> None:
        """Spawn a background task and track it so the runtime won't GC it."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _on_window_event(self, name: str, _data: str) -> None:
        prev = dict(self._windows)
        fresh = await self.list_windows()
        fresh_map = {w.id: w for w in fresh}
        for w in fresh:
            if w.id not in prev:
                self.window_opened.emit(w)
                self.geometry_changed.emit(w.id, w.geometry, w.monitor, w.desktop)
            elif prev[w.id] != w:
                if prev[w.id].geometry != w.geometry or prev[w.id].monitor != w.monitor:
                    self.geometry_changed.emit(w.id, w.geometry, w.monitor, w.desktop)
                else:
                    self.window_changed.emit(w)
        for wid in prev.keys() - fresh_map.keys():
            self.window_closed.emit(wid)

    async def _on_output_event(self, _name: str, _data: str) -> None:
        prev = dict(self._outputs)
        fresh = await self.list_outputs()
        fresh_map = {o.name: o for o in fresh}
        for o in fresh:
            if o.name not in prev:
                self.output_added.emit(o)
            elif prev[o.name] != o:
                self.output_changed.emit(o)
        for name in prev.keys() - fresh_map.keys():
            self.output_removed.emit(name)

    def _require_connected(self) -> None:
        if not self._connected:
            raise BackendDisconnected(
                "HyprlandBackend is not connected; call start() first"
            )

    def _require_connected_or_priming(self) -> None:
        """Permit queries during ``start()``'s own prime-the-cache phase."""


# ── JSON-decoding helpers (unit-testable on their own) ────────────────────


def _decode_client(entry: dict[str, Any]) -> WindowInfo:
    """Build a :class:`WindowInfo` from one element of ``hyprctl -j clients``."""
    wid = str(entry["address"])  # KeyError surfaces as a malformed-entry skip
    at = entry.get("at") or [0, 0]
    size = entry.get("size") or [0, 0]
    geom = Geometry(x=int(at[0]), y=int(at[1]), w=int(size[0]), h=int(size[1]))

    app_id = str(entry.get("initialClass") or entry.get("class") or "").lower()
    wm_class = str(entry.get("class") or "")
    monitor = str(entry.get("monitor") or "")

    # Workspace: ``workspace.id`` is 1-based; -99 is the special workspace.
    ws = entry.get("workspace") or {}
    ws_id = ws.get("id") if isinstance(ws, dict) else None
    desktop: DesktopIndex = 0
    state = WindowState.NORMAL
    if isinstance(ws_id, int):
        if ws_id == -99 or str(ws.get("name", "")).lower().startswith("special"):
            state = WindowState.MINIMIZED
        elif ws_id > 0:
            desktop = ws_id - 1

    if entry.get("fullscreen"):
        state = WindowState.FULLSCREEN

    pid: int | None = entry.get("pid") if isinstance(entry.get("pid"), int) else None
    if pid is not None and pid <= 0:
        pid = None

    # Monitor name: Hyprland reports it as the output index sometimes; we
    # only trust string names.
    if not isinstance(entry.get("monitor"), str):
        monitor = ""

    return WindowInfo(
        id=wid,
        app_id=app_id,
        wm_class=wm_class,
        title=str(entry.get("title") or ""),
        pid=pid,
        type=WindowType.NORMAL,
        state=state,
        geometry=geom,
        monitor=monitor,
        desktop=desktop,
    )


def _decode_monitor(entry: dict[str, Any]) -> OutputInfo:
    """Build an :class:`OutputInfo` from one element of ``hyprctl -j monitors``."""
    geom = Geometry(
        x=int(entry.get("x", 0)),
        y=int(entry.get("y", 0)),
        w=int(entry.get("width", 0)),
        h=int(entry.get("height", 0)),
    )
    # Hyprland exposes ``reserved`` as [left, top, right, bottom] pixel
    # struts; work_area is geometry minus those reserved margins.
    reserved = entry.get("reserved") or [0, 0, 0, 0]
    try:
        left, top, right, bottom = (int(v) for v in reserved[:4])
    except (TypeError, ValueError):
        left = top = right = bottom = 0
    work = Geometry(
        x=geom.x + left,
        y=geom.y + top,
        w=max(0, geom.w - left - right),
        h=max(0, geom.h - top - bottom),
    )
    # Hyprland reports refresh in Hz as a float; multiply by 1000 to match
    # WindowBackend's mHz convention.
    refresh_hz = float(entry.get("refreshRate") or 0.0)
    return OutputInfo(
        name=str(entry.get("name") or ""),
        geometry=geom,
        work_area=work,
        scale=float(entry.get("scale") or 1.0),
        refresh_mhz=int(refresh_hz * 1000),
        is_primary=bool(entry.get("focused", False)),
        is_connected=True,
    )


__all__ = ["MIN_HYPRLAND_VERSION", "HyprlandBackend"]
