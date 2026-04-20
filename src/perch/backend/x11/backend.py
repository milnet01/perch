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
from typing import TYPE_CHECKING

from Xlib import X as _X
from Xlib import display as _display
from Xlib import error as _xerror

from perch.backend.base import (
    BackendDisconnected,
    BackendUnavailable,
    BackendUnsupported,
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

from .ewmh import AtomTable, desktop_from_wire
from .outputs import apply_workarea, list_outputs

if TYPE_CHECKING:
    from Xlib.display import Display

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
        # Subscribe to the root-level changes we care about for output +
        # desktop + client-list tracking. Per-window subscriptions (for
        # window_changed / geometry_changed) are set up in M4.c/d.
        root = self._d.screen().root
        try:
            root.change_attributes(
                event_mask=_X.SubstructureNotifyMask | _X.PropertyChangeMask
            )
            self._d.flush()
        except _xerror.BadAccess as exc:
            # Another client already has SubstructureRedirectMask — harmless
            # for us (we never ask for Redirect), but BadAccess is still
            # reportable.
            raise BackendDisconnected(
                f"cannot subscribe to root events: {exc!s}"
            ) from exc

        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False
        if self._d is not None:
            # Display.close() can raise OSError on a socket already torn down
            # by the server (pathological shutdown race). Nothing actionable;
            # stop() must not throw during app shutdown.
            with contextlib.suppress(OSError):
                self._d.close()
            self._d = None
        self._atoms = None
        self.backend_disconnected.emit("x11 stop")

    @property
    def capabilities(self) -> Capabilities:
        return _X11_CAPABILITIES

    # ── Queries ─────────────────────────────────────────────────────────────
    async def list_windows(self) -> list[WindowInfo]:
        # Full enumeration lands in M4.c.
        self._require_connected()
        return []

    async def get_window(self, wid: WindowId) -> WindowInfo:
        # Until M4.c populates the window table, every lookup is a miss.
        raise UnknownWindow(f"no window with id {wid!r}")

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
        # M4.e will implement _NET_MOVERESIZE_WINDOW dispatch here.
        raise BackendUnsupported(
            "X11Backend.set_geometry lands in M4.e; no WindowId is yet tracked"
        )

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        raise BackendUnsupported(
            "X11Backend.set_state lands in M4.e; no WindowId is yet tracked"
        )

    async def close_window(self, wid: WindowId) -> None:
        raise BackendUnsupported(
            "X11Backend.close_window lands in M4.e; no WindowId is yet tracked"
        )

    # ── Hotkeys (optional) ─────────────────────────────────────────────────
    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        raise BackendUnsupported("X11Backend.register_hotkey lands in M4.f")

    async def unregister_hotkey(self, callback_id: str) -> None:
        raise BackendUnsupported("X11Backend.unregister_hotkey lands in M4.f")

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
