"""``SwayBackend`` — :class:`WindowBackend` over the i3-IPC socket at ``$SWAYSOCK``.

Authoritative design: ``docs/06-backend-stubs.md`` §Sway.

Key design points:

* The i3 IPC protocol is stable; Sway has not broken it in any 1.x release.
  We use the async :class:`i3ipc.aio.Connection` client — version pin lives
  in ``pyproject.toml`` under the ``sway`` extra.
* Sway is tiling-first. ``can_set_position = False`` reflects the fact that
  position writes only work on floating windows; the core's rules engine
  admits this in ``docs/07-rules-engine.md``. Users who want Perch to move
  specific windows on Sway set them ``floating enable`` in their Sway config.
* ``WindowState.MAXIMIZED`` has no direct Sway equivalent. We raise
  :class:`BackendUnsupported` and let the reducer substitute work-area
  geometry (see ``docs/07-rules-engine.md`` §Apply order).
* Sway owns hotkeys in its config; there is no runtime grab API. Users bind
  keys to ``swaymsg exec perch-cli ...`` invocations in their Sway config.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from i3ipc.aio import Connection as _AioConnection
    from i3ipc.con import Con as _Con

log = logging.getLogger("perch.backend.sway")


_CAPABILITIES = Capabilities(
    can_set_position=False,  # floating-only; tiled windows snap to their container
    can_set_size=True,
    can_set_monitor=True,
    can_set_desktop=True,
    can_set_state=True,
    can_enumerate_windows=True,
    can_observe_geometry=True,
    can_observe_outputs=True,
    can_register_hotkeys=False,  # Sway owns hotkeys via its config
    can_preplace_windows=False,
    notes=(
        "Sway/wlroots stub. Geometry applies only to floating windows; "
        "tiled windows snap to their container. MAXIMIZED state is "
        "unsupported (core substitutes work-area geometry). Hotkeys go "
        "through the user's Sway config, not Perch."
    ),
)


def _env_sockpath() -> str | None:
    """Return ``$SWAYSOCK`` if set and non-empty, else ``None``."""
    path = os.environ.get("SWAYSOCK")
    return path if path else None


class SwayBackend(WindowBackend):
    """Sway / wlroots backend over i3-IPC.

    Cheap to construct. ``start()`` opens the i3 connection, subscribes to
    the ``window`` + ``workspace`` + ``output`` event streams, and emits
    ``backend_connected``. ``stop()`` tears the connection down.
    """

    def __init__(self) -> None:
        super().__init__()
        self._conn: _AioConnection | None = None
        self._connected: bool = False
        self._windows: dict[WindowId, WindowInfo] = {}
        self._outputs: dict[OutputName, OutputInfo] = {}
        self._workspaces: list[dict[str, Any]] = []

    @classmethod
    def is_available(cls) -> bool:
        return _env_sockpath() is not None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        sock = _env_sockpath()
        if sock is None:
            raise BackendUnavailable("SWAYSOCK is not set; no Sway session detected")
        try:
            from i3ipc.aio import Connection
        except ImportError as exc:
            raise BackendUnavailable(
                "i3ipc is not installed; `pip install 'perch[sway]'` to enable SwayBackend"
            ) from exc

        try:
            self._conn = await Connection(socket_path=sock, auto_reconnect=False).connect()
        except OSError as exc:
            raise BackendUnavailable(f"cannot connect to Sway IPC at {sock!r}: {exc}") from exc

        await self._prime_tree()
        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False
        if self._conn is not None:
            # i3ipc.aio.Connection.main_quit stops the event loop; direct
            # close is main_quit + socket.close under the hood.
            try:
                self._conn.main_quit()
            except Exception as exc:  # pragma: no cover — best-effort tear-down
                log.debug("sway conn shutdown: %s", exc)
            self._conn = None
        self._windows.clear()
        self._outputs.clear()
        self._workspaces.clear()
        self.backend_disconnected.emit("stopped")

    @property
    def capabilities(self) -> Capabilities:
        return _CAPABILITIES

    # ── Queries ────────────────────────────────────────────────────────────

    async def list_windows(self) -> list[WindowInfo]:
        self._require_connected()
        await self._prime_tree()
        return list(self._windows.values())

    async def get_window(self, wid: WindowId) -> WindowInfo:
        self._require_connected()
        if wid not in self._windows:
            await self._prime_tree()
        try:
            return self._windows[wid]
        except KeyError:
            raise UnknownWindow(f"no Sway window with id {wid!r}") from None

    async def list_outputs(self) -> list[OutputInfo]:
        self._require_connected()
        assert self._conn is not None
        raw = await self._conn.get_outputs()
        outs: list[OutputInfo] = []
        for o in raw:
            if not getattr(o, "active", False):
                continue
            rect = getattr(o, "rect", None)
            if rect is None:
                continue
            geom = Geometry(x=rect.x, y=rect.y, w=rect.width, h=rect.height)
            outs.append(
                OutputInfo(
                    name=o.name,
                    geometry=geom,
                    # Sway IPC does not expose work-area separately; panels
                    # live outside the managed area. Downstream code treats
                    # geometry as the best-effort work area.
                    work_area=geom,
                    scale=float(getattr(o, "scale", 1.0) or 1.0),
                    # Sway exposes refresh in Hz, not mHz; multiply to
                    # match WindowBackend's documented unit.
                    refresh_mhz=int(float(getattr(o, "current_mode", {}).get("refresh", 0))),
                    is_primary=bool(getattr(o, "primary", False)),
                    is_connected=True,
                )
            )
        self._outputs = {o.name: o for o in outs}
        return outs

    async def current_desktop(self) -> DesktopIndex:
        self._require_connected()
        assert self._conn is not None
        workspaces = await self._conn.get_workspaces()
        for i, ws in enumerate(workspaces):
            if getattr(ws, "focused", False):
                return i
        return 0

    async def desktop_count(self) -> int:
        self._require_connected()
        assert self._conn is not None
        workspaces = await self._conn.get_workspaces()
        return max(1, len(workspaces))

    # ── Commands ───────────────────────────────────────────────────────────

    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        self._require_connected()
        assert self._conn is not None

        if wid not in self._windows:
            await self._prime_tree()
        if wid not in self._windows:
            raise UnknownWindow(f"no Sway window with id {wid!r}")

        if monitor is not None:
            if monitor not in self._outputs:
                await self.list_outputs()
            if monitor not in self._outputs:
                raise UnknownOutput(f"no Sway output named {monitor!r}")

        # Criteria: `[con_id=N]` is Sway's selector for a specific managed
        # window. WindowId is the con.id rendered as a decimal string.
        sel = f"[con_id={wid}]"
        cmds: list[str] = []

        if desktop is not None:
            cmds.append(f"{sel} move container to workspace number {desktop + 1}")
        if monitor is not None:
            cmds.append(f"{sel} move container to output {monitor}")

        # Sway geometry writes only apply to floating windows. We don't
        # force-float here — docs/06 §Sway documents that the user is
        # expected to mark the window floating; silently toggling would
        # surprise people. We still issue the resize/move and let Sway
        # ignore it for tiled windows. `move position` sets x/y; `resize
        # set` sets width/height.
        cmds.append(f"{sel} move position {geom.x}px {geom.y}px")
        cmds.append(f"{sel} resize set {geom.w}px {geom.h}px")

        await self._run_commands(cmds)
        # Re-read tree once the command settles so list_windows returns
        # the fresh geometry on the next call.
        await self._prime_tree()

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        self._require_connected()
        assert self._conn is not None

        if wid not in self._windows:
            await self._prime_tree()
        if wid not in self._windows:
            raise UnknownWindow(f"no Sway window with id {wid!r}")

        sel = f"[con_id={wid}]"

        if state is WindowState.MAXIMIZED:
            # Sway has no "maximize" in its model — tiled windows already
            # fill their container; floating windows don't have a maximize
            # toggle. The reducer substitutes work-area geometry.
            raise BackendUnsupported(
                "Sway has no MAXIMIZED equivalent; core substitutes work-area geometry"
            )
        if state is WindowState.FULLSCREEN:
            await self._run_commands([f"{sel} fullscreen enable"])
            return
        if state is WindowState.MINIMIZED:
            await self._run_commands([f"{sel} move scratchpad"])
            return
        if state is WindowState.NORMAL:
            await self._run_commands([f"{sel} fullscreen disable"])
            return
        raise BackendUnsupported(f"unknown window state: {state!r}")  # pragma: no cover

    async def close_window(self, wid: WindowId) -> None:
        self._require_connected()
        assert self._conn is not None
        if wid not in self._windows:
            await self._prime_tree()
        if wid not in self._windows:
            raise UnknownWindow(f"no Sway window with id {wid!r}")
        await self._run_commands([f"[con_id={wid}] kill"])

    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        raise BackendUnsupported(
            "Sway owns hotkeys via its config; bind keys to 'swaymsg exec perch ...' "
            "in your Sway config instead."
        )

    async def unregister_hotkey(self, callback_id: str) -> None:
        # No-op to match the "not supported" story from register_hotkey —
        # the core is allowed to call unregister during shutdown regardless.
        return

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _run_commands(self, cmds: list[str]) -> None:
        """Run one or more i3-IPC commands; raise :class:`BackendError` on failure."""
        assert self._conn is not None
        joined = ", ".join(cmds)
        replies = await self._conn.command(joined)
        for reply in replies:
            if not getattr(reply, "success", True):
                err = getattr(reply, "error", None) or "unspecified failure"
                raise BackendError(f"sway command failed ({err!r}): {joined}")

    async def _prime_tree(self) -> None:
        """Pull the full tree and rebuild ``_windows`` / ``_workspaces``."""
        assert self._conn is not None
        tree = await self._conn.get_tree()
        # Every leaf con with app_id/window_class is a managed window.
        self._windows = {
            str(leaf.id): _decode_window(leaf)
            for leaf in tree.leaves()
            if _is_managed(leaf)
        }

    def _require_connected(self) -> None:
        if not self._connected or self._conn is None:
            raise BackendDisconnected("SwayBackend is not connected; call start() first")


# ── i3ipc-con helpers (isolated so they can be unit-tested on stubs) ──────


def _is_managed(con: _Con) -> bool:
    """Leaf filter: include normal toplevel windows, exclude scratchpad placeholders."""
    # ``type == "con"`` and a pid → it's a managed client window. Sway also
    # uses "floating_con" for floating windows; both count.
    con_type = getattr(con, "type", "")
    if con_type not in ("con", "floating_con"):
        return False
    pid = getattr(con, "pid", None)
    return pid is not None


def _decode_window(con: _Con) -> WindowInfo:
    """Build a :class:`WindowInfo` from an ``i3ipc.Con``."""
    rect = con.rect
    geom = Geometry(x=rect.x, y=rect.y, w=rect.width, h=rect.height)

    # Sway reports Wayland clients with ``app_id``; XWayland clients with
    # ``window_class``. Prefer app_id; fall back to class.
    app_id = (getattr(con, "app_id", None) or "").lower()
    wm_class = getattr(con, "window_class", "") or ""
    if not app_id and wm_class:
        app_id = wm_class.lower()

    # Walk up the ancestry once: workspace and output both appear on the
    # way to the root, at known types. Sway workspaces can be named-only
    # (``num == -1``); those are reported as desktop 0.
    monitor = ""
    desktop: DesktopIndex = 0
    node: _Con | None = getattr(con, "parent", None)
    while node is not None:
        node_type = getattr(node, "type", "")
        if node_type == "workspace":
            num = getattr(node, "num", -1)
            if isinstance(num, int) and num > 0:
                desktop = num - 1
        elif node_type == "output":
            monitor = getattr(node, "name", "") or ""
        node = getattr(node, "parent", None)

    state = WindowState.NORMAL
    if getattr(con, "fullscreen_mode", 0):
        state = WindowState.FULLSCREEN
    # ``scratchpad_state`` on the i3ipc object tells us if the window is
    # in the hidden scratchpad — the closest Sway equivalent to minimised.
    if getattr(con, "scratchpad_state", "none") not in ("none", None):
        state = WindowState.MINIMIZED

    return WindowInfo(
        id=str(con.id),
        app_id=app_id,
        wm_class=wm_class,
        title=getattr(con, "name", "") or "",
        pid=getattr(con, "pid", None),
        type=WindowType.NORMAL,
        state=state,
        geometry=geom,
        monitor=monitor,
        desktop=desktop,
    )


__all__ = ["SwayBackend"]
