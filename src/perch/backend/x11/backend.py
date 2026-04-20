"""``X11Backend`` — the concrete :class:`WindowBackend` for any EWMH-compliant WM.

This is a progressive build-out. M4.b lands the skeleton: transport lifecycle
(``start`` / ``stop`` via :class:`Xlib.display.Display`), :data:`Capabilities`
declaration matching ``docs/04-backend-x11.md``, :meth:`list_outputs` via
XRandR, and the EWMH root queries for the current desktop / desktop count.

Window enumeration, identity extraction, the event loop, commands
(``set_geometry`` / ``set_state`` / ``close_window``), and hotkey registration
arrive in M4.c..M4.f. Until those land they return empty lists or raise
:class:`BackendUnsupported`; the compliance suite's skip-on-capability rule
means most of its tests will skip rather than fail, but the shape of
``X11Backend`` is already correct and the suite can be extended as features
land.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSocketNotifier, Qt, QTimer
from Xlib import X as _X
from Xlib import display as _display
from Xlib import error as _xerror

from perch.backend.base import (
    BackendDisconnected,
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

from .ewmh import (
    WM_STATE_ADD,
    WM_STATE_REMOVE,
    AtomTable,
    build_change_state_message,
    build_close_message,
    build_moveresize_message,
    build_wm_desktop_message,
    build_wm_state_message,
    desktop_from_wire,
    desktop_to_wire,
)
from .identity import read_window_info
from .outputs import apply_workarea, list_outputs

if TYPE_CHECKING:
    from Xlib.display import Display
    from Xlib.xobject.drawable import Window

_X11_CAPABILITIES = Capabilities(
    can_set_position=True,
    can_set_size=True,
    can_set_monitor=True,  # via coordinate math; no dedicated API
    can_set_desktop=True,
    can_set_state=True,
    can_enumerate_windows=True,
    can_observe_geometry=True,
    can_observe_outputs=True,
    can_register_hotkeys=True,
    can_preplace_windows=False,  # X11 has no pre-map placement primitive
    notes=(
        "X11/EWMH via python-xlib + in-tree EWMH helper. "
        "override_redirect windows are ignored. "
        "i3 tiled windows ignore geometry writes; Perch skips them."
    ),
)


class X11Backend(WindowBackend):
    """EWMH-compliant backend.

    Single ``Display`` connection; no threads. All methods are async on the
    interface but synchronous in effect — the work they do is fast enough to
    run on the event loop without a thread pool. Errors from ``python-xlib``
    (``BadWindow``, ``BadMatch``, ``BadAccess``) are normalised to the
    :mod:`perch.backend` error taxonomy at the boundary.
    """

    def __init__(self, display_name: str | None = None) -> None:
        super().__init__()
        # ``display_name`` is ``None`` for $DISPLAY; tests pass an explicit
        # ":NN" against an Xvfb instance.
        self._display_name: str | None = display_name
        self._d: Display | None = None
        self._atoms: AtomTable | None = None
        self._connected: bool = False
        # WindowId string → Xlib Window handle. Populated during enumeration
        # and used by every command that targets a specific window. IDs are
        # the int X resource cast to str to keep the interface type stable
        # (OutputName/WindowId are both ``str``).
        self._windows: dict[WindowId, Window] = {}
        # Cached last-seen info per window so PropertyNotify / ConfigureNotify
        # can decide "was this a *real* change?" without re-querying every
        # property. Saves about 6 round-trips per ConfigureNotify event.
        self._info_cache: dict[WindowId, WindowInfo] = {}
        # Cached output snapshot so we can diff on RRScreenChangeNotify.
        self._outputs_cache: dict[OutputName, OutputInfo] = {}
        # The QSocketNotifier that wakes us on readable X11 socket data.
        self._notifier: QSocketNotifier | None = None
        # Debounce timer for XRandR events — a single hot-plug typically fires
        # RRScreenChangeNotify + several RRCrtcChangeNotify + RROutputChange
        # within ~50 ms; we coalesce into one output-diff pass after 200 ms
        # quiet (matches the doc).
        self._randr_debounce: QTimer | None = None
        # RandR extension-event codes, populated after init_extension('RANDR').
        self._rr_screen_change: int | None = None
        self._rr_crtc_change: int | None = None
        self._rr_output_change: int | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._connected:
            return
        try:
            self._d = _display.Display(self._display_name)
        except (
            _xerror.DisplayError,
            ConnectionError,
            OSError,
            OverflowError,
        ) as exc:
            # DisplayNameError / DisplayConnectionError both subclass
            # Xlib.error.DisplayError; OSError covers "no such file" when the
            # X socket is missing entirely; OverflowError surfaces when a
            # malformed display number overflows python-xlib's TCP-port math
            # (``:99999`` → port 105999, which does not fit). All three mean
            # "no usable transport." BackendUnavailable is the public surface
            # the core watches for to trigger the UI-only fallback path
            # (see docs/03-backend-interface.md §Backend selection).
            raise BackendUnavailable(f"cannot open display: {exc!s}") from exc

        self._atoms = AtomTable(self._d)
        # Subscribe to the root-level changes: SubstructureNotify for window
        # lifecycle (Create/Map/Unmap/Destroy reparented under root),
        # PropertyChange for _NET_CLIENT_LIST / _NET_CURRENT_DESKTOP /
        # _NET_NUMBER_OF_DESKTOPS / _NET_WORKAREA updates.
        root = self._d.screen().root
        try:
            root.change_attributes(
                event_mask=_X.SubstructureNotifyMask | _X.PropertyChangeMask
            )
        except _xerror.BadAccess as exc:
            raise BackendDisconnected(
                f"cannot subscribe to root events: {exc!s}"
            ) from exc

        # Subscribe to RandR events. init_extension assigns the extension-
        # event codes into d.extension_event.* (they are not static).
        self._init_randr_subscription()

        self._d.flush()

        # Wire Qt's event loop to the X socket. _drain() pumps every event
        # that's readable — level-triggered QSocketNotifier can fire once per
        # readable wakeup and we cover multiple queued events.
        self._notifier = QSocketNotifier(
            self._d.fileno(), QSocketNotifier.Type.Read
        )
        self._notifier.activated.connect(self._on_socket_readable)

        # Debounce timer for XRandR — single-shot, re-armed on each event.
        self._randr_debounce = QTimer()
        self._randr_debounce.setSingleShot(True)
        self._randr_debounce.setInterval(200)
        self._randr_debounce.setTimerType(Qt.TimerType.CoarseTimer)
        self._randr_debounce.timeout.connect(self._on_randr_debounce_fired)

        self._connected = True
        # Prime the caches so the first live event can diff against something.
        infos = await self.list_windows()
        self._info_cache = {i.id: i for i in infos}
        outs = await self.list_outputs()
        self._outputs_cache = {o.name: o for o in outs}
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self._randr_debounce is not None:
            self._randr_debounce.stop()
            self._randr_debounce.deleteLater()
            self._randr_debounce = None
        if self._d is not None:
            # Display.close() can raise OSError on a socket already torn down
            # by the server (pathological shutdown race). Nothing actionable;
            # stop() must not throw during app shutdown.
            with contextlib.suppress(OSError):
                self._d.close()
            self._d = None
        self._atoms = None
        self._info_cache.clear()
        self._outputs_cache.clear()
        self.backend_disconnected.emit("x11 stop")

    @property
    def capabilities(self) -> Capabilities:
        return _X11_CAPABILITIES

    # ── Queries ─────────────────────────────────────────────────────────────
    async def list_windows(self) -> list[WindowInfo]:
        d = self._require_connected()
        atoms = self._require_atoms()
        outputs = await self.list_outputs()

        # _NET_CLIENT_LIST is a WINDOW[] CARDINAL/32 on root.
        root = d.screen().root
        try:
            prop = root.get_full_property(atoms["_NET_CLIENT_LIST"], _X.AnyPropertyType)
        except _xerror.BadWindow:
            # Only possible if the root window itself was destroyed, which
            # would be a session exit — let the error bubble through stop().
            return []
        if prop is None or prop.format != 32 or not prop.value:
            self._windows.clear()
            return []

        seen: set[str] = set()
        infos: list[WindowInfo] = []
        new_table: dict[WindowId, Window] = {}
        for wid_int in prop.value:
            wid_int = int(wid_int)
            win = d.create_resource_object("window", wid_int)
            info = read_window_info(d, atoms, win, outputs)
            if info is None:
                continue
            wid_str = str(wid_int)
            seen.add(wid_str)
            new_table[wid_str] = win
            infos.append(info)

            # Subscribe to property changes so we get updates for this window.
            catch = _xerror.CatchError(_xerror.BadWindow, _xerror.BadMatch)
            win.change_attributes(
                event_mask=_X.PropertyChangeMask | _X.StructureNotifyMask,
                onerror=catch,
            )
        d.flush()

        self._windows = new_table
        return infos

    async def get_window(self, wid: WindowId) -> WindowInfo:
        d = self._require_connected()
        atoms = self._require_atoms()
        win = self._windows.get(wid)
        if win is None:
            raise UnknownWindow(f"no window with id {wid!r}")
        outputs = await self.list_outputs()
        info = read_window_info(d, atoms, win, outputs)
        if info is None:
            # Window died between list_windows() and get_window(). Drop the
            # stale handle so the next caller gets a clean miss.
            self._windows.pop(wid, None)
            raise UnknownWindow(f"window {wid!r} no longer exists")
        return info

    async def list_outputs(self) -> list[OutputInfo]:
        d = self._require_connected()
        outputs = list_outputs(d)
        workarea = self._read_workarea()
        if workarea is not None:
            outputs = apply_workarea(outputs, workarea)
        return outputs

    async def current_desktop(self) -> DesktopIndex:
        d = self._require_connected()
        atoms = self._require_atoms()
        root = d.screen().root
        prop = root.get_full_property(atoms["_NET_CURRENT_DESKTOP"], _X.AnyPropertyType)
        if prop is None or prop.format != 32 or not prop.value:
            return 0
        return desktop_from_wire(int(prop.value[0]))

    async def desktop_count(self) -> int:
        d = self._require_connected()
        atoms = self._require_atoms()
        root = d.screen().root
        prop = root.get_full_property(atoms["_NET_NUMBER_OF_DESKTOPS"], _X.AnyPropertyType)
        if prop is None or prop.format != 32 or not prop.value:
            return 1
        return int(prop.value[0])

    # ── Commands ───────────────────────────────────────────────────────────
    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        d = self._require_connected()
        atoms = self._require_atoms()
        win = self._windows.get(wid)
        if win is None:
            raise UnknownWindow(f"no window with id {wid!r}")

        # Monitor parameter: translate the requested (x, y) into root-absolute
        # coords by adding the output's origin. Then validate the output is
        # known. The X11 backend has no native "move to output N" primitive —
        # the geometry offset is how every EWMH tool does it.
        target_x = geom.x
        target_y = geom.y
        if monitor is not None:
            out = self._outputs_cache.get(monitor)
            if out is None:
                raise UnknownOutput(f"no output named {monitor!r}")
            target_x = out.geometry.x + geom.x
            target_y = out.geometry.y + geom.y

        # Send the client message routed through the WM for correct
        # decoration-aware placement (StaticGravity → client-area coords).
        msg = build_moveresize_message(
            win, atoms, target_x, target_y, geom.w, geom.h
        )
        root = d.screen().root
        root.send_event(
            msg,
            event_mask=_X.SubstructureRedirectMask | _X.SubstructureNotifyMask,
        )

        # Move to the requested desktop in the same batch so pager-style
        # "send to desktop N and place at (x, y)" moves land atomically from
        # the user's perspective.
        if desktop is not None:
            desk_msg = build_wm_desktop_message(
                win, atoms, desktop_to_wire(desktop)
            )
            root.send_event(
                desk_msg,
                event_mask=_X.SubstructureRedirectMask
                | _X.SubstructureNotifyMask,
            )

        d.flush()

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        d = self._require_connected()
        atoms = self._require_atoms()
        win = self._windows.get(wid)
        if win is None:
            raise UnknownWindow(f"no window with id {wid!r}")

        root = d.screen().root
        ev_mask = _X.SubstructureRedirectMask | _X.SubstructureNotifyMask

        if state is WindowState.MINIMIZED:
            # ICCCM: WM_CHANGE_STATE client message with IconicState=3 is the
            # wire-level equivalent of libX11's XIconifyWindow.
            root.send_event(build_change_state_message(win, atoms), event_mask=ev_mask)
            d.flush()
            return

        # Compute the add/remove pairs against the standard triple (MAXIMIZED_*,
        # FULLSCREEN). This keeps transitions idempotent: going NORMAL from
        # any state clears every sticky bit.
        fs = atoms["_NET_WM_STATE_FULLSCREEN"]
        mh = atoms["_NET_WM_STATE_MAXIMIZED_HORZ"]
        mv = atoms["_NET_WM_STATE_MAXIMIZED_VERT"]

        if state is WindowState.FULLSCREEN:
            msg = build_wm_state_message(win, atoms, WM_STATE_ADD, fs)
            root.send_event(msg, event_mask=ev_mask)
            # Clear any lingering maximised state so the transition is clean.
            root.send_event(
                build_wm_state_message(win, atoms, WM_STATE_REMOVE, mh, mv),
                event_mask=ev_mask,
            )
        elif state is WindowState.MAXIMIZED:
            root.send_event(
                build_wm_state_message(win, atoms, WM_STATE_ADD, mh, mv),
                event_mask=ev_mask,
            )
            root.send_event(
                build_wm_state_message(win, atoms, WM_STATE_REMOVE, fs),
                event_mask=ev_mask,
            )
        elif state is WindowState.NORMAL:
            # Remove everything.
            root.send_event(
                build_wm_state_message(win, atoms, WM_STATE_REMOVE, mh, mv),
                event_mask=ev_mask,
            )
            root.send_event(
                build_wm_state_message(win, atoms, WM_STATE_REMOVE, fs),
                event_mask=ev_mask,
            )
        else:
            raise BackendUnsupported(f"unknown WindowState: {state!r}")
        d.flush()

    async def close_window(self, wid: WindowId) -> None:
        d = self._require_connected()
        atoms = self._require_atoms()
        win = self._windows.get(wid)
        if win is None:
            raise UnknownWindow(f"no window with id {wid!r}")

        # If the window advertises WM_DELETE_WINDOW in WM_PROTOCOLS, the
        # polite path is an ICCCM client message. Otherwise fall back to a
        # hard kill.
        if self._supports_delete_protocol(win, atoms):
            # Send directly to the target window (not routed through root).
            msg = build_close_message(win, atoms)
            win.send_event(msg, event_mask=0, propagate=False)
        else:
            # XKillClient — the last-resort abrupt close. python-xlib exposes
            # this as display.kill_client(resource). Matches what xkill does.
            d.kill_client(win)
        d.flush()

    def _supports_delete_protocol(
        self, win: Window, atoms: AtomTable
    ) -> bool:
        try:
            prop = win.get_full_property(atoms["WM_PROTOCOLS"], _X.AnyPropertyType)
        except (_xerror.BadWindow, _xerror.BadMatch):
            return False
        if prop is None or prop.format != 32:
            return False
        delete_atom = atoms["WM_DELETE_WINDOW"]
        return any(int(a) == delete_atom for a in prop.value)

    # ── Hotkeys (optional) ─────────────────────────────────────────────────
    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        raise BackendUnsupported("X11Backend.register_hotkey lands in M4.f")

    async def unregister_hotkey(self, callback_id: str) -> None:
        raise BackendUnsupported("X11Backend.unregister_hotkey lands in M4.f")

    # ── Event loop ─────────────────────────────────────────────────────────
    def _init_randr_subscription(self) -> None:
        """Select RandR events on the root and remember their event codes."""
        from Xlib.ext import randr

        d = self._d
        if d is None:
            return
        root = d.screen().root
        try:
            root.xrandr_select_input(
                randr.RRScreenChangeNotifyMask
                | randr.RRCrtcChangeNotifyMask
                | randr.RROutputChangeNotifyMask
            )
        except _xerror.BadAccess:
            # No RandR on this server. Degrade gracefully — can_observe_outputs
            # still holds for the static enumeration; hot-plug is simply blind.
            return
        # Xlib assigns extension-event codes during init_extension('RANDR'),
        # accessed via the dynamic d.extension_event namespace.
        ee = d.extension_event
        self._rr_screen_change = getattr(ee, "ScreenChangeNotify", None)
        self._rr_crtc_change = getattr(ee, "CrtcChangeNotify", None)
        self._rr_output_change = getattr(ee, "OutputChangeNotify", None)

    def _on_socket_readable(self, _fd: int) -> None:
        """QSocketNotifier slot: drain every queued X event."""
        d = self._d
        if d is None:
            return
        try:
            while d.pending_events():
                event = d.next_event()
                self._dispatch(event)
        except (_xerror.ConnectionClosedError, OSError) as exc:
            # The X server went away mid-drain — stop the backend cleanly.
            self._connected = False
            self.backend_disconnected.emit(f"x11 disconnected: {exc!s}")

    def _dispatch(self, event: Any) -> None:
        """Route an X event to the matching handler."""
        etype = event.type
        # RandR extension events (codes assigned at init time).
        if etype == self._rr_screen_change:
            self._on_randr_event()
            return
        if etype == self._rr_crtc_change or etype == self._rr_output_change:
            self._on_randr_event()
            return
        if etype == _X.PropertyNotify:
            self._on_property_notify(event)
            return
        if etype == _X.ConfigureNotify:
            self._on_configure_notify(event)
            return
        if etype == _X.UnmapNotify or etype == _X.DestroyNotify:
            self._on_window_gone(event)
            return
        # MapNotify intentionally not handled — EWMH WMs emit
        # PropertyNotify(_NET_CLIENT_LIST) as soon as a window is fully
        # managed, and our reconcile runs off that. Wiring MapNotify as a
        # parallel trigger fires window_opened too early (before WM_CLASS /
        # _NET_WM_STATE are set), producing spurious "empty app_id" events
        # followed by a correction — verified against Openbox 3.6.1.
        #
        # Everything else (FocusIn/Out, Visibility, KeyPress when no hotkey
        # is grabbed, …) is not our concern.

    def _on_randr_event(self) -> None:
        if self._randr_debounce is not None:
            self._randr_debounce.start()

    def _on_randr_debounce_fired(self) -> None:
        """Refresh outputs and emit add/remove/change signals for the diff."""
        if not self._connected:
            return
        # Build a fresh snapshot.
        try:
            outs = list_outputs(self._d) if self._d is not None else []
        except _xerror.XError:
            # RandR request failed mid-run; leave the cache alone.
            return
        workarea = self._read_workarea()
        if workarea is not None:
            outs = apply_workarea(outs, workarea)
        new = {o.name: o for o in outs}
        old = self._outputs_cache
        # Diff.
        for name, info in new.items():
            if name not in old:
                self.output_added.emit(info)
            elif info != old[name]:
                self.output_changed.emit(info)
        for name in old:
            if name not in new:
                self.output_removed.emit(name)
        self._outputs_cache = new

    def _on_property_notify(self, event: Any) -> None:
        """Handle PropertyNotify: root-level client-list / desktop changes,
        or per-window title / state / type updates."""
        d = self._d
        atoms = self._atoms
        if d is None or atoms is None:
            return
        root = d.screen().root
        if event.window.id == root.id:
            self._on_root_property_change(event.atom)
            return
        # Per-window property changes — re-read identity and emit
        # window_changed if anything visible has changed.
        wid_str = str(event.window.id)
        win = self._windows.get(wid_str)
        if win is None:
            return
        outputs = list(self._outputs_cache.values())
        info = read_window_info(d, atoms, win, outputs)
        if info is None:
            # Window died; clean up and emit closed.
            self._drop_window(wid_str)
            return
        cached = self._info_cache.get(wid_str)
        if cached != info:
            self._info_cache[wid_str] = info
            self.window_changed.emit(info)

    def _on_root_property_change(self, atom: int) -> None:
        atoms = self._atoms
        if atoms is None:
            return
        # Only reconcile on atoms we care about; ignore others to save work.
        if atom == atoms["_NET_CLIENT_LIST"]:
            # Reconcile is synchronous and fast (one property read + a small
            # diff). Running it inline keeps the event-dispatch ordering
            # deterministic: window_closed fires before any window_opened
            # from the same _NET_CLIENT_LIST update.
            self._reconcile_client_list()

    def _reconcile_client_list(self) -> None:
        """Read _NET_CLIENT_LIST, diff against cached windows, emit signals."""
        d = self._d
        atoms = self._atoms
        if d is None or atoms is None:
            return
        root = d.screen().root
        try:
            prop = root.get_full_property(
                atoms["_NET_CLIENT_LIST"], _X.AnyPropertyType
            )
        except _xerror.XError:
            return
        now_ids = (
            [int(v) for v in prop.value] if prop is not None and prop.format == 32 else []
        )
        now_str = {str(i) for i in now_ids}
        outputs = list(self._outputs_cache.values())

        # Gone first so the event ordering matches the docs (closed is terminal).
        for wid in list(self._info_cache):
            if wid not in now_str:
                self._drop_window(wid)

        # New arrivals.
        for wid_int in now_ids:
            wid_str = str(wid_int)
            if wid_str in self._info_cache:
                continue
            win = d.create_resource_object("window", wid_int)
            info = read_window_info(d, atoms, win, outputs)
            if info is None:
                continue
            self._windows[wid_str] = win
            self._info_cache[wid_str] = info
            catch = _xerror.CatchError(_xerror.BadWindow, _xerror.BadMatch)
            win.change_attributes(
                event_mask=_X.PropertyChangeMask | _X.StructureNotifyMask,
                onerror=catch,
            )
            self.window_opened.emit(info)
        d.flush()

    def _on_configure_notify(self, event: Any) -> None:
        """Geometry change reported by the server."""
        wid_str = str(event.window.id)
        win = self._windows.get(wid_str)
        d = self._d
        atoms = self._atoms
        if win is None or d is None or atoms is None:
            return
        outputs = list(self._outputs_cache.values())
        info = read_window_info(d, atoms, win, outputs)
        if info is None:
            self._drop_window(wid_str)
            return
        cached = self._info_cache.get(wid_str)
        changed = (
            cached is None
            or cached.geometry != info.geometry
            or cached.monitor != info.monitor
            or cached.desktop != info.desktop
        )
        if changed:
            self._info_cache[wid_str] = info
            self.geometry_changed.emit(
                info.id, info.geometry, info.monitor, info.desktop
            )

    def _on_window_gone(self, event: Any) -> None:
        wid_str = str(event.window.id)
        if wid_str in self._info_cache:
            self._drop_window(wid_str)

    def _drop_window(self, wid: WindowId) -> None:
        self._windows.pop(wid, None)
        self._info_cache.pop(wid, None)
        self.window_closed.emit(wid)

    # ── Internals ──────────────────────────────────────────────────────────
    def _require_connected(self) -> Display:
        if not self._connected or self._d is None:
            raise BackendDisconnected("X11Backend.start() has not been called")
        return self._d

    def _require_atoms(self) -> AtomTable:
        if self._atoms is None:
            raise BackendDisconnected("X11Backend.start() has not been called")
        return self._atoms

    def _read_workarea(self) -> Geometry | None:
        """Read ``_NET_WORKAREA`` and return the current desktop's rect.

        Returns ``None`` when the WM does not advertise a workarea (Openbox
        in its default config does; i3 notably does not). Callers fall back
        to each output's full geometry.
        """
        d = self._d
        atoms = self._atoms
        if d is None or atoms is None:
            return None
        root = d.screen().root
        prop = root.get_full_property(atoms["_NET_WORKAREA"], _X.AnyPropertyType)
        if prop is None or prop.format != 32 or len(prop.value) < 4:
            return None
        # _NET_WORKAREA is (x, y, w, h) per desktop. We read the current
        # desktop's slice — most EWMH WMs don't vary it per desktop in
        # practice, but the spec allows it.
        cur = 0
        cur_prop = root.get_full_property(
            atoms["_NET_CURRENT_DESKTOP"], _X.AnyPropertyType
        )
        if cur_prop is not None and cur_prop.format == 32 and cur_prop.value:
            cur = int(cur_prop.value[0])
        base = cur * 4
        if base + 4 > len(prop.value):
            base = 0
        x, y, w, h = (int(v) for v in prop.value[base : base + 4])
        return Geometry(x, y, w, h)
