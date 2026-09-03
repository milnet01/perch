"""Unit tests for :mod:`perch.backend.x11.hotkeys`.

The grab/ungrab round-trip against a live server is exercised in
``test_live_openbox.py`` (M4.g). Here we validate the pure logic:
PortableText → X11 mod-mask + keysym, the NumLock resolution walk, the
lock-mask fan-out, and KeyPress-state normalisation.
"""

from __future__ import annotations

from typing import Any

import pytest
from Xlib import X as _X

from perch.backend.x11.hotkeys import (
    HotkeyParseError,
    _lock_masks,
    compute_numlock_mask,
    normalise_modifier_state,
    parse_portable_accel,
)

# ── parse_portable_accel ───────────────────────────────────────────────────


def test_parse_simple_modifier_plus_key() -> None:
    got = parse_portable_accel("Meta+Left")
    assert got.modifiers == _X.Mod4Mask
    assert got.keysym_name == "Left"


def test_parse_multiple_modifiers() -> None:
    got = parse_portable_accel("Ctrl+Alt+T")
    assert got.modifiers == _X.ControlMask | _X.Mod1Mask
    # Lone alpha key with no Shift: lowercased for X11.
    assert got.keysym_name == "t"


def test_parse_function_key_preserves_case() -> None:
    got = parse_portable_accel("F11")
    assert got.modifiers == 0
    assert got.keysym_name == "F11"


def test_parse_shift_letter_preserves_uppercase_keysym() -> None:
    # With Shift in the modifier set, the user explicitly wants Shift+a,
    # which X11 expresses as the lowercase keysym + ShiftMask. Still send
    # lowercase: the mask carries the shift information.
    got = parse_portable_accel("Shift+a")
    assert got.modifiers == _X.ShiftMask
    assert got.keysym_name == "a"


def test_parse_qt_aliases_map_to_xk_names() -> None:
    assert parse_portable_accel("PgUp").keysym_name == "Prior"
    assert parse_portable_accel("Esc").keysym_name == "Escape"
    assert parse_portable_accel("Backspace").keysym_name == "BackSpace"
    assert parse_portable_accel("Space").keysym_name == "space"


def test_parse_case_insensitive_modifier_names() -> None:
    got = parse_portable_accel("META+CTRL+L")
    assert got.modifiers == _X.Mod4Mask | _X.ControlMask


def test_parse_rejects_empty_accelerator() -> None:
    with pytest.raises(HotkeyParseError):
        parse_portable_accel("")


def test_parse_rejects_multiple_nonmodifier_keys() -> None:
    with pytest.raises(HotkeyParseError):
        parse_portable_accel("Ctrl+A+B")


def test_parse_rejects_whitespace_only_accelerator() -> None:
    with pytest.raises(HotkeyParseError):
        parse_portable_accel("  ")


# ── lock-mask fan-out ──────────────────────────────────────────────────────


def test_lock_masks_includes_base_and_capslock_without_numlock() -> None:
    # When NumLock mask is 0, the set collapses to just {0, LockMask}.
    got = _lock_masks(0)
    assert got == frozenset({0, _X.LockMask})


def test_lock_masks_includes_all_four_combinations_with_numlock() -> None:
    # Mod2Mask is the typical NumLock bit on US layouts.
    got = _lock_masks(_X.Mod2Mask)
    assert got == frozenset({
        0,
        _X.LockMask,
        _X.Mod2Mask,
        _X.LockMask | _X.Mod2Mask,
    })


# ── normalise_modifier_state ───────────────────────────────────────────────


def test_normalise_strips_capslock_bit() -> None:
    # Held: Meta + CapsLock. Base should just be Meta.
    state = _X.Mod4Mask | _X.LockMask
    assert normalise_modifier_state(state, _X.Mod2Mask) == _X.Mod4Mask


def test_normalise_strips_numlock_bit() -> None:
    state = _X.ControlMask | _X.Mod1Mask | _X.Mod2Mask
    got = normalise_modifier_state(state, _X.Mod2Mask)
    assert got == _X.ControlMask | _X.Mod1Mask


def test_normalise_preserves_real_modifiers_when_no_lock_bits_set() -> None:
    state = _X.ShiftMask | _X.Mod4Mask
    got = normalise_modifier_state(state, _X.Mod2Mask)
    assert got == state


# ── compute_numlock_mask (via stub display) ────────────────────────────────


class _StubDisplay:
    def __init__(
        self,
        numlock_keycode: int,
        mapping: dict[int, list[int]],
    ) -> None:
        self._numlock_keycode = numlock_keycode
        self._mapping = mapping

    def keysym_to_keycode(self, _keysym: Any) -> int:
        return self._numlock_keycode

    def get_modifier_mapping(self) -> list[list[int]]:
        # Always return 8 sublists; missing indices default to empty.
        return [self._mapping.get(i, []) for i in range(8)]


def test_compute_numlock_mask_finds_mod2_on_typical_layout() -> None:
    # NumLock at keycode 77 on mod2 (typical US layout).
    d = _StubDisplay(numlock_keycode=77, mapping={4: [77]})
    assert compute_numlock_mask(d) == _X.Mod2Mask


def test_compute_numlock_mask_finds_mod3_on_mac_like_layout() -> None:
    # Some Mac layouts move NumLock to Mod3 (index 5).
    d = _StubDisplay(numlock_keycode=77, mapping={5: [77]})
    assert compute_numlock_mask(d) == _X.Mod3Mask


def test_compute_numlock_mask_returns_zero_when_no_numlock_bound() -> None:
    d = _StubDisplay(numlock_keycode=0, mapping={})
    assert compute_numlock_mask(d) == 0


def test_compute_numlock_mask_returns_zero_when_numlock_unbound_to_mod() -> None:
    # Numlock keysym exists but isn't bound to any Mod1-Mod5 bit.
    d = _StubDisplay(numlock_keycode=77, mapping={})
    assert compute_numlock_mask(d) == 0


# ── _on_key_press dispatch (simulates the full KeyPress → hotkey_fired
# chain without needing xtest / xdotool to actually reach a grabber, which
# Xvfb does not reliably support) ──────────────────────────────────────────


class _StubKeyPressEvent:
    def __init__(self, detail: int, state: int, time: int = 0) -> None:
        self.detail = detail
        self.state = state
        self.time = time


def test_on_key_press_emits_hotkey_fired_for_matching_entry() -> None:
    from unittest.mock import MagicMock

    from perch.backend.x11.backend import X11Backend

    # Build the backend without constructing a QObject (we only need the
    # signal + lookup machinery).
    backend = X11Backend.__new__(X11Backend)
    backend._numlock_mask = _X.Mod2Mask
    backend._scrolllock_mask = 0
    backend._key_release_times = {}
    backend._hotkey_lookup = {(95, _X.ControlMask | _X.Mod1Mask): "cb-test"}
    backend.hotkey_fired = MagicMock()

    # User held Ctrl+Alt+F11 with NumLock on (Mod2 set in state).
    evt = _StubKeyPressEvent(
        detail=95, state=_X.ControlMask | _X.Mod1Mask | _X.Mod2Mask
    )
    backend._on_key_press(evt)

    backend.hotkey_fired.emit.assert_called_once_with("cb-test")


def test_on_key_press_ignores_unregistered_combinations() -> None:
    from unittest.mock import MagicMock

    from perch.backend.x11.backend import X11Backend

    backend = X11Backend.__new__(X11Backend)
    backend._numlock_mask = _X.Mod2Mask
    backend._scrolllock_mask = 0
    backend._key_release_times = {}
    backend._hotkey_lookup = {(95, _X.ControlMask | _X.Mod1Mask): "cb-test"}
    backend.hotkey_fired = MagicMock()

    # Plain F11 (no modifiers) — we should not fire "cb-test".
    evt = _StubKeyPressEvent(detail=95, state=0)
    backend._on_key_press(evt)
    backend.hotkey_fired.emit.assert_not_called()


# ── PERC-0047: literal "+" as the key ──────────────────────────────────────
# QKeySequence PortableText spells the plus key as a bare "+", so "Ctrl++"
# is the legal form docs/03-backend-interface.md names as the contract.
# Splitting on "+" and dropping empties loses it entirely.


def test_parse_accepts_literal_plus_as_the_key() -> None:
    got = parse_portable_accel("Ctrl++")
    assert got.modifiers == _X.ControlMask
    assert got.keysym_name == "plus"


def test_parse_accepts_bare_plus_with_no_modifier() -> None:
    got = parse_portable_accel("+")
    assert got.modifiers == 0
    assert got.keysym_name == "plus"


def test_parse_accepts_literal_plus_with_several_modifiers() -> None:
    got = parse_portable_accel("Ctrl+Alt++")
    assert got.modifiers == _X.ControlMask | _X.Mod1Mask
    assert got.keysym_name == "plus"


def test_parse_still_rejects_a_dangling_modifier_separator() -> None:
    # "Ctrl+" names no key at all — that is malformed, not a plus key.
    with pytest.raises(HotkeyParseError):
        parse_portable_accel("Ctrl+")


# ── PERC-0047: ScrollLock in the fan-out ───────────────────────────────────
# docs/04-backend-x11.md §Hotkeys promises the grab covers every combination
# of NumLock / CapsLock / ScrollLock. Four masks cover only the first two, so
# a hotkey pressed with ScrollLock on is never delivered.


def test_lock_masks_covers_all_eight_combinations_with_scrolllock() -> None:
    got = _lock_masks(_X.Mod2Mask, _X.Mod5Mask)
    assert got == frozenset({
        0,
        _X.LockMask,
        _X.Mod2Mask,
        _X.Mod5Mask,
        _X.LockMask | _X.Mod2Mask,
        _X.LockMask | _X.Mod5Mask,
        _X.Mod2Mask | _X.Mod5Mask,
        _X.LockMask | _X.Mod2Mask | _X.Mod5Mask,
    })


def test_normalise_strips_scrolllock_bit() -> None:
    state = _X.Mod4Mask | _X.Mod5Mask
    assert normalise_modifier_state(state, _X.Mod2Mask, _X.Mod5Mask) == _X.Mod4Mask


def test_compute_scrolllock_mask_finds_its_mod_bit() -> None:
    from perch.backend.x11.hotkeys import compute_scrolllock_mask

    d = _StubDisplay(numlock_keycode=78, mapping={7: [78]})
    assert compute_scrolllock_mask(d) == _X.Mod5Mask


def test_compute_scrolllock_mask_returns_zero_when_unbound() -> None:
    from perch.backend.x11.hotkeys import compute_scrolllock_mask

    d = _StubDisplay(numlock_keycode=0, mapping={})
    assert compute_scrolllock_mask(d) == 0


# ── PERC-0047: autorepeat filter ───────────────────────────────────────────
# docs/04-backend-x11.md §Hotkeys: "Key repeat delivers a rapid KeyRelease +
# KeyPress pair with matching timestamps; filter these when we only want one
# fire per press." Without the filter a held snap hotkey re-applies at the
# autorepeat rate.


class _StubKeyReleaseEvent:
    def __init__(self, detail: int, state: int, time: int = 0) -> None:
        self.detail = detail
        self.state = state
        self.time = time


def _hotkey_backend() -> Any:
    from unittest.mock import MagicMock

    from perch.backend.x11.backend import X11Backend

    backend = X11Backend.__new__(X11Backend)
    backend._numlock_mask = _X.Mod2Mask
    backend._scrolllock_mask = 0
    backend._key_release_times = {}
    backend._hotkey_lookup = {(95, _X.ControlMask): "cb-test"}
    backend.hotkey_fired = MagicMock()
    return backend


def test_autorepeat_pair_with_matching_timestamp_fires_once() -> None:
    backend = _hotkey_backend()
    # Genuine press.
    backend._on_key_press(_StubKeyPressEvent(95, _X.ControlMask, time=1000))
    # X autorepeat: a KeyRelease and KeyPress sharing one timestamp.
    backend._on_key_release(_StubKeyReleaseEvent(95, _X.ControlMask, time=1040))
    backend._on_key_press(_StubKeyPressEvent(95, _X.ControlMask, time=1040))

    backend.hotkey_fired.emit.assert_called_once_with("cb-test")


def test_genuine_second_press_after_release_fires_again() -> None:
    backend = _hotkey_backend()
    backend._on_key_press(_StubKeyPressEvent(95, _X.ControlMask, time=1000))
    # A real release, then a distinctly later press — two deliberate taps.
    backend._on_key_release(_StubKeyReleaseEvent(95, _X.ControlMask, time=1100))
    backend._on_key_press(_StubKeyPressEvent(95, _X.ControlMask, time=1400))

    assert backend.hotkey_fired.emit.call_count == 2


def test_release_of_one_key_does_not_suppress_another() -> None:
    backend = _hotkey_backend()
    backend._hotkey_lookup[(96, _X.ControlMask)] = "cb-other"
    backend._on_key_release(_StubKeyReleaseEvent(95, _X.ControlMask, time=2000))
    # Same timestamp, different keycode — not the repeat of that release.
    backend._on_key_press(_StubKeyPressEvent(96, _X.ControlMask, time=2000))

    backend.hotkey_fired.emit.assert_called_once_with("cb-other")
