"""Unit tests for :mod:`perch.backend.x11.identity`.

These use lightweight stub objects instead of a real display — the goal is
to validate that property-shape handling, override-redirect filtering, the
UTF-8/Latin-1 title fallback, and the frame-extents subtraction are wired
together correctly. End-to-end proof against a real WM is in
``test_live_openbox.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from perch.backend.types import Geometry, OutputInfo, WindowState, WindowType
from perch.backend.x11.ewmh import AtomTable
from perch.backend.x11.identity import read_window_info

# ── Stub Xlib fakes ────────────────────────────────────────────────────────


@dataclass
class _Attrs:
    override_redirect: bool = False


@dataclass
class _Prop:
    value: Any
    format: int = 32
    property_type: int = 0


@dataclass
class _RawGeom:
    width: int
    height: int


class _FakeTranslateReply:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class _FakeRoot:
    id = 1

    def translate_coords(
        self, src_window: Any, x: int, y: int
    ) -> _FakeTranslateReply:
        # Mirrors python-xlib: root.translate_coords(window, x, y) → root coords.
        dx, dy = getattr(src_window, "_translate_to", (0, 0))
        return _FakeTranslateReply(dx + x, dy + y)


class _FakeScreen:
    root = _FakeRoot()


class _FakeWindow:
    """Minimal stand-in for an ``Xlib.xobject.drawable.Window``."""

    def __init__(
        self,
        *,
        wid: int = 0x400001,
        override_redirect: bool = False,
        wm_class: tuple[str, str] | None = ("firefox", "firefox"),
        wm_name: str | None = "Mozilla Firefox",
        title_utf8: bytes | None = None,
        props: dict[int, _Prop] | None = None,
        geom: tuple[int, int] = (800, 600),
        translate_to: tuple[int, int] = (110, 70),
        transient_for: int | None = None,
    ) -> None:
        self.id = wid
        self._attrs = _Attrs(override_redirect=override_redirect)
        self._wm_class = wm_class
        self._wm_name = wm_name
        self._title_utf8 = title_utf8
        self._props = props or {}
        self._geom = geom
        self._translate_to = translate_to
        self._transient_for = transient_for

    def get_attributes(self) -> _Attrs:
        return self._attrs

    def get_wm_class(self) -> tuple[str, str] | None:
        return self._wm_class

    def get_wm_name(self) -> str | None:
        return self._wm_name

    def get_full_property(self, atom: int, _type: int) -> _Prop | None:
        return self._props.get(atom)

    def get_geometry(self) -> _RawGeom:
        return _RawGeom(width=self._geom[0], height=self._geom[1])

    def get_wm_transient_for(self) -> Any:
        if self._transient_for is None:
            return None
        return type("Parent", (), {"id": self._transient_for})()


def _atoms(fake: _FakeAtoms) -> AtomTable:
    """Cast a duck-typed stub to :class:`AtomTable` for strict-typed callers.

    The stub implements the four methods ``read_window_info`` actually calls
    (``__getitem__``, ``name_for``, ``names_for``) but can't inherit from
    ``AtomTable`` because that constructor needs a live ``Xlib.Display``.
    """
    return cast(AtomTable, fake)


class _FakeAtoms:
    """Matches the public surface of :class:`perch.backend.x11.ewmh.AtomTable`."""

    def __init__(self) -> None:
        # Simple deterministic atoms.
        self._atoms: dict[str, int] = {
            "_NET_WM_NAME": 100,
            "UTF8_STRING": 101,
            "_NET_WM_PID": 102,
            "_NET_WM_DESKTOP": 103,
            "_NET_WM_STATE": 104,
            "_NET_WM_WINDOW_TYPE": 105,
            "_NET_FRAME_EXTENTS": 106,
            "WM_WINDOW_ROLE": 107,
            "_NET_WM_STATE_FULLSCREEN": 200,
            "_NET_WM_STATE_MAXIMIZED_HORZ": 201,
            "_NET_WM_STATE_MAXIMIZED_VERT": 202,
            "_NET_WM_STATE_HIDDEN": 203,
            "_NET_WM_WINDOW_TYPE_DIALOG": 300,
            "_NET_WM_WINDOW_TYPE_NORMAL": 301,
        }

    def __getitem__(self, name: str) -> int:
        return self._atoms[name]

    def name_for(self, atom: int) -> str | None:
        for k, v in self._atoms.items():
            if v == atom:
                return k
        return None

    def names_for(self, atoms: Any) -> list[str]:
        return [n for n in (self.name_for(a) for a in atoms) if n is not None]


class _FakeDisplay:
    def screen(self) -> _FakeScreen:
        return _FakeScreen()


# ── Tests ──────────────────────────────────────────────────────────────────


_OUTPUTS = [
    OutputInfo(
        name="DP-1",
        geometry=Geometry(0, 0, 2560, 1440),
        work_area=Geometry(0, 0, 2560, 1400),
        scale=1.0,
        refresh_mhz=144000,
        is_primary=True,
        is_connected=True,
    ),
    OutputInfo(
        name="HDMI-1",
        geometry=Geometry(2560, 0, 1920, 1080),
        work_area=Geometry(2560, 0, 1920, 1040),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=False,
        is_connected=True,
    ),
]


def test_override_redirect_windows_are_ignored() -> None:
    win = _FakeWindow(override_redirect=True)
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is None


def test_basic_window_info_matches_expected_shape() -> None:
    atoms = _FakeAtoms()
    # root.translate_coords(window, 0, 0) returns the client top-left in
    # root coords (extents are NOT double-applied — see the comment in
    # identity._read_client_geometry). So translate_to=(110, 70) + geom
    # 800x600 → Geometry(110, 70, 800, 600) straight through.
    props = {
        atoms["_NET_WM_PID"]: _Prop(value=[4321], format=32),
        atoms["_NET_WM_STATE"]: _Prop(value=[atoms["_NET_WM_STATE_HIDDEN"]], format=32),
        atoms["_NET_WM_WINDOW_TYPE"]: _Prop(
            value=[atoms["_NET_WM_WINDOW_TYPE_DIALOG"]], format=32,
        ),
        atoms["_NET_WM_DESKTOP"]: _Prop(value=[2], format=32),
    }
    win = _FakeWindow(
        props=props,
        geom=(800, 600),
        translate_to=(110, 70),
    )
    got = read_window_info(_FakeDisplay(), _atoms(atoms), win, _OUTPUTS)
    assert got is not None
    assert got.app_id == "firefox"
    assert got.wm_class == "firefox"
    assert got.title == "Mozilla Firefox"
    assert got.pid == 4321
    assert got.type is WindowType.DIALOG
    assert got.state is WindowState.MINIMIZED  # _NET_WM_STATE_HIDDEN
    assert got.geometry == Geometry(110, 70, 800, 600)
    assert got.monitor == "DP-1"
    assert got.desktop == 2


def test_net_wm_name_utf8_wins_over_wm_name_latin1() -> None:
    atoms = _FakeAtoms()
    props = {
        atoms["_NET_WM_NAME"]: _Prop(
            value="Résumé — editor".encode(), format=8,
        ),
    }
    win = _FakeWindow(props=props, wm_name="should-not-be-used")
    got = read_window_info(_FakeDisplay(), _atoms(atoms), win, _OUTPUTS)
    assert got is not None
    assert got.title == "Résumé — editor"


def test_missing_net_wm_name_falls_back_to_wm_name() -> None:
    atoms = _FakeAtoms()
    # No _NET_WM_NAME in props → fall back to WM_NAME (latin-1).
    win = _FakeWindow(props={}, wm_name="Plain ICCCM title")
    got = read_window_info(_FakeDisplay(), _atoms(atoms), win, _OUTPUTS)
    assert got is not None
    assert got.title == "Plain ICCCM title"


def test_missing_wm_class_produces_empty_app_id_and_class() -> None:
    win = _FakeWindow(wm_class=None)
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is not None
    assert got.app_id == ""
    assert got.wm_class == ""


def test_app_id_is_lowercased() -> None:
    # Firefox's WM_CLASS is literally "Firefox" on Wayland-XWayland. Lowercase
    # keeps identity stable across distros / versions.
    win = _FakeWindow(wm_class=("Firefox", "Firefox"))
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is not None
    assert got.app_id == "firefox"
    assert got.wm_class == "Firefox"


def test_sticky_desktop_maps_to_negative_one() -> None:
    atoms = _FakeAtoms()
    props = {atoms["_NET_WM_DESKTOP"]: _Prop(value=[0xFFFFFFFF], format=32)}
    win = _FakeWindow(props=props)
    got = read_window_info(_FakeDisplay(), _atoms(atoms), win, _OUTPUTS)
    assert got is not None
    assert got.desktop == -1


def test_transient_parent_surfaces_as_wid_string() -> None:
    win = _FakeWindow(transient_for=0x200033)
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is not None
    assert got.parent == str(0x200033)


def test_offscreen_window_falls_back_to_primary_monitor() -> None:
    # Translate the window way off the right edge so it doesn't overlap anything.
    win = _FakeWindow(translate_to=(99999, 99999), geom=(100, 100))
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is not None
    assert got.monitor == "DP-1"  # primary fallback


def test_absent_state_defaults_to_normal() -> None:
    # No _NET_WM_STATE at all — window exists but has nothing set.
    win = _FakeWindow(props={})
    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), win, _OUTPUTS)
    assert got is not None
    assert got.state is WindowState.NORMAL


def test_dead_window_at_attributes_read_returns_none() -> None:
    from Xlib import error as _xerror

    class _DeadWindow(_FakeWindow):
        def get_attributes(self) -> Any:
            # Simulate the window being destroyed just after _NET_CLIENT_LIST
            # read — the post-enumeration race documented in
            # docs/04-backend-x11.md. Bypass BadWindow.__init__ (which
            # expects wire-format error data) via __new__.
            raise _xerror.BadWindow.__new__(_xerror.BadWindow)

    got = read_window_info(_FakeDisplay(), _atoms(_FakeAtoms()), _DeadWindow(), _OUTPUTS)
    assert got is None
