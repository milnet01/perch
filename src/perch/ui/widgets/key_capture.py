"""Hotkey-capture widget.

:class:`HotkeyEdit` is a thin :class:`QKeySequenceEdit` subclass pinned
to single-chord captures with a Clear button (Qt 6.4+ API). It filters
bare Super / Hyper key presses so modifier-only presses never make it into
a sequence on GNOME Wayland and wlroots-derived compositors, where the
Meta / Super key arrives as ``Key_Super_L`` rather than
``Qt::Key_Meta`` (QTBUG-62102; KWin patches this at the compositor
level, other Wayland stacks do not).

Emits :attr:`accelChanged` with the sequence in
``QKeySequence.PortableText`` form (``"Meta+Left"``, ``"Ctrl+Alt+T"``)
or the empty string when cleared. Portable Text is the internal
format; a backend that needs another form translates at its own
transport boundary (see ``docs/03-backend-interface.md`` §Hotkey
accelerators).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit, QWidget

_SUPER_KEYS: frozenset[Qt.Key] = frozenset(
    {
        Qt.Key.Key_Super_L,
        Qt.Key.Key_Super_R,
        Qt.Key.Key_Hyper_L,
        Qt.Key.Key_Hyper_R,
    }
)

_MODIFIER_MASK: int = int(
    Qt.KeyboardModifier.ControlModifier.value
    | Qt.KeyboardModifier.AltModifier.value
    | Qt.KeyboardModifier.MetaModifier.value
    | Qt.KeyboardModifier.ShiftModifier.value
)

# Function-key range we accept without a modifier (so users can bind
# ``F11`` / ``F12`` directly to Perch actions without forcing them to
# add a modifier they don't want).
_FUNCTION_KEY_MIN: int = int(Qt.Key.Key_F1)
_FUNCTION_KEY_MAX: int = int(Qt.Key.Key_F35)


def _combined_to_int(combo: object) -> int:
    """Extract the ``int`` form of a ``seq[0]`` result.

    PySide6 returns either a ``QKeyCombination`` (Qt 6.1+) or a raw
    ``int`` depending on the version. Both support ``int(x)``; this
    thin helper keeps the mypy suppression isolated to one line.
    """
    if hasattr(combo, "toCombined"):
        return int(combo.toCombined())
    return int(combo)  # type: ignore[call-overload,no-any-return]


class HotkeyEdit(QKeySequenceEdit):
    """Capture a single-chord hotkey with Wayland-Super correctness."""

    accelChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumSequenceLength(1)
        self.setClearButtonEnabled(True)
        self.keySequenceChanged.connect(self._on_sequence_changed)

    # ── Event filtering ─────────────────────────────────────────────────
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Drop bare Super / Hyper presses so modifier-only chords don't record.

        On Plasma Wayland KWin rewrites ``Super_L`` to ``Qt::Key_Meta``
        in its QKeyEvent pipeline (Phabricator D6828), but GNOME
        Wayland and wlroots-derived compositors pass the raw keysym
        through. ``QKeySequenceEdit``'s built-in modifier-only guard
        keys off ``Qt::Key_Meta``, so on those stacks a bare Super-key
        press would otherwise be recorded as an unusable chord.
        """
        if event.key() in _SUPER_KEYS:
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Value API ───────────────────────────────────────────────────────
    def accel(self) -> str:
        """Return the current accelerator in Portable Text form, or ``""``."""
        seq = self.keySequence()
        if seq.isEmpty():
            return ""
        return seq.toString(QKeySequence.SequenceFormat.PortableText)

    def set_accel(self, accel: str) -> None:
        """Load ``accel`` (Portable Text or empty) into the widget."""
        if not accel:
            self.clear()
            return
        seq = QKeySequence.fromString(
            accel, QKeySequence.SequenceFormat.PortableText
        )
        self.setKeySequence(seq)

    # ── Internals ───────────────────────────────────────────────────────
    def _on_sequence_changed(self, seq: QKeySequence) -> None:
        if seq.isEmpty():
            self.accelChanged.emit("")
            return
        # ``QKeySequence.__getitem__`` exists at runtime (returns a
        # ``QKeyCombination`` or int depending on the PySide6 version)
        # but its type stub is incomplete; keep the runtime access
        # behind an indirection so mypy sees ``int``.
        # ``seq[0]`` returns either a ``QKeyCombination`` (Qt 6.1+) or a
        # raw int depending on the PySide6 version. Both are callable
        # with ``int()`` via ``SupportsInt``; hide the version difference
        # behind a single integer extraction.
        key_int: int = _combined_to_int(seq[0])  # type: ignore[index]
        modifier_bits = key_int & _MODIFIER_MASK
        key_only = key_int & ~_MODIFIER_MASK
        is_function_key = _FUNCTION_KEY_MIN <= key_only <= _FUNCTION_KEY_MAX
        if modifier_bits == 0 and not is_function_key:
            # Bare printable key is not a valid global hotkey; reject.
            self.clear()
            return
        self.accelChanged.emit(
            seq.toString(QKeySequence.SequenceFormat.PortableText)
        )
