"""Match-pattern editor widget.

Edits a :class:`~perch.core.matching.MatchPattern`: ``app_id`` /
``wm_class`` globs, a ``title`` regex, an optional ``pid`` filter, a
set of ``type`` flags, and the ``catch_all`` escape hatch. See
``docs/07-rules-engine.md`` §Matching for the semantics.

Invalid regex / non-integer ``pid`` values are surfaced inline on the
offending field. The widget exposes :meth:`value` to return a fresh
``MatchPattern`` once validation passes — callers should check
:meth:`is_valid` before committing.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QWidget,
)

from perch.backend.types import WindowType
from perch.core.matching import MatchPattern


class MatchEditor(QWidget):
    """Compose / edit a :class:`MatchPattern`.

    Widget-field → pattern-field mapping::

        app_id        → MatchPattern.app_id    (glob, optional)
        wm_class      → MatchPattern.wm_class  (glob, optional)
        title         → MatchPattern.title     (regex, optional)
        pid           → MatchPattern.pid       (int, optional)
        types check-grid → MatchPattern.types  (tuple of WindowType)
        catch_all     → MatchPattern.catch_all (bool)

    Emits :attr:`valueChanged` whenever any field changes so dialogs
    can dirty-track; :attr:`validityChanged` fires when the overall
    validity of the compound value flips.
    """

    valueChanged = Signal()
    validityChanged = Signal(bool)

    def __init__(
        self,
        pattern: MatchPattern | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.app_id_edit = QLineEdit(self)
        self.app_id_edit.setPlaceholderText(
            self.tr("firefox, org.kde.Konsole*, …")
        )

        self.wm_class_edit = QLineEdit(self)
        self.wm_class_edit.setPlaceholderText(self.tr("Firefox, Plasma*, …"))

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText(
            self.tr("Python regex (searched, not anchored)")
        )

        self.pid_edit = QLineEdit(self)
        self.pid_edit.setPlaceholderText(self.tr("Integer PID (optional)"))

        self.type_checkboxes: dict[WindowType, QCheckBox] = {}
        types_grid = QGridLayout()
        types_grid.setContentsMargins(0, 0, 0, 0)
        for i, wt in enumerate(WindowType):
            cb = QCheckBox(wt.value, self)
            cb.toggled.connect(self._on_field_changed)
            self.type_checkboxes[wt] = cb
            types_grid.addWidget(cb, i // 3, i % 3)
        types_container = QWidget(self)
        types_container.setLayout(types_grid)

        self.catch_all_checkbox = QCheckBox(
            "Match every window (catch_all)", self
        )

        form = QFormLayout(self)
        form.addRow("app_id", self.app_id_edit)
        form.addRow("wm_class", self.wm_class_edit)
        form.addRow("title regex", self.title_edit)
        form.addRow("pid", self.pid_edit)
        form.addRow("type", types_container)
        form.addRow(self.catch_all_checkbox)

        for edit in (
            self.app_id_edit,
            self.wm_class_edit,
            self.title_edit,
            self.pid_edit,
        ):
            edit.textChanged.connect(self._on_field_changed)
        self.catch_all_checkbox.toggled.connect(self._on_field_changed)

        self._last_validity: bool = True
        if pattern is not None:
            self.set_pattern(pattern)

    # ── Public API ──────────────────────────────────────────────────────
    def set_pattern(self, pattern: MatchPattern) -> None:
        """Replace every field from ``pattern`` without re-emitting signals."""
        with _block(self):
            self.app_id_edit.setText(pattern.app_id or "")
            self.wm_class_edit.setText(pattern.wm_class or "")
            self.title_edit.setText(
                pattern.title.pattern if pattern.title is not None else ""
            )
            self.pid_edit.setText(
                str(pattern.pid) if pattern.pid is not None else ""
            )
            selected = set(pattern.types)
            for wt, cb in self.type_checkboxes.items():
                cb.setChecked(wt in selected)
            self.catch_all_checkbox.setChecked(pattern.catch_all)
        self._emit_validity_change()

    def is_valid(self) -> bool:
        """Return True if the current field values compose a valid pattern."""
        return (
            self._title_regex_error() is None
            and self._pid_error() is None
        )

    def value(self) -> MatchPattern:
        """Return the current :class:`MatchPattern`.

        Raises :class:`ValueError` if the current fields do not compose
        a valid pattern; callers should guard with :meth:`is_valid`.
        """
        err = self._title_regex_error()
        if err is not None:
            raise ValueError(f"title regex: {err}")
        err = self._pid_error()
        if err is not None:
            raise ValueError(f"pid: {err}")

        title_text = self.title_edit.text()
        title = re.compile(title_text) if title_text else None

        pid_text = self.pid_edit.text().strip()
        pid = int(pid_text) if pid_text else None

        selected_types = tuple(
            wt for wt, cb in self.type_checkboxes.items() if cb.isChecked()
        )

        return MatchPattern(
            app_id=self.app_id_edit.text() or None,
            wm_class=self.wm_class_edit.text() or None,
            title=title,
            pid=pid,
            types=selected_types,
            catch_all=self.catch_all_checkbox.isChecked(),
        )

    # ── Field validation helpers ────────────────────────────────────────
    def _title_regex_error(self) -> str | None:
        text = self.title_edit.text()
        if not text:
            return None
        try:
            re.compile(text)
        except re.error as exc:
            return str(exc)
        return None

    def _pid_error(self) -> str | None:
        text = self.pid_edit.text().strip()
        if not text:
            return None
        try:
            value = int(text)
        except ValueError:
            return "not an integer"
        if value < 0:
            return "must be non-negative"
        return None

    # ── Signal plumbing ─────────────────────────────────────────────────
    def _on_field_changed(self, *_: object) -> None:
        self._paint_validation()
        self.valueChanged.emit()
        self._emit_validity_change()

    def _paint_validation(self) -> None:
        """Annotate the title / pid edits with tooltips on invalid input."""
        err = self._title_regex_error()
        self.title_edit.setToolTip(err or "")
        self.title_edit.setProperty("perch_invalid", err is not None)

        err = self._pid_error()
        self.pid_edit.setToolTip(err or "")
        self.pid_edit.setProperty("perch_invalid", err is not None)

    def _emit_validity_change(self) -> None:
        new_validity = self.is_valid()
        if new_validity != self._last_validity:
            self._last_validity = new_validity
            self.validityChanged.emit(new_validity)


class _block:
    """Context manager: block ``valueChanged`` while set_pattern refreshes."""

    def __init__(self, widget: MatchEditor) -> None:
        self._widget = widget
        self._children = (
            widget.app_id_edit,
            widget.wm_class_edit,
            widget.title_edit,
            widget.pid_edit,
            widget.catch_all_checkbox,
            *widget.type_checkboxes.values(),
        )

    def __enter__(self) -> None:
        for child in self._children:
            child.blockSignals(True)

    def __exit__(self, *_exc: object) -> None:
        for child in self._children:
            child.blockSignals(False)
