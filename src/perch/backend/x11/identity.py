"""Construct :class:`WindowInfo` snapshots from live X windows.

Separated from :mod:`perch.backend.x11.backend` so the sequencing and error
handling around the dozen property reads per window is legible, and so each
helper is easy to read in isolation. Everything here touches the display:
``get_wm_class``, ``get_full_property``, ``translate_coords``, and
``get_geometry`` are all :class:`ReplyRequest`s that raise
``Xlib.error.BadWindow`` / ``BadMatch`` *inline* when the target window has
been destroyed since we read ``_NET_CLIENT_LIST``.

The public entry point is :func:`read_window_info`. It returns ``None`` when
the window is gone, is ``override_redirect=True`` (tooltips, menus — not our
business), or is not yet fully mapped (``_NET_WM_STATE`` missing — the Steam
client reparent race documented in ``docs/04-backend-x11.md`` §Edge cases).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from Xlib import X as _X
from Xlib import error as _xerror

from perch.backend.types import (
    Geometry,
    OutputInfo,
    WindowInfo,
    WindowState,
    WindowType,
)

from .ewmh import (
    AtomTable,
    decode_text_property,
    derive_window_state,
    desktop_from_wire,
    map_window_type,
)
from .geometry import (
    monitor_for_geometry,
    translate_to_root,
)

if TYPE_CHECKING:
    from Xlib.display import Display
    from Xlib.xobject.drawable import Window

log = logging.getLogger(__name__)


# Errors that mean "window died between the _NET_CLIENT_LIST read and the
# property fetch." Any of these: skip the window and keep going.
_DEAD = (_xerror.BadWindow, _xerror.BadMatch, _xerror.BadDrawable)


def read_window_info(
    display: Display,
    atoms: AtomTable,
    window: Window,
    outputs: list[OutputInfo],
) -> WindowInfo | None:
    """Build a :class:`WindowInfo` for ``window`` or return ``None``.

    Order of operations is chosen so the cheap "do we even want this window?"
    filters (override_redirect, mapping state) run before the expensive
    property fetches.
    """
    # 1. Override-redirect filter — runs before any property reads because
    #    attribute fetch is cheap and a False here saves ~10 round-trips.
    try:
        attrs = window.get_attributes()
    except _DEAD as exc:
        # Routine: the window died between being listed and being read.
        log.debug("skipping window %s, attributes unreadable: %s", window.id, exc)
        return None
    if attrs.override_redirect:
        return None

    # 2. WM_CLASS / identity atoms. Dead windows get dropped.
    try:
        wm_class = window.get_wm_class()  # (instance, class) or None
    except _DEAD as exc:
        log.debug("skipping window %s, WM_CLASS unreadable: %s", window.id, exc)
        return None
    if wm_class is None:
        instance, klass = "", ""
    else:
        instance, klass = wm_class
    app_id = instance.lower()

    # 3. Title — prefer _NET_WM_NAME (UTF-8) over WM_NAME (Latin-1).
    title = _read_title(display, atoms, window)

    # 4. PID — optional.
    pid = _read_pid(atoms, window)

    # 5. Window type and state.
    wtype = _read_window_type(atoms, window)
    wstate = read_window_state(atoms, window)

    # 6. Role / parent (role is ICCCM WM_WINDOW_ROLE, parent is WM_TRANSIENT_FOR).
    role = _read_role(atoms, window)
    parent = _read_transient_for(window)

    # 7. Geometry — frame coords → client-area Geometry via _NET_FRAME_EXTENTS.
    geom = _read_client_geometry(display, atoms, window)
    if geom is None:
        return None

    # 8. Monitor-of-window + desktop.
    monitor = monitor_for_geometry(geom, outputs) or _primary_name(outputs)
    desktop = _read_desktop(atoms, window)

    return WindowInfo(
        id=str(window.id),
        app_id=app_id,
        wm_class=klass,
        title=title,
        pid=pid,
        type=wtype,
        state=wstate,
        geometry=geom,
        monitor=monitor if monitor is not None else "",
        desktop=desktop,
        parent=str(parent) if parent is not None else None,
        role=role,
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _read_title(display: Display, atoms: AtomTable, window: Window) -> str:
    try:
        prop = window.get_full_property(atoms["_NET_WM_NAME"], atoms["UTF8_STRING"])
    except _DEAD:
        return ""
    if prop is not None:
        return decode_text_property(prop.value, utf8=True)
    # Fall back to ICCCM WM_NAME (Latin-1).
    try:
        raw = window.get_wm_name()
    except _DEAD:
        return ""
    return decode_text_property(raw, utf8=False)


def _read_pid(atoms: AtomTable, window: Window) -> int | None:
    try:
        prop = window.get_full_property(atoms["_NET_WM_PID"], _X.AnyPropertyType)
    except _DEAD:
        return None
    if prop is None or prop.format != 32 or not prop.value:
        return None
    pid = int(prop.value[0])
    return pid if pid > 0 else None


def _read_window_type(atoms: AtomTable, window: Window) -> WindowType:
    try:
        prop = window.get_full_property(
            atoms["_NET_WM_WINDOW_TYPE"], _X.AnyPropertyType
        )
    except _DEAD:
        return WindowType.UNKNOWN
    if prop is None or prop.format != 32 or not prop.value:
        # EWMH §5.6: no _NET_WM_WINDOW_TYPE on a top-level window with
        # WM_TRANSIENT_FOR set means "dialog"; otherwise "normal". Perch
        # collapses the absent case to UNKNOWN and lets the rules engine's
        # own defaults kick in — the type field is advisory, not load-bearing.
        return WindowType.UNKNOWN
    names = atoms.names_for(int(a) for a in prop.value)
    return map_window_type(names)


def read_window_state(atoms: AtomTable, window: Window) -> WindowState:
    try:
        prop = window.get_full_property(
            atoms["_NET_WM_STATE"], _X.AnyPropertyType
        )
    except _DEAD:
        return WindowState.NORMAL
    if prop is None or prop.format != 32:
        return WindowState.NORMAL
    names = atoms.names_for(int(a) for a in prop.value)
    return derive_window_state(names)


def _read_role(atoms: AtomTable, window: Window) -> str:
    try:
        prop = window.get_full_property(atoms["WM_WINDOW_ROLE"], _X.AnyPropertyType)
    except _DEAD:
        return ""
    if prop is None:
        return ""
    return decode_text_property(prop.value, utf8=False)


def _read_transient_for(window: Window) -> int | None:
    try:
        transient = window.get_wm_transient_for()
    except (*_DEAD, AttributeError):
        # AttributeError: some python-xlib versions have omitted the shortcut.
        return None
    if transient is None:
        return None
    return int(transient.id)


def _read_client_geometry(
    display: Display, atoms: AtomTable, window: Window
) -> Geometry | None:
    """Compute the client-area rectangle in root coords or None on BadWindow.

    ``root.translate_coords(window, 0, 0)`` already returns the root-relative
    position of the *client* window's top-left (reparenting WMs don't fool
    TranslateCoordinates — it walks the window tree), and ``get_geometry``
    returns the client's own width / height. ``_NET_FRAME_EXTENTS`` is not
    subtracted: both inputs are already expressed in client-area terms, and
    applying extents on top would double-count the decoration offset.
    Smoke-verified against Openbox 3.6.1 during M4.e.
    """
    # atoms is reserved for a future FrameExtents-aware code path (e.g. when
    # the backend starts consuming the ConfigureNotify payload, whose x/y
    # fields *are* frame-relative). Silence the unused-arg warning for now.
    del atoms
    try:
        raw = window.get_geometry()
        root_x, root_y = translate_to_root(display, window)
    except _DEAD:
        return None
    return Geometry(root_x, root_y, int(raw.width), int(raw.height))


def _read_desktop(atoms: AtomTable, window: Window) -> int:
    try:
        prop = window.get_full_property(
            atoms["_NET_WM_DESKTOP"], _X.AnyPropertyType
        )
    except _DEAD:
        return 0
    if prop is None or prop.format != 32 or not prop.value:
        return 0
    return desktop_from_wire(int(prop.value[0]))


def _primary_name(outputs: list[OutputInfo]) -> str | None:
    """Fallback name when a window's geometry doesn't overlap any monitor."""
    for out in outputs:
        if out.is_primary and out.is_connected:
            return out.name
    for out in outputs:
        if out.is_connected:
            return out.name
    return None
