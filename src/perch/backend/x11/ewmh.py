"""EWMH helper: atoms, client-message builders, and property → core-type mappers.

This module is the *protocol* layer of the X11 backend — it knows about
freedesktop wm-spec 1.5 and ICCCM, but nothing about Perch's event loop, Qt,
or async. Every helper here is pure or only touches a :class:`Xlib.display.Display`
that the caller owns. This keeps ``pytest`` able to exercise the protocol math
(bit layouts, priority ordering, enum mapping) without spinning up Xvfb.

Design reference: ``docs/04-backend-x11.md``.

Phase 2.5 research and the M4 follow-up pass (``docs/11-roadmap.md``) pinned
the following wire-format details, which are implemented here verbatim:

- ``_NET_MOVERESIZE_WINDOW`` — bits 0..7 gravity, 8..11 x/y/w/h presence,
  12..15 source indication. Perch uses ``StaticGravity (10)`` + ``source = 2``
  (pager/taskbar — same choice as ``wmctrl`` and ``libwnck``).
- ``_NET_WM_STATE`` — ``l[3]`` is the source indication; ``l[0]`` action is
  one of REMOVE/ADD/TOGGLE.
- Minimize is *not* ``XIconifyWindow`` (``python-xlib`` 0.33 has no such
  wrapper) — it is an ICCCM ``WM_CHANGE_STATE`` client message with
  ``IconicState = 3``. That's what ``libX11``'s ``XIconifyWindow`` emits.
- ``_NET_WM_STATE`` priority for :class:`WindowState`:
  fullscreen > maximised > hidden/iconic > normal.
- ``_NET_WM_WINDOW_TYPE`` — the *first* recognised atom wins; anything else
  falls through to :data:`~perch.backend.types.WindowType.UNKNOWN`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from perch.backend.types import WindowState, WindowType

if TYPE_CHECKING:
    from Xlib.display import Display
    from Xlib.protocol.event import ClientMessage
    from Xlib.xobject.drawable import Window


# ── Source indications (wm-spec §1.7) ──────────────────────────────────────

SOURCE_UNSPECIFIED = 0
SOURCE_APPLICATION = 1
SOURCE_PAGER = 2
"""Perch is neither the owning app nor the WM itself; "pager/taskbar" is the
correct indication for third-party tools that issue window-management
requests on behalf of the user."""


# ── _NET_MOVERESIZE_WINDOW packing ─────────────────────────────────────────

STATIC_GRAVITY = 10

_PRESENCE_X = 1 << 8
_PRESENCE_Y = 1 << 9
_PRESENCE_W = 1 << 10
_PRESENCE_H = 1 << 11
PRESENCE_ALL = _PRESENCE_X | _PRESENCE_Y | _PRESENCE_W | _PRESENCE_H


def moveresize_flags(
    *,
    gravity: int = STATIC_GRAVITY,
    source: int = SOURCE_PAGER,
    x: bool = True,
    y: bool = True,
    w: bool = True,
    h: bool = True,
) -> int:
    """Pack the ``data.l[0]`` word for a ``_NET_MOVERESIZE_WINDOW`` message.

    Layout: bits 0..7 = gravity, 8..11 = x/y/w/h presence, 12..15 = source.
    Bits 16..31 must stay zero.

    Raises :class:`ValueError` if ``gravity`` or ``source`` don't fit.
    """
    if not 0 <= gravity <= 0xFF:
        raise ValueError(f"gravity {gravity!r} does not fit in 8 bits")
    if not 0 <= source <= 0xF:
        raise ValueError(f"source {source!r} does not fit in 4 bits")
    flags = gravity & 0xFF
    if x:
        flags |= _PRESENCE_X
    if y:
        flags |= _PRESENCE_Y
    if w:
        flags |= _PRESENCE_W
    if h:
        flags |= _PRESENCE_H
    flags |= (source & 0xF) << 12
    return flags


# ── _NET_WM_STATE action codes (wm-spec §5.7) ──────────────────────────────

WM_STATE_REMOVE = 0
WM_STATE_ADD = 1
WM_STATE_TOGGLE = 2


# ── ICCCM WM_CHANGE_STATE (Xutil.h) ────────────────────────────────────────

ICCCM_WITHDRAWN_STATE = 0
ICCCM_NORMAL_STATE = 1
ICCCM_ICONIC_STATE = 3


# ── WindowType mapping (wm-spec §5.6) ──────────────────────────────────────

_WINDOW_TYPE_MAP: Mapping[str, WindowType] = {
    "_NET_WM_WINDOW_TYPE_NORMAL": WindowType.NORMAL,
    "_NET_WM_WINDOW_TYPE_DIALOG": WindowType.DIALOG,
    "_NET_WM_WINDOW_TYPE_SPLASH": WindowType.SPLASH,
    "_NET_WM_WINDOW_TYPE_UTILITY": WindowType.UTILITY,
    "_NET_WM_WINDOW_TYPE_TOOLBAR": WindowType.TOOLBAR,
    "_NET_WM_WINDOW_TYPE_MENU": WindowType.MENU,
    "_NET_WM_WINDOW_TYPE_POPUP_MENU": WindowType.MENU,
    "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU": WindowType.MENU,
    "_NET_WM_WINDOW_TYPE_DOCK": WindowType.DOCK,
    "_NET_WM_WINDOW_TYPE_DESKTOP": WindowType.DESKTOP,
}


def map_window_type(type_atom_names: Iterable[str]) -> WindowType:
    """Return the first recognised :class:`WindowType` from an EWMH type atom list.

    The EWMH spec says a window may advertise a list of window-type atoms in
    priority order (most specific first); the WM uses the first it
    understands. Perch follows the same rule. Unknown atoms are skipped; an
    empty list or a list of only-unknowns yields :data:`WindowType.UNKNOWN`
    (EWMH's implicit "normal if not specified" default is deliberately *not*
    applied here — the caller decides).
    """
    for name in type_atom_names:
        mapped = _WINDOW_TYPE_MAP.get(name)
        if mapped is not None:
            return mapped
    return WindowType.UNKNOWN


# ── WindowState derivation from _NET_WM_STATE ──────────────────────────────

def derive_window_state(state_atom_names: Iterable[str]) -> WindowState:
    """Priority-collapse ``_NET_WM_STATE`` atoms to a :class:`WindowState`.

    Priority (most-restrictive wins): fullscreen > maximised (both axes) >
    iconic/hidden > normal. ``_NET_WM_STATE_MAXIMIZED_HORZ`` on its own (no
    ``_VERT``) is *not* MAXIMIZED — the wm-spec requires both.
    """
    names = set(state_atom_names)
    if "_NET_WM_STATE_FULLSCREEN" in names:
        return WindowState.FULLSCREEN
    maxed = (
        "_NET_WM_STATE_MAXIMIZED_HORZ" in names
        and "_NET_WM_STATE_MAXIMIZED_VERT" in names
    )
    if maxed:
        return WindowState.MAXIMIZED
    if "_NET_WM_STATE_HIDDEN" in names:
        return WindowState.MINIMIZED
    return WindowState.NORMAL


# ── Atom registry ──────────────────────────────────────────────────────────

# All EWMH / ICCCM atom names Perch ever interns. Centralised so:
# 1. We have one place to audit "which parts of EWMH do we actually touch?"
#    (scope creep would show up here as a PR-sized diff).
# 2. The backend can pre-intern them at start() in a single round-trip via
#    a small loop, instead of scattering ``intern_atom`` calls through every
#    method.

ATOM_NAMES: tuple[str, ...] = (
    # Root-level state
    "_NET_CLIENT_LIST",
    "_NET_CURRENT_DESKTOP",
    "_NET_NUMBER_OF_DESKTOPS",
    "_NET_WORKAREA",
    "_NET_SUPPORTING_WM_CHECK",
    "_NET_ACTIVE_WINDOW",
    # Per-window identity / state
    "_NET_WM_NAME",
    "_NET_WM_PID",
    "_NET_WM_DESKTOP",
    "_NET_WM_STATE",
    "_NET_WM_WINDOW_TYPE",
    "_NET_FRAME_EXTENTS",
    # Commands
    "_NET_MOVERESIZE_WINDOW",
    "WM_CHANGE_STATE",
    "WM_PROTOCOLS",
    "WM_DELETE_WINDOW",
    # State atoms (used as values inside _NET_WM_STATE messages)
    "_NET_WM_STATE_FULLSCREEN",
    "_NET_WM_STATE_MAXIMIZED_HORZ",
    "_NET_WM_STATE_MAXIMIZED_VERT",
    "_NET_WM_STATE_HIDDEN",
    # Type atoms (values inside _NET_WM_WINDOW_TYPE)
    "_NET_WM_WINDOW_TYPE_NORMAL",
    "_NET_WM_WINDOW_TYPE_DIALOG",
    "_NET_WM_WINDOW_TYPE_SPLASH",
    "_NET_WM_WINDOW_TYPE_UTILITY",
    "_NET_WM_WINDOW_TYPE_TOOLBAR",
    "_NET_WM_WINDOW_TYPE_MENU",
    "_NET_WM_WINDOW_TYPE_POPUP_MENU",
    "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
    "_NET_WM_WINDOW_TYPE_DOCK",
    "_NET_WM_WINDOW_TYPE_DESKTOP",
    # Text properties
    "UTF8_STRING",
    "WM_WINDOW_ROLE",
)


class AtomTable:
    """Lookup ``name → int`` for the fixed :data:`ATOM_NAMES` set.

    Construction interns every name in one pass; misses after construction
    go through ``display.intern_atom`` and are cached. The table is
    intentionally small — we don't carry a general-purpose atom cache.
    """

    __slots__ = ("_atoms", "_display")

    def __init__(self, display: Display, names: Iterable[str] = ATOM_NAMES) -> None:
        self._display = display
        self._atoms: dict[str, int] = {}
        for name in names:
            self._atoms[name] = display.intern_atom(name)

    def __getitem__(self, name: str) -> int:
        atom = self._atoms.get(name)
        if atom is None:
            atom = self._display.intern_atom(name)
            self._atoms[name] = atom
        return atom

    def name_for(self, atom: int) -> str | None:
        """Reverse lookup for cached atoms only.

        Used to resolve ``_NET_WM_STATE`` and ``_NET_WM_WINDOW_TYPE`` list
        values back to strings without issuing one ``get_atom_name`` round-
        trip per value. Returns ``None`` for atoms we never interned
        (unknown state/type extensions).
        """
        for name, value in self._atoms.items():
            if value == atom:
                return name
        return None

    def names_for(self, atoms: Iterable[int]) -> list[str]:
        out: list[str] = []
        for atom in atoms:
            n = self.name_for(atom)
            if n is not None:
                out.append(n)
        return out


# ── Client message factories ───────────────────────────────────────────────


def build_moveresize_message(
    window: Window,
    atoms: AtomTable,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    source: int = SOURCE_PAGER,
) -> ClientMessage:
    """Build a ``_NET_MOVERESIZE_WINDOW`` event aimed at ``window``."""
    from Xlib.protocol.event import ClientMessage

    flags = moveresize_flags(source=source)
    # x and y are INT32 per wm-spec, but python-xlib packs format-32
    # ClientMessage data through an unsigned array ('I'), so a negative
    # coordinate raises OverflowError — outside the backend error taxonomy
    # entirely, and reachable from any window the user dragged off the left
    # or top edge, whose position Perch faithfully remembered. Send the
    # two's-complement bits the X server reads back as the signed value.
    return ClientMessage(
        window=window,
        client_type=atoms["_NET_MOVERESIZE_WINDOW"],
        data=(32, [flags, x & 0xFFFFFFFF, y & 0xFFFFFFFF, w, h]),
    )


def build_wm_state_message(
    window: Window,
    atoms: AtomTable,
    action: int,
    atom1: int,
    atom2: int = 0,
    *,
    source: int = SOURCE_PAGER,
) -> ClientMessage:
    """Build a ``_NET_WM_STATE`` event (add/remove/toggle one or two state atoms)."""
    from Xlib.protocol.event import ClientMessage

    if action not in (WM_STATE_REMOVE, WM_STATE_ADD, WM_STATE_TOGGLE):
        raise ValueError(f"invalid _NET_WM_STATE action: {action!r}")
    return ClientMessage(
        window=window,
        client_type=atoms["_NET_WM_STATE"],
        data=(32, [action, atom1, atom2, source, 0]),
    )


def build_change_state_message(
    window: Window,
    atoms: AtomTable,
    state: int = ICCCM_ICONIC_STATE,
) -> ClientMessage:
    """Build a ``WM_CHANGE_STATE`` event (ICCCM iconify path)."""
    from Xlib.protocol.event import ClientMessage

    return ClientMessage(
        window=window,
        client_type=atoms["WM_CHANGE_STATE"],
        data=(32, [state, 0, 0, 0, 0]),
    )


def build_wm_desktop_message(
    window: Window,
    atoms: AtomTable,
    desktop: int,
    *,
    source: int = SOURCE_PAGER,
) -> ClientMessage:
    """Build a ``_NET_WM_DESKTOP`` event (move the window to a virtual desktop).

    ``desktop = 0xFFFFFFFF`` means "sticky / all desktops" (wm-spec §5.8);
    :data:`~perch.backend.types.DesktopIndex` uses ``-1`` for that. Callers
    translate at the boundary.
    """
    from Xlib.protocol.event import ClientMessage

    return ClientMessage(
        window=window,
        client_type=atoms["_NET_WM_DESKTOP"],
        data=(32, [desktop, source, 0, 0, 0]),
    )


def build_active_window_message(
    window: Window,
    atoms: AtomTable,
    *,
    source: int = SOURCE_PAGER,
) -> ClientMessage:
    """Build a ``_NET_ACTIVE_WINDOW`` event (activate, and so de-iconify).

    wm-spec §5.7: a compliant WM un-iconifies the window before raising it,
    which makes this the only EWMH route back out of the iconic state — the
    ICCCM ``WM_CHANGE_STATE`` message that puts a window there has no
    NormalState counterpart a pager may send.
    """
    from Xlib.protocol.event import ClientMessage

    return ClientMessage(
        window=window,
        client_type=atoms["_NET_ACTIVE_WINDOW"],
        data=(32, [source, 0, 0, 0, 0]),
    )


def build_close_message(window: Window, atoms: AtomTable) -> ClientMessage:
    """Build a ``WM_PROTOCOLS`` + ``WM_DELETE_WINDOW`` event (ICCCM close)."""
    from Xlib.protocol.event import ClientMessage

    return ClientMessage(
        window=window,
        client_type=atoms["WM_PROTOCOLS"],
        data=(32, [atoms["WM_DELETE_WINDOW"], 0, 0, 0, 0]),
    )


# ── DesktopIndex <-> EWMH wire value ───────────────────────────────────────

STICKY_WIRE_VALUE = 0xFFFFFFFF


def desktop_to_wire(index: int) -> int:
    """Translate :data:`DesktopIndex` (``-1`` = sticky) to the EWMH wire value."""
    return STICKY_WIRE_VALUE if index < 0 else index


def desktop_from_wire(value: int) -> int:
    """Translate an EWMH desktop number (0xFFFFFFFF = sticky) to :data:`DesktopIndex`."""
    return -1 if value == STICKY_WIRE_VALUE else value


# ── Text decoding ──────────────────────────────────────────────────────────

def decode_text_property(
    value: bytes | str | None, *, utf8: bool
) -> str:
    """Decode a text property to :class:`str`.

    ``python-xlib`` is inconsistent: ``get_wm_class`` / ``get_wm_name`` already
    decode (to Latin-1) and return :class:`str`, whereas manual
    ``get_full_property`` returns :class:`bytes`. This helper normalises both
    shapes. ``utf8=True`` for ``_NET_WM_NAME``-style UTF8_STRING; ``False``
    for ICCCM ``WM_NAME``-style Latin-1 ``STRING``.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    encoding = "utf-8" if utf8 else "latin-1"
    return value.decode(encoding, errors="replace").rstrip("\x00")
