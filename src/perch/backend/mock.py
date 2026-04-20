"""In-memory backend used by the compliance suite, the rules-engine tests, and
higher-level reducer/integration tests.

The mock implements the full :class:`~perch.backend.base.WindowBackend`
contract, records every command so tests can assert on them, and exposes an
underscored test-driver API (``_spawn_window``, ``_move_window``,
``_fire_hotkey``, …) to poke events at the core without a live compositor.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .base import (
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
)
from .types import (
    Capabilities,
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
)

_DEFAULT_CAPABILITIES = Capabilities(
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
    notes="MockBackend — declares full capabilities by default.",
)


@dataclass
class _CommandLog:
    """Ordered log of every command the core invoked on the backend."""

    entries: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def record(self, name: str, *args: Any) -> None:
        self.entries.append((name, args))

    def clear(self) -> None:
        self.entries.clear()

    def names(self) -> list[str]:
        return [name for name, _ in self.entries]


class MockBackend(WindowBackend):
    """In-memory backend.

    Defaults to an empty world and full capabilities. Tests seed windows and
    outputs via the underscored driver API and flip capability bits via
    :meth:`set_capabilities` to exercise degraded paths.
    """

    def __init__(self) -> None:
        super().__init__()
        self._capabilities: Capabilities = _DEFAULT_CAPABILITIES
        self._windows: dict[WindowId, WindowInfo] = {}
        self._outputs: dict[OutputName, OutputInfo] = {}
        self._current_desktop: DesktopIndex = 0
        self._desktop_count: int = 1
        self._connected: bool = False
        self._set_state_raises: dict[WindowState, type[BackendUnsupported]] = {}
        self.commands: _CommandLog = _CommandLog()
        self.hotkeys: dict[str, str] = {}  # callback_id → accel

    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        self._connected = False
        self.backend_disconnected.emit("mock stop")

    @property
    def capabilities(self) -> Capabilities:
        return self._capabilities

    def set_capabilities(self, caps: Capabilities) -> None:
        """Test hook — flip capabilities mid-test (e.g. drop ``can_set_desktop``)."""
        self._capabilities = caps

    # ── Queries ─────────────────────────────────────────────────────────────
    async def list_windows(self) -> list[WindowInfo]:
        return list(self._windows.values())

    async def get_window(self, wid: WindowId) -> WindowInfo:
        try:
            return self._windows[wid]
        except KeyError:
            raise UnknownWindow(f"no window with id {wid!r}") from None

    async def list_outputs(self) -> list[OutputInfo]:
        return list(self._outputs.values())

    async def current_desktop(self) -> DesktopIndex:
        return self._current_desktop

    async def desktop_count(self) -> int:
        return self._desktop_count

    # ── Commands ────────────────────────────────────────────────────────────
    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        self.commands.record("set_geometry", wid, geom, monitor, desktop)

        caps = self._capabilities
        if (
            (not caps.can_set_position or not caps.can_set_size)
            or (monitor is not None and not caps.can_set_monitor)
            or (desktop is not None and not caps.can_set_desktop)
        ):
            raise BackendUnsupported(
                "set_geometry: missing capability for requested fields"
            )

        if wid not in self._windows:
            raise UnknownWindow(f"no window with id {wid!r}")
        if monitor is not None and monitor not in self._outputs:
            raise UnknownOutput(f"no output named {monitor!r}")

        current = self._windows[wid]
        new_monitor = monitor if monitor is not None else current.monitor
        new_desktop = desktop if desktop is not None else current.desktop
        updated = replace(
            current, geometry=geom, monitor=new_monitor, desktop=new_desktop
        )
        self._windows[wid] = updated
        self.geometry_changed.emit(wid, geom, new_monitor, new_desktop)

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        self.commands.record("set_state", wid, state)
        if not self._capabilities.can_set_state:
            raise BackendUnsupported("set_state: can_set_state is False")
        if wid not in self._windows:
            raise UnknownWindow(f"no window with id {wid!r}")
        exc = self._set_state_raises.get(state)
        if exc is not None:
            raise exc(f"set_state({state!s}): unsupported on this backend")
        updated = replace(self._windows[wid], state=state)
        self._windows[wid] = updated
        self.window_changed.emit(updated)

    async def close_window(self, wid: WindowId) -> None:
        self.commands.record("close_window", wid)
        if wid not in self._windows:
            raise UnknownWindow(f"no window with id {wid!r}")
        self._fire_close(wid)

    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        self.commands.record("register_hotkey", accel, callback_id)
        if not self._capabilities.can_register_hotkeys:
            raise BackendUnsupported("register_hotkey: can_register_hotkeys is False")
        self.hotkeys[callback_id] = accel

    async def unregister_hotkey(self, callback_id: str) -> None:
        self.commands.record("unregister_hotkey", callback_id)
        self.hotkeys.pop(callback_id, None)

    # ── Test-driver API (not part of WindowBackend) ─────────────────────────
    def _spawn_window(self, info: WindowInfo) -> None:
        """Simulate a window appearing. Emits ``window_opened``."""
        if info.id in self._windows:
            raise ValueError(f"window {info.id!r} already present")
        self._windows[info.id] = info
        self.window_opened.emit(info)

    def _change_window(self, info: WindowInfo) -> None:
        """Simulate a title/type/state change. Emits ``window_changed``."""
        if info.id not in self._windows:
            raise ValueError(f"window {info.id!r} not present")
        self._windows[info.id] = info
        self.window_changed.emit(info)

    def _move_window(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        """Simulate a user drag-resize. Emits ``geometry_changed``.

        Unlike :meth:`set_geometry` this is not a command (nothing is recorded
        in :attr:`commands`); it models the compositor reporting a geometry
        change that did not originate from Perch.
        """
        if wid not in self._windows:
            raise ValueError(f"window {wid!r} not present")
        current = self._windows[wid]
        new_monitor = monitor if monitor is not None else current.monitor
        new_desktop = desktop if desktop is not None else current.desktop
        self._windows[wid] = replace(
            current, geometry=geom, monitor=new_monitor, desktop=new_desktop
        )
        self.geometry_changed.emit(wid, geom, new_monitor, new_desktop)

    def _fire_close(self, wid: WindowId) -> None:
        """Simulate the window going away. Emits ``window_closed``."""
        self._windows.pop(wid, None)
        self.window_closed.emit(wid)

    def _add_output(self, info: OutputInfo) -> None:
        if info.name in self._outputs:
            raise ValueError(f"output {info.name!r} already present")
        self._outputs[info.name] = info
        self.output_added.emit(info)

    def _change_output(self, info: OutputInfo) -> None:
        if info.name not in self._outputs:
            raise ValueError(f"output {info.name!r} not present")
        self._outputs[info.name] = info
        self.output_changed.emit(info)

    def _remove_output(self, name: OutputName) -> None:
        if name not in self._outputs:
            raise ValueError(f"output {name!r} not present")
        del self._outputs[name]
        self.output_removed.emit(name)

    def _set_desktop(self, index: DesktopIndex, count: int | None = None) -> None:
        self._current_desktop = index
        if count is not None:
            self._desktop_count = count

    def _fire_hotkey(self, callback_id: str) -> None:
        self.hotkey_fired.emit(callback_id)

    def _fail_state(
        self,
        state: WindowState,
        exc: type[BackendUnsupported] = BackendUnsupported,
    ) -> None:
        """Arrange for the next ``set_state(..., state)`` to raise.

        Models Sway/Hyprland rejecting ``MAXIMIZED`` — see
        ``docs/06-backend-stubs.md``.
        """
        self._set_state_raises[state] = exc

    def _clear_fail_state(self, state: WindowState) -> None:
        self._set_state_raises.pop(state, None)
