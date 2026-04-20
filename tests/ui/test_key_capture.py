"""HotkeyEdit widget + portable↔XDG translator tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence

from perch.ui.widgets.key_capture import (
    HotkeyEdit,
    portable_to_xdg,
    xdg_to_portable,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── HotkeyEdit ──────────────────────────────────────────────────────────


def test_default_accel_is_empty_string(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    assert widget.accel() == ""


def test_set_accel_loads_portable_text(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    widget.set_accel("Meta+Left")
    assert widget.accel() == "Meta+Left"


def test_set_accel_empty_clears(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    widget.set_accel("Ctrl+A")
    widget.set_accel("")
    assert widget.accel() == ""


def test_maximum_sequence_length_is_one(qtbot: QtBot) -> None:
    """Perch accelerators are single chords, not multi-key sequences."""
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    assert widget.maximumSequenceLength() == 1


def test_clear_button_is_enabled(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    assert widget.isClearButtonEnabled()


def test_setting_valid_chord_emits_accel_changed(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    with qtbot.waitSignal(widget.accelChanged, timeout=500) as sig:
        widget.setKeySequence(QKeySequence("Ctrl+A"))
    assert sig.args == ["Ctrl+A"]


def test_bare_printable_key_is_rejected(qtbot: QtBot) -> None:
    """Bare ``A`` (no modifier) is not a valid global hotkey."""
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    # setKeySequence fires keySequenceChanged → _on_sequence_changed
    # clears the sequence when modifier_bits == 0 and it's not a
    # function key. The final state is empty.
    widget.setKeySequence(QKeySequence("A"))
    assert widget.accel() == ""


def test_function_key_without_modifier_is_accepted(qtbot: QtBot) -> None:
    """F11 / F12 are legitimate unmodified global hotkeys."""
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    widget.setKeySequence(QKeySequence("F11"))
    assert widget.accel() == "F11"


def test_wayland_super_keypress_is_filtered(qtbot: QtBot) -> None:
    """QTBUG-62102: bare Key_Super_L must not slip past into the sequence.

    On GNOME Wayland / wlroots the Super keysym arrives as Key_Super_L
    rather than Qt::Key_Meta. QKeySequenceEdit's built-in modifier-only
    guard keys off Qt::Key_Meta, so bare Super_L would otherwise get
    recorded as an unusable chord. The override in HotkeyEdit filters
    it.
    """
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Super_L,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.keyPressEvent(event)
    # The press was accepted but nothing entered the sequence.
    assert event.isAccepted()
    assert widget.accel() == ""


def test_wayland_hyper_keypress_is_filtered(qtbot: QtBot) -> None:
    widget = HotkeyEdit()
    qtbot.addWidget(widget)
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Hyper_L,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.keyPressEvent(event)
    assert event.isAccepted()
    assert widget.accel() == ""


# ── portable_to_xdg / xdg_to_portable ───────────────────────────────────


def test_portable_to_xdg_maps_meta_to_logo() -> None:
    assert portable_to_xdg("Meta+Left") == "LOGO+Left"


def test_portable_to_xdg_maps_ctrl_alt_shift_uppercase() -> None:
    assert portable_to_xdg("Ctrl+Alt+Shift+T") == "CTRL+ALT+SHIFT+T"


def test_portable_to_xdg_preserves_key_name_case() -> None:
    # xkbcommon-style key names already line up with Qt's for the common
    # cases (Left, Return, printable letters). Only modifiers change case.
    assert portable_to_xdg("Meta+Return") == "LOGO+Return"


def test_portable_to_xdg_empty_string_is_empty() -> None:
    assert portable_to_xdg("") == ""


def test_xdg_to_portable_round_trip() -> None:
    accel = "Meta+Shift+F11"
    assert xdg_to_portable(portable_to_xdg(accel)) == accel


def test_xdg_to_portable_handles_empty() -> None:
    assert xdg_to_portable("") == ""
