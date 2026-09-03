"""Hotkey registration via ``XGrabKey`` with lock-mask fan-out.

Responsibilities:

1. Translate a Qt :class:`QKeySequence` Portable-Text accelerator (e.g.
   ``"Meta+Ctrl+Left"``) into the ``(X11 mod mask, keycode)`` pair
   ``XGrabKey`` wants.
2. Compute the NumLock mask dynamically — some keyboard layouts bind
   NumLock to a Mod bit other than Mod2 (notably Mac layouts), so we
   walk the modifier map at startup.
3. Grab the key four times, with every combination of
   ``(0, LockMask, numlock_mask, LockMask | numlock_mask)`` — the
   standard EWMH-tool pattern that lets the hotkey fire regardless of
   whether the user had CapsLock / NumLock on when they pressed it.
4. Normalise ``KeyPress.state`` back down to the base mask before
   comparing against our registration table.

The Qt accelerator form matches what Perch stores in ``config.toml`` and
what the UI's :class:`HotkeyEdit` emits. The X11 form is an implementation
detail that never leaks back into the core.

Design references:
- ``docs/04-backend-x11.md`` §Hotkeys
- ``docs/03-backend-interface.md`` §Hotkey accelerators
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from Xlib import XK
from Xlib import X as _X
from Xlib import error as _xerror

if TYPE_CHECKING:
    from Xlib.display import Display


# ── PortableText → X11 modifiers + keysym ──────────────────────────────────

_MOD_PORTABLE_TO_X = {
    "meta": _X.Mod4Mask,   # Super / Windows / Command
    "ctrl": _X.ControlMask,
    "control": _X.ControlMask,
    "alt": _X.Mod1Mask,
    "shift": _X.ShiftMask,
}

# Qt's Portable-Text names a few keys differently from X11 keysyms; normalise
# at the boundary so ``"Left"`` → XK_Left, ``"Return"`` → XK_Return, etc.
# Single characters (letters, digits) pass through unchanged (lowercased for
# letters since Qt emits them capitalised but X11 wants ``a`` not ``A``
# unless Shift is set).
_KEY_ALIASES: dict[str, str] = {
    "PgUp": "Prior",
    "PgDown": "Next",
    "Up": "Up",
    "Down": "Down",
    "Left": "Left",
    "Right": "Right",
    "Home": "Home",
    "End": "End",
    "Insert": "Insert",
    "Delete": "Delete",
    "Backspace": "BackSpace",
    "Tab": "Tab",
    "Esc": "Escape",
    "Return": "Return",
    "Enter": "Return",
    "Space": "space",
    # QKeySequence spells the plus key as a bare "+", so "Ctrl++" is the
    # legal PortableText form for Ctrl and that key.
    "+": "plus",
}


class HotkeyParseError(ValueError):
    """Raised when a PortableText accelerator can't be mapped to X11."""


@dataclass(frozen=True, slots=True)
class ParsedHotkey:
    """An accelerator split into modifiers and a keysym name.

    ``modifiers`` is the X11 mod mask *without* lock bits; ``keysym_name``
    is the XK_* suffix string passed to :func:`Xlib.XK.string_to_keysym`.
    """

    modifiers: int
    keysym_name: str


def parse_portable_accel(accel: str) -> ParsedHotkey:
    """Parse a QKeySequence PortableText accelerator into X11 pieces.

    Examples:
      ``"Meta+Left"`` → ``ParsedHotkey(Mod4Mask, "Left")``
      ``"Ctrl+Alt+T"`` → ``ParsedHotkey(ControlMask|Mod1Mask, "t")``
      ``"F11"`` → ``ParsedHotkey(0, "F11")``

    Raises :class:`HotkeyParseError` for empty strings, unknown modifiers,
    or accelerators that encode more than one non-modifier key.
    """
    if not accel:
        raise HotkeyParseError("empty accelerator")
    # "+" is both the separator and a key name. Qt writes that key as a
    # trailing "+", which splits to two empty trailing fields ("Ctrl++" →
    # ["Ctrl", "", ""]). A single empty field is a dangling separator and
    # stays an error.
    raw_parts = accel.split("+")
    literal_plus = raw_parts[-2:] == ["", ""]
    if literal_plus:
        raw_parts = raw_parts[:-2]
    parts = [p.strip() for p in raw_parts if p.strip()]
    if not (parts or literal_plus):
        raise HotkeyParseError(f"empty accelerator: {accel!r}")

    mods = 0
    key_parts: list[str] = ["+"] if literal_plus else []
    for token in parts:
        lowered = token.lower()
        if lowered in _MOD_PORTABLE_TO_X:
            mods |= _MOD_PORTABLE_TO_X[lowered]
        else:
            key_parts.append(token)
    if len(key_parts) != 1:
        raise HotkeyParseError(
            f"expected exactly one non-modifier key in {accel!r}, got {key_parts!r}"
        )
    return ParsedHotkey(
        modifiers=mods, keysym_name=_resolve_keysym_name(key_parts[0], mods)
    )


def _resolve_keysym_name(raw_key: str, mods: int) -> str:
    """Map one PortableText key name onto its X11 keysym name."""
    name = _KEY_ALIASES.get(raw_key)
    if name is not None:
        return name
    if len(raw_key) == 1 and raw_key.isalpha():
        # X11 keysyms are case-sensitive; a lone letter key in Qt is
        # capitalised ("A") even when Shift is absent. Map to lowercase
        # keysym — Shift is already in the modifier mask when the user
        # intends the shifted variant.
        return raw_key.lower() if (mods & _X.ShiftMask) == 0 else raw_key
    return raw_key


# ── NumLock mask discovery ─────────────────────────────────────────────────


def _mask_for_keysym(display: Display, keysym_name: str) -> int:
    """Return the mod mask carrying ``keysym_name``, or 0 if it carries none.

    Walks the modifier map (``d.get_modifier_mapping()``) looking for the
    keysym's keycode. Mod bits Mod1..Mod5 live at indices 3..7 of the
    mapping; Shift (0), Lock (1), Control (2) can never carry a lock key
    other than CapsLock and are skipped.
    """
    target = int(display.keysym_to_keycode(XK.string_to_keysym(keysym_name)))
    if target == 0:
        return 0
    mapping = display.get_modifier_mapping()
    for idx in range(3, 8):
        if target in mapping[idx]:
            return 1 << idx
    return 0


def compute_numlock_mask(display: Display) -> int:
    """Return the X11 mod mask that corresponds to NumLock, or 0 if none."""
    return _mask_for_keysym(display, "Num_Lock")


def compute_scrolllock_mask(display: Display) -> int:
    """Return the X11 mod mask that corresponds to ScrollLock, or 0 if none.

    ScrollLock is bound far less consistently than NumLock — often nowhere
    at all, which is what the 0 means. It matters because a lock bit left
    set silently changes ``KeyPress.state``, and a grab that does not cover
    it never fires.
    """
    return _mask_for_keysym(display, "Scroll_Lock")


# ── Grab / ungrab fan-out ──────────────────────────────────────────────────


def _lock_masks(numlock: int, scrolllock: int = 0) -> frozenset[int]:
    """Every combination of lock bits we need to cover per grab.

    CapsLock, NumLock and ScrollLock can each be latched independently, so
    the fan-out is the power set of the three bits — eight grabs where all
    three are bound, fewer when a bit resolves to 0 and the set collapses.
    """
    masks = {0}
    for bit in (_X.LockMask, numlock, scrolllock):
        if bit:
            masks |= {m | bit for m in masks}
    return frozenset(masks)


class HotkeyBusyError(Exception):
    """Another client has the same grab — surfaced to the user UI.

    Does not subclass :class:`Xlib.error.BadAccess` on purpose: ``BadAccess``
    is untyped in python-xlib (all X errors have ``type: Any`` stubs), and
    subclassing it pollutes the error taxonomy here with :class:`Any`.
    Callers catch ``BackendUnsupported`` in practice; this internal type is
    the bridge between the raw X error and that public surface.
    """


def grab_hotkey(
    display: Display, parsed: ParsedHotkey, numlock: int, scrolllock: int = 0
) -> int:
    """Install an ``XGrabKey`` and return the keycode for later ungrab.

    Raises :class:`HotkeyParseError` if the keysym has no keycode on the
    current layout, and :class:`HotkeyBusyError` if another client already
    owns the grab.
    """
    keysym = XK.string_to_keysym(parsed.keysym_name)
    if keysym == 0:
        raise HotkeyParseError(f"unknown keysym: {parsed.keysym_name!r}")
    keycode = int(display.keysym_to_keycode(keysym))
    if keycode == 0:
        raise HotkeyParseError(
            f"keysym {parsed.keysym_name!r} has no keycode on the current layout"
        )

    root = display.screen().root
    catch = _xerror.CatchError(_xerror.BadAccess)
    for extra in _lock_masks(numlock, scrolllock):
        root.grab_key(
            keycode,
            parsed.modifiers | extra,
            1,  # owner_events
            _X.GrabModeAsync,
            _X.GrabModeAsync,
            onerror=catch,
        )
    # Force the async errors to materialise so we can detect BadAccess before
    # telling the user "hotkey registered" incorrectly.
    display.sync()
    err = catch.get_error()
    if err is not None:
        # Undo the partial grabs we might have installed.
        _ungrab_locks(display, keycode, parsed.modifiers, numlock, scrolllock)
        raise HotkeyBusyError(
            f"grab_key BadAccess for {parsed!r}; another client owns it"
        )
    return keycode


def ungrab_hotkey(
    display: Display,
    keycode: int,
    modifiers: int,
    numlock: int,
    scrolllock: int = 0,
) -> None:
    """Remove every lock-mask variant of a previous grab."""
    _ungrab_locks(display, keycode, modifiers, numlock, scrolllock)
    display.flush()


def _ungrab_locks(
    display: Display,
    keycode: int,
    modifiers: int,
    numlock: int,
    scrolllock: int = 0,
) -> None:
    root = display.screen().root
    for extra in _lock_masks(numlock, scrolllock):
        root.ungrab_key(keycode, modifiers | extra)


def normalise_modifier_state(
    state: int, numlock: int, scrolllock: int = 0
) -> int:
    """Strip lock bits from a KeyPress ``state`` for table lookup.

    Lock bits vary with CapsLock / NumLock state and should never be part
    of the "what modifier set was held?" question.
    """
    return int(state & ~(_X.LockMask | numlock | scrolllock))
