"""Geometry-expression editor widget.

Edits a :class:`~perch.core.actions.GeometryExpr` — one of
:class:`AbsoluteGeometry`, :class:`PercentGeometry`, or
:class:`PresetGeometry`. See ``docs/02-state-format.md`` §Apply actions
for the semantics.

The widget uses a mode combo to switch between the three variants and
shows only the editable fields for the active mode:

* **Absolute** — four ``QSpinBox`` (x, y, w, h) in pixels.
* **Percent** — four ``QDoubleSpinBox`` (x%, y%, w%, h%) as percentages
  of the monitor's work area, 0-100.
* **Preset** — a combo of built-in names from
  :data:`~perch.core.actions.BUILTIN_PRESETS`. User-defined presets from
  ``[snaps]`` can be appended via :meth:`add_user_presets`.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from perch.core.actions import (
    BUILTIN_PRESETS,
    AbsoluteGeometry,
    GeometryExpr,
    PercentGeometry,
    PresetGeometry,
)

MODE_ABSOLUTE = "absolute"
MODE_PERCENT = "percent"
MODE_PRESET = "preset"


class GeometryEditor(QWidget):
    """Edit a :class:`GeometryExpr` across absolute / percent / preset modes."""

    valueChanged = Signal()

    def __init__(
        self,
        expr: GeometryExpr | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("Absolute (px)", MODE_ABSOLUTE)
        self.mode_combo.addItem("Percent (%)", MODE_PERCENT)
        self.mode_combo.addItem("Preset", MODE_PRESET)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._build_absolute_page())
        self.stack.addWidget(self._build_percent_page())
        self.stack.addWidget(self._build_preset_page())

        root = QVBoxLayout(self)
        root_form = QFormLayout()
        root_form.addRow("Mode", self.mode_combo)
        root.addLayout(root_form)
        root.addWidget(self.stack, 1)

        if expr is not None:
            self.set_value(expr)

    # ── Mode pages ──────────────────────────────────────────────────────
    def _build_absolute_page(self) -> QWidget:
        page = QWidget(self)
        layout = QFormLayout(page)
        # Pixel geometry is clamped to the monitor's work area at apply
        # time so the UI doesn't need a hard upper bound; a generous max
        # covers 8K-plus displays without ever rejecting a legitimate
        # value.
        self.abs_x = self._make_spin(-65535, 65535)
        self.abs_y = self._make_spin(-65535, 65535)
        self.abs_w = self._make_spin(1, 65535)
        self.abs_h = self._make_spin(1, 65535)
        layout.addRow("x", self.abs_x)
        layout.addRow("y", self.abs_y)
        layout.addRow("w", self.abs_w)
        layout.addRow("h", self.abs_h)
        return page

    def _build_percent_page(self) -> QWidget:
        page = QWidget(self)
        layout = QFormLayout(page)
        self.pct_x = self._make_pct_spin()
        self.pct_y = self._make_pct_spin()
        self.pct_w = self._make_pct_spin(default=100.0)
        self.pct_h = self._make_pct_spin(default=100.0)
        layout.addRow("x %", self.pct_x)
        layout.addRow("y %", self.pct_y)
        layout.addRow("w %", self.pct_w)
        layout.addRow("h %", self.pct_h)
        return page

    def _build_preset_page(self) -> QWidget:
        page = QWidget(self)
        row = QHBoxLayout(page)
        self.preset_combo = QComboBox(page)
        for name in BUILTIN_PRESETS:
            self.preset_combo.addItem(name, name)
        self.preset_combo.currentIndexChanged.connect(self._emit_changed)
        row.addWidget(QLabel("Name", page))
        row.addWidget(self.preset_combo, 1)
        return page

    # ── Public API ──────────────────────────────────────────────────────
    def add_user_presets(self, names: Iterable[str]) -> None:
        """Append user-defined preset names after the built-ins."""
        existing = {self.preset_combo.itemData(i) for i in range(self.preset_combo.count())}
        for name in names:
            if name not in existing:
                self.preset_combo.addItem(name, name)

    def set_value(self, expr: GeometryExpr) -> None:
        """Switch the mode + field values to reflect ``expr``."""
        self.blockSignals(True)
        try:
            if isinstance(expr, AbsoluteGeometry):
                self.mode_combo.setCurrentIndex(0)
                self.abs_x.setValue(expr.x)
                self.abs_y.setValue(expr.y)
                self.abs_w.setValue(expr.w)
                self.abs_h.setValue(expr.h)
            elif isinstance(expr, PercentGeometry):
                self.mode_combo.setCurrentIndex(1)
                self.pct_x.setValue(expr.x_pct * 100.0)
                self.pct_y.setValue(expr.y_pct * 100.0)
                self.pct_w.setValue(expr.w_pct * 100.0)
                self.pct_h.setValue(expr.h_pct * 100.0)
            elif isinstance(expr, PresetGeometry):
                self.mode_combo.setCurrentIndex(2)
                idx = self.preset_combo.findData(expr.name)
                if idx < 0:
                    # Unknown preset name — add it so round-trip preserves
                    # it. The rules-engine will reject unknown names at
                    # apply time.
                    self.preset_combo.addItem(expr.name, expr.name)
                    idx = self.preset_combo.findData(expr.name)
                self.preset_combo.setCurrentIndex(idx)
            else:
                raise TypeError(f"unsupported geometry expression: {type(expr).__name__}")
            self.stack.setCurrentIndex(self.mode_combo.currentIndex())
        finally:
            self.blockSignals(False)

    def value(self) -> GeometryExpr:
        """Return the current :class:`GeometryExpr`."""
        mode = self.mode_combo.currentData()
        if mode == MODE_ABSOLUTE:
            return AbsoluteGeometry(
                x=self.abs_x.value(),
                y=self.abs_y.value(),
                w=self.abs_w.value(),
                h=self.abs_h.value(),
            )
        if mode == MODE_PERCENT:
            return PercentGeometry(
                x_pct=self.pct_x.value() / 100.0,
                y_pct=self.pct_y.value() / 100.0,
                w_pct=self.pct_w.value() / 100.0,
                h_pct=self.pct_h.value() / 100.0,
            )
        return PresetGeometry(name=self.preset_combo.currentData())

    # ── Internal helpers ────────────────────────────────────────────────
    def _make_spin(self, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.valueChanged.connect(self._emit_changed)
        return spin

    def _make_pct_spin(self, default: float = 0.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(5.0)
        spin.setSuffix(" %")
        spin.setValue(default)
        spin.valueChanged.connect(self._emit_changed)
        return spin

    def _on_mode_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self._emit_changed()

    def _emit_changed(self, *_: object) -> None:
        self.valueChanged.emit()
