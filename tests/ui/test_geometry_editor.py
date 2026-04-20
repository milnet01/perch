"""GeometryEditor widget tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from perch.core.actions import (
    AbsoluteGeometry,
    PercentGeometry,
    PresetGeometry,
)
from perch.ui.widgets.geometry_editor import (
    MODE_ABSOLUTE,
    MODE_PERCENT,
    MODE_PRESET,
    GeometryEditor,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_default_mode_is_absolute_with_zero_values(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    value = editor.value()
    assert isinstance(value, AbsoluteGeometry)
    assert value.x == 0 and value.y == 0
    assert value.w == 1 and value.h == 1  # min of the width/height spin


def test_set_value_round_trips_absolute_geometry(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    expr = AbsoluteGeometry(100, 200, 800, 600)
    editor.set_value(expr)
    assert editor.mode_combo.currentData() == MODE_ABSOLUTE
    assert editor.value() == expr


def test_set_value_round_trips_percent_geometry(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    expr = PercentGeometry(0.0, 0.0, 0.5, 1.0)
    editor.set_value(expr)
    assert editor.mode_combo.currentData() == MODE_PERCENT
    got = editor.value()
    assert isinstance(got, PercentGeometry)
    assert got.x_pct == 0.0
    assert got.y_pct == 0.0
    assert got.w_pct == 0.5
    assert got.h_pct == 1.0


def test_set_value_round_trips_preset_geometry(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    expr = PresetGeometry("left-half")
    editor.set_value(expr)
    assert editor.mode_combo.currentData() == MODE_PRESET
    assert editor.value() == expr


def test_unknown_preset_name_is_preserved(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    expr = PresetGeometry("my-custom-preset")
    editor.set_value(expr)
    assert editor.value() == expr


def test_value_changed_fires_on_spinbox_edit(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    with qtbot.waitSignal(editor.valueChanged, timeout=500):
        editor.abs_w.setValue(1280)
    got = editor.value()
    assert isinstance(got, AbsoluteGeometry)
    assert got.w == 1280


def test_mode_switch_fires_value_changed(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    with qtbot.waitSignal(editor.valueChanged, timeout=500):
        editor.mode_combo.setCurrentIndex(1)  # percent
    assert isinstance(editor.value(), PercentGeometry)


def test_add_user_presets_appends_without_duplicates(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    original_count = editor.preset_combo.count()
    editor.add_user_presets(["custom-1", "custom-2"])
    editor.add_user_presets(["custom-1"])  # duplicate
    assert editor.preset_combo.count() == original_count + 2
    names = [
        editor.preset_combo.itemData(i)
        for i in range(editor.preset_combo.count())
    ]
    assert names.count("custom-1") == 1


def test_percent_values_clamped_to_monitor_range(qtbot: QtBot) -> None:
    editor = GeometryEditor()
    qtbot.addWidget(editor)
    editor.mode_combo.setCurrentIndex(1)  # percent
    editor.pct_w.setValue(150.0)  # beyond 100%
    got = editor.value()
    assert isinstance(got, PercentGeometry)
    assert got.w_pct == 1.0  # clamped at 100% by the QDoubleSpinBox range
