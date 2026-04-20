"""Pure-logic tests for :mod:`perch.backend.x11.ewmh`.

Nothing here touches a real ``Display`` — the module is deliberately
structured so atom packing, state derivation, and type mapping are all
testable without Xvfb. The live display interactions land in
``tests/backend/x11/test_live_openbox.py`` (M4.g).
"""

from __future__ import annotations

import pytest

from perch.backend.types import WindowState, WindowType
from perch.backend.x11.ewmh import (
    PRESENCE_ALL,
    SOURCE_APPLICATION,
    SOURCE_PAGER,
    STATIC_GRAVITY,
    STICKY_WIRE_VALUE,
    WM_STATE_ADD,
    WM_STATE_REMOVE,
    WM_STATE_TOGGLE,
    decode_text_property,
    derive_window_state,
    desktop_from_wire,
    desktop_to_wire,
    map_window_type,
    moveresize_flags,
)

# ── moveresize_flags bit layout ────────────────────────────────────────────


def test_moveresize_flags_defaults_pack_gravity_presence_source() -> None:
    flags = moveresize_flags()
    assert flags & 0xFF == STATIC_GRAVITY
    assert flags & PRESENCE_ALL == PRESENCE_ALL
    assert (flags >> 12) & 0xF == SOURCE_PAGER


def test_moveresize_flags_application_source_lives_in_bits_12_through_15() -> None:
    flags = moveresize_flags(source=SOURCE_APPLICATION)
    # Bits 12..15 carry the source, not 12..13 — a common doc-site misreading.
    assert (flags >> 12) & 0xF == SOURCE_APPLICATION
    # Bits 16..31 must be zero.
    assert flags >> 16 == 0


def test_moveresize_flags_drops_absent_components() -> None:
    # Width-and-height-only move: x/y presence bits clear.
    flags = moveresize_flags(x=False, y=False)
    assert flags & (1 << 8) == 0
    assert flags & (1 << 9) == 0
    assert flags & (1 << 10) != 0
    assert flags & (1 << 11) != 0


def test_moveresize_flags_validates_gravity_range() -> None:
    with pytest.raises(ValueError):
        moveresize_flags(gravity=300)


def test_moveresize_flags_validates_source_range() -> None:
    with pytest.raises(ValueError):
        moveresize_flags(source=16)  # 4 bits only


# ── WindowType mapping (first-recognised wins) ────────────────────────────


def test_map_window_type_returns_unknown_for_empty_list() -> None:
    assert map_window_type([]) is WindowType.UNKNOWN


def test_map_window_type_skips_unknown_atoms() -> None:
    assert (
        map_window_type(["_NET_WM_WINDOW_TYPE_FOO", "_NET_WM_WINDOW_TYPE_DIALOG"])
        is WindowType.DIALOG
    )


def test_map_window_type_honours_priority_order() -> None:
    # Caller sends most-specific-first; we take the first match.
    got = map_window_type(
        ["_NET_WM_WINDOW_TYPE_UTILITY", "_NET_WM_WINDOW_TYPE_NORMAL"]
    )
    assert got is WindowType.UTILITY


def test_map_window_type_popup_and_dropdown_both_collapse_to_menu() -> None:
    assert map_window_type(["_NET_WM_WINDOW_TYPE_POPUP_MENU"]) is WindowType.MENU
    assert (
        map_window_type(["_NET_WM_WINDOW_TYPE_DROPDOWN_MENU"]) is WindowType.MENU
    )


# ── WindowState derivation (priority collapse) ────────────────────────────


def test_derive_state_fullscreen_beats_everything() -> None:
    names = [
        "_NET_WM_STATE_FULLSCREEN",
        "_NET_WM_STATE_MAXIMIZED_HORZ",
        "_NET_WM_STATE_MAXIMIZED_VERT",
        "_NET_WM_STATE_HIDDEN",
    ]
    assert derive_window_state(names) is WindowState.FULLSCREEN


def test_derive_state_both_maximize_axes_required() -> None:
    # Single-axis maximise is a valid EWMH state but is NOT WindowState.MAXIMIZED.
    got = derive_window_state(["_NET_WM_STATE_MAXIMIZED_HORZ"])
    assert got is WindowState.NORMAL


def test_derive_state_maximized_when_both_axes_present() -> None:
    got = derive_window_state(
        ["_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_MAXIMIZED_VERT"]
    )
    assert got is WindowState.MAXIMIZED


def test_derive_state_hidden_maps_to_minimized() -> None:
    assert (
        derive_window_state(["_NET_WM_STATE_HIDDEN"]) is WindowState.MINIMIZED
    )


def test_derive_state_empty_defaults_to_normal() -> None:
    assert derive_window_state([]) is WindowState.NORMAL


# ── desktop wire value round-trip ─────────────────────────────────────────


def test_desktop_sticky_roundtrip() -> None:
    # DesktopIndex(-1) ↔ wire 0xFFFFFFFF.
    assert desktop_to_wire(-1) == STICKY_WIRE_VALUE
    assert desktop_from_wire(STICKY_WIRE_VALUE) == -1


def test_desktop_plain_passthrough() -> None:
    assert desktop_to_wire(2) == 2
    assert desktop_from_wire(2) == 2


# ── WM_STATE action constants ─────────────────────────────────────────────


def test_wm_state_action_constants() -> None:
    # Exact numeric values from wm-spec §5.7 — consumers depend on these.
    assert (WM_STATE_REMOVE, WM_STATE_ADD, WM_STATE_TOGGLE) == (0, 1, 2)


# ── decode_text_property ──────────────────────────────────────────────────


def test_decode_utf8_bytes_to_str() -> None:
    assert decode_text_property(b"Mozilla Firefox", utf8=True) == (
        "Mozilla Firefox"
    )


def test_decode_latin1_bytes_to_str() -> None:
    # 0xE9 is "é" in Latin-1, invalid as UTF-8 without a continuation byte.
    assert decode_text_property(b"caf\xe9", utf8=False) == "café"


def test_decode_passthrough_when_already_str() -> None:
    assert decode_text_property("already-decoded", utf8=True) == "already-decoded"


def test_decode_none_returns_empty_string() -> None:
    assert decode_text_property(None, utf8=True) == ""


def test_decode_strips_trailing_null_terminators() -> None:
    # Some X clients null-terminate WM_NAME; our str consumers never want it.
    assert decode_text_property(b"kitchen\x00", utf8=True) == "kitchen"
