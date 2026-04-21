"""Modal editor for a single layout / profile-override entry.

A layout entry is a ``(match, apply)`` pair; the apply block can carry
``geometry``, ``snap``, ``monitor``, ``desktop``, and ``maximized``.
The editor composes the existing :class:`MatchEditor` and
:class:`GeometryEditor` widgets with a small "Placement" group for the
remaining scalar fields, and returns a fully-parsed :class:`LayoutEntry`
on accept.

Users pick *one* of the two placement mechanisms (geometry or snap) —
the dialog's radio buttons enforce the same exclusivity rule the TOML
parser applies at load time (``docs/07-rules-engine.md`` §Validation).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from perch.core.actions import (
    BUILTIN_PRESETS,
    ApplyAction,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.layouts import LayoutEntry
from perch.core.matching import MatchPattern

from .widgets import GeometryEditor, MatchEditor


class EntryEditorDialog(QDialog):
    """Modal dialog to add or edit a :class:`LayoutEntry`."""

    def __init__(
        self,
        entry: LayoutEntry | None = None,
        *,
        user_snaps: tuple[str, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Edit entry") if entry is not None else self.tr("Add entry")
        )
        self.resize(520, 620)

        # ── Match editor ───────────────────────────────────────────────
        match_group = QGroupBox(self.tr("Match"))
        match_layout = QVBoxLayout(match_group)
        self.match_editor = MatchEditor(parent=self)
        match_layout.addWidget(self.match_editor)

        # ── Placement (geometry XOR snap) ──────────────────────────────
        placement_group = QGroupBox(self.tr("Placement"))
        placement_layout = QVBoxLayout(placement_group)

        mode_row = QHBoxLayout()
        self.geometry_radio = QRadioButton(self.tr("Geometry"))
        self.snap_radio = QRadioButton(self.tr("Snap preset"))
        self.none_radio = QRadioButton(self.tr("None"))
        self.geometry_radio.setChecked(True)
        mode_row.addWidget(self.geometry_radio)
        mode_row.addWidget(self.snap_radio)
        mode_row.addWidget(self.none_radio)
        mode_row.addStretch(1)
        placement_layout.addLayout(mode_row)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self.geometry_radio)
        mode_group.addButton(self.snap_radio)
        mode_group.addButton(self.none_radio)

        self.placement_stack = QStackedWidget(self)
        self.geometry_editor = GeometryEditor(parent=self)
        # Layout entries frequently want snap presets; expose them so
        # Preset mode's combo matches what the [snaps] section defines.
        if user_snaps:
            self.geometry_editor.add_user_presets(user_snaps)
        self.placement_stack.addWidget(self.geometry_editor)

        snap_page = QWidget(self)
        snap_form = QFormLayout(snap_page)
        self.snap_combo = QComboBox()
        for preset_name in BUILTIN_PRESETS:
            self.snap_combo.addItem(preset_name, preset_name)
        for user_snap in user_snaps:
            self.snap_combo.addItem(user_snap, user_snap)
        snap_form.addRow(self.tr("Snap preset:"), self.snap_combo)
        self.placement_stack.addWidget(snap_page)

        none_page = QWidget(self)
        none_layout = QVBoxLayout(none_page)
        none_hint = QLabel(
            self.tr(
                "No placement — the entry sets monitor / desktop / "
                "maximized only."
            )
        )
        none_hint.setWordWrap(True)
        none_layout.addWidget(none_hint)
        none_layout.addStretch(1)
        self.placement_stack.addWidget(none_page)

        placement_layout.addWidget(self.placement_stack, 1)

        self.geometry_radio.toggled.connect(self._on_mode_changed)
        self.snap_radio.toggled.connect(self._on_mode_changed)
        self.none_radio.toggled.connect(self._on_mode_changed)

        # ── Monitor / desktop / maximized ──────────────────────────────
        extras_group = QGroupBox(self.tr("Also set"))
        extras_form = QFormLayout(extras_group)
        self.monitor_edit = QLineEdit()
        self.monitor_edit.setPlaceholderText(
            self.tr("output name, 'primary', 'current', or integer index")
        )
        extras_form.addRow(self.tr("Monitor:"), self.monitor_edit)

        self.desktop_edit = QLineEdit()
        self.desktop_edit.setPlaceholderText(
            self.tr("integer desktop index, 'current', or 'all'")
        )
        extras_form.addRow(self.tr("Desktop:"), self.desktop_edit)

        # Maximized is tri-state: unset / true / false.
        self.maximized_combo = QComboBox()
        self.maximized_combo.addItem(self.tr("unset"), None)
        self.maximized_combo.addItem(self.tr("true"), True)
        self.maximized_combo.addItem(self.tr("false"), False)
        extras_form.addRow(self.tr("Maximized:"), self.maximized_combo)

        # ── Button row ─────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(match_group, 1)
        root.addWidget(placement_group, 1)
        root.addWidget(extras_group)
        root.addWidget(buttons)

        if entry is not None:
            self._load(entry)

    # ── Loading ─────────────────────────────────────────────────────────
    def _load(self, entry: LayoutEntry) -> None:
        self.match_editor.set_pattern(entry.match)
        action = entry.apply
        if action.geometry is not None:
            self.geometry_radio.setChecked(True)
            self.geometry_editor.set_value(action.geometry)
        elif action.snap is not None:
            self.snap_radio.setChecked(True)
            idx = self.snap_combo.findData(action.snap)
            if idx < 0:
                self.snap_combo.addItem(action.snap, action.snap)
                idx = self.snap_combo.findData(action.snap)
            self.snap_combo.setCurrentIndex(idx)
        else:
            self.none_radio.setChecked(True)

        if action.monitor is not None:
            self.monitor_edit.setText(str(action.monitor))
        if action.desktop is not None:
            self.desktop_edit.setText(str(action.desktop))
        idx = self.maximized_combo.findData(action.maximized)
        if idx >= 0:
            self.maximized_combo.setCurrentIndex(idx)
        self._on_mode_changed()

    # ── Mode switching ──────────────────────────────────────────────────
    def _on_mode_changed(self) -> None:
        if self.geometry_radio.isChecked():
            self.placement_stack.setCurrentIndex(0)
        elif self.snap_radio.isChecked():
            self.placement_stack.setCurrentIndex(1)
        else:
            self.placement_stack.setCurrentIndex(2)

    # ── Accept ──────────────────────────────────────────────────────────
    def _on_accept(self) -> None:
        try:
            entry = self.value()
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Invalid entry"), str(exc))
            return
        self._entry = entry
        self.accept()

    def value(self) -> LayoutEntry:
        """Return a validated :class:`LayoutEntry` from the current fields.

        Raises :class:`ValueError` when:

        * The match pattern is empty (would match everything) and
          ``catch_all`` isn't set — the parser would reject it on load.
        * ``pid`` / ``title`` field errors are still outstanding.
        * ``maximized=True`` is combined with geometry/snap.
        """
        pattern = self.match_editor.value()
        if pattern.is_empty() and not pattern.catch_all:
            raise ValueError(
                self.tr(
                    "match is empty — set at least one field or enable "
                    "catch-all."
                )
            )

        geometry = None
        snap: str | None = None
        if self.geometry_radio.isChecked():
            geometry = self.geometry_editor.value()
        elif self.snap_radio.isChecked():
            data = self.snap_combo.currentData()
            if isinstance(data, str) and data:
                snap = data

        monitor_text = self.monitor_edit.text().strip()
        monitor: str | int | None = None
        if monitor_text:
            try:
                monitor = int(monitor_text)
            except ValueError:
                monitor = monitor_text

        desktop_text = self.desktop_edit.text().strip()
        desktop: str | int | None = None
        if desktop_text:
            try:
                desktop = int(desktop_text)
            except ValueError:
                desktop = desktop_text

        maximized: bool | None = self.maximized_combo.currentData()

        if maximized is True and (geometry is not None or snap is not None):
            raise ValueError(
                self.tr(
                    "maximized=true cannot be combined with an explicit "
                    "geometry or snap preset."
                )
            )

        if (
            geometry is None
            and snap is None
            and monitor is None
            and desktop is None
            and maximized is None
        ):
            raise ValueError(
                self.tr(
                    "entry has no effect — set at least one of geometry, "
                    "snap, monitor, desktop, or maximized."
                )
            )

        action = ApplyAction(
            geometry=geometry,
            snap=snap,
            monitor=monitor,
            desktop=desktop,
            maximized=maximized,
        )
        return LayoutEntry(match=pattern, apply=action)


def summarise_match(pattern: MatchPattern) -> str:
    """Human-readable one-line summary of a match pattern."""
    parts: list[str] = []
    if pattern.catch_all:
        parts.append("catch_all")
    if pattern.app_id:
        parts.append(f"app_id={pattern.app_id}")
    if pattern.wm_class:
        parts.append(f"wm_class={pattern.wm_class}")
    if pattern.title is not None:
        parts.append(f"title=~{pattern.title.pattern}")
    if pattern.pid is not None:
        parts.append(f"pid={pattern.pid}")
    if pattern.types:
        parts.append("type=" + ",".join(t.value for t in pattern.types))
    return " ".join(parts) or "<empty>"


def summarise_apply(action: ApplyAction) -> str:
    """Human-readable one-line summary of an apply action."""
    parts: list[str] = []
    if action.geometry is not None:
        if isinstance(action.geometry, PresetGeometry):
            parts.append(f"preset:{action.geometry.name}")
        elif isinstance(action.geometry, PercentGeometry):
            parts.append(
                f"pct:{action.geometry.w_pct * 100:.0f}%x{action.geometry.h_pct * 100:.0f}%"
            )
        else:
            parts.append(
                f"abs:{action.geometry.w}x{action.geometry.h}"
                f"@{action.geometry.x},{action.geometry.y}"
            )
    if action.snap is not None:
        parts.append(f"snap:{action.snap}")
    if action.monitor is not None:
        parts.append(f"mon:{action.monitor}")
    if action.desktop is not None:
        parts.append(f"desktop:{action.desktop}")
    if action.maximized is not None:
        parts.append(f"max:{'yes' if action.maximized else 'no'}")
    return " ".join(parts) or "<empty>"


