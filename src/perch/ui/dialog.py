"""Config dialog — QListWidget sidebar + QStackedWidget pages.

Layout per ``docs/08-ui.md`` §Config dialog. Pages:

* General — the four toggles / combo edit-and-save round-trip.
* Windows — live table of currently-open windows the active backend
  reports, with "Save as last-seen" / "Forget last-seen" actions that
  mutate :class:`~perch.core.state_store.StateStore`.
* Rules — drag-reorder + delete over :class:`RulesModel`.
* Layouts — per-layout entry editor using ``MatchEditor`` +
  ``GeometryEditor``.
* Profiles — per-profile topology + overrides editor reusing the
  layout-entry editor.
* Hotkeys — live :class:`HotkeyEdit` per snap preset; persists to
  ``config.toml`` and re-registers with the active backend on save.
* Exclusions — drag-reorder + delete.
* Import / Export — file-picker based config transfer with a dry-run
  diff panel.

Save path: the dialog holds the tomlkit :class:`TOMLDocument` parsed from
``config.toml`` at open time and mutates it via :mod:`perch.config.edit`.
``writer.write_document`` then performs the atomic-replace recipe. The
user's comments survive.
"""

from __future__ import annotations

import contextlib
import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from perch.backend.base import WindowBackend
from perch.backend.types import (
    DesktopIndex,
    Geometry,
    OutputName,
    WindowId,
    WindowInfo,
)
from perch.config import Config
from perch.config.edit import (
    ConfigEditError,
    add_layout,
    add_layout_entry,
    apply_general,
    delete_exclusion,
    delete_layout,
    delete_layout_entry,
    delete_rule,
    rename_layout,
    reorder_exclusions,
    reorder_rules,
    set_layout_description,
)
from perch.config.schema import VALID_THEMES
from perch.config.writer import load_document, write_document
from perch.core.identity import compute_identity
from perch.core.layouts import Layout, LayoutEntry
from perch.core.profiles import Profile, ProfileOverride
from perch.core.rules import Rule
from perch.core.state_store import StateStore

from .entry_editor import EntryEditorDialog, summarise_apply, summarise_match
from .rules_model import RulesModel
from .widgets import HotkeyEdit
from .windows_model import WindowsTableModel

log = logging.getLogger(__name__)


# ── Section identifiers (stable strings, used by the tray intent) ───────

SECTION_GENERAL = "general"
SECTION_WINDOWS = "windows"
SECTION_RULES = "rules"
SECTION_LAYOUTS = "layouts"
SECTION_PROFILES = "profiles"
SECTION_HOTKEYS = "hotkeys"
SECTION_EXCLUSIONS = "exclusions"
SECTION_IMPORT_EXPORT = "import_export"

SECTION_ORDER: tuple[str, ...] = (
    SECTION_GENERAL,
    SECTION_WINDOWS,
    SECTION_RULES,
    SECTION_LAYOUTS,
    SECTION_PROFILES,
    SECTION_HOTKEYS,
    SECTION_EXCLUSIONS,
    SECTION_IMPORT_EXPORT,
)


def _section_label(section: str) -> str:
    """Translated display label for a sidebar row."""
    context = "perch.ui.dialog"
    labels = {
        SECTION_GENERAL: QCoreApplication.translate(context, "General"),
        SECTION_WINDOWS: QCoreApplication.translate(context, "Windows"),
        SECTION_RULES: QCoreApplication.translate(context, "Rules"),
        SECTION_LAYOUTS: QCoreApplication.translate(context, "Layouts"),
        SECTION_PROFILES: QCoreApplication.translate(context, "Profiles"),
        SECTION_HOTKEYS: QCoreApplication.translate(context, "Hotkeys"),
        SECTION_EXCLUSIONS: QCoreApplication.translate(context, "Exclusions"),
        SECTION_IMPORT_EXPORT: QCoreApplication.translate(
            context, "Import / Export"
        ),
    }
    return labels[section]


# ── Working state held across edits ─────────────────────────────────────

@dataclass
class _DialogState:
    """Mutable state the dialog edits; committed to disk on Apply/OK."""

    config: Config
    document: Any  # tomlkit TOMLDocument; Any to keep this module test-importable
    # Tuple of the rules as they exist at open time. Committed pages
    # diff against it to compute deletes + reorders.
    original_rules: tuple[Rule, ...] = ()

    def __post_init__(self) -> None:
        self.original_rules = tuple(self.config.rules)


# ── Section pages ───────────────────────────────────────────────────────


class GeneralPage(QWidget):
    """The General section — four toggles and a theme combo."""

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._changed = False

        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self.start_at_login = QCheckBox(self.tr("Start Perch at login"))
        self.start_at_login.setChecked(state.config.general.start_at_login)
        self.start_at_login.toggled.connect(self._mark_changed)

        self.restore_on_open = QCheckBox(
            self.tr("Restore remembered geometry when a window reopens")
        )
        self.restore_on_open.setChecked(state.config.general.restore_on_open)
        self.restore_on_open.toggled.connect(self._mark_changed)

        self.notify_on_restore = QCheckBox(
            self.tr("Show a notification when Perch restores a window")
        )
        self.notify_on_restore.setChecked(
            state.config.general.notify_on_restore
        )
        self.notify_on_restore.toggled.connect(self._mark_changed)

        self.theme = QComboBox()
        for value in VALID_THEMES:
            self.theme.addItem(value, value)
        self.theme.setCurrentText(state.config.general.theme)
        self.theme.currentIndexChanged.connect(self._mark_changed)

        layout.addRow(self.start_at_login)
        layout.addRow(self.restore_on_open)
        layout.addRow(self.notify_on_restore)
        layout.addRow(self.tr("Theme:"), self.theme)

    def _mark_changed(self, *_: Any) -> None:
        self._changed = True

    def is_dirty(self) -> bool:
        return self._changed

    def commit(self) -> None:
        """Apply the page's state into the ``[general]`` table."""
        apply_general(
            self._state.document,
            start_at_login=self.start_at_login.isChecked(),
            restore_on_open=self.restore_on_open.isChecked(),
            notify_on_restore=self.notify_on_restore.isChecked(),
            theme=self.theme.currentData(),
        )
        self._changed = False


class WindowsPage(QWidget):
    """Live table of currently-open windows + last-seen actions.

    The backend's four lifecycle signals (``window_opened`` / ``_closed``
    / ``_changed`` / ``geometry_changed``) drive a
    :class:`WindowsTableModel`; ``backend.list_windows()`` seeds it when
    the page first becomes visible.

    Two row actions mutate :class:`StateStore`:

    * **Save as last-seen** — record the current geometry/monitor/desktop
      under the window's identity so the next reopen restores here.
    * **Forget last-seen** — drop the identity from ``state.json``.

    Both actions flip ``is_dirty()`` so the dialog's normal Apply/OK
    path flushes the state store; Cancel leaves it untouched.
    """

    def __init__(
        self,
        backend: WindowBackend | None,
        state_store: StateStore | None,
        config: Config | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._state_store = state_store
        # Live user-snap table, so the preset combo reflects the user's
        # named presets alongside the built-ins. When ``config`` is None
        # (tests) only the built-ins show.
        self._user_snaps: dict[str, Any] = (
            dict(config.snaps) if config is not None else {}
        )
        self._outputs_cache: dict[str, Any] = {}
        self._dirty = False

        layout = QVBoxLayout(self)

        if backend is None or state_store is None:
            # Null-wiring path — only hit by tests that don't pass these.
            # The production ``ConfigDialog`` always passes both.
            label = QLabel(
                self.tr(
                    "No backend attached; the Windows pane is inactive."
                )
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)
            self.model: WindowsTableModel | None = None
            self.view: QTableView | None = None
            self.preset_combo: QComboBox | None = None
            self.apply_preset_button: QPushButton | None = None
            return

        self.model = WindowsTableModel(
            has_last_seen=lambda identity: (
                state_store.get_last_seen(identity) is not None
            ),
            parent=self,
        )

        self.view = QTableView(self)
        self.view.setAccessibleName(self.tr("Managed windows"))
        self.view.setAccessibleDescription(
            self.tr(
                "Live list of windows Perch is tracking. Select a row "
                "and use the buttons below to save or forget the "
                "remembered geometry for that window's identity."
            )
        )
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.view.horizontalHeader().setStretchLastSection(False)
        self.view.verticalHeader().setVisible(False)

        hint = QLabel(
            self.tr(
                "Windows tracked by the active backend. Pick a preset "
                "below and click Apply preset to resize/reposition the "
                "selected window. Save as last-seen records the current "
                "geometry so Perch restores it on next open."
            )
        )
        hint.setWordWrap(True)

        # Preset row: [preset combo] [Apply preset]
        self.preset_combo = QComboBox(self)
        self._populate_presets()

        self.apply_preset_button = QPushButton(self.tr("Apply preset"))
        self.apply_preset_button.setEnabled(False)
        self.apply_preset_button.clicked.connect(self._on_apply_preset)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(self.tr("Preset:")))
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.apply_preset_button)

        self.save_button = QPushButton(self.tr("Save as last-seen"))
        self.forget_button = QPushButton(self.tr("Forget last-seen"))
        self.save_button.setEnabled(False)
        self.forget_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.forget_button.clicked.connect(self._on_forget_clicked)

        self.view.selectionModel().selectionChanged.connect(
            lambda *_: self._update_button_state()
        )

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.forget_button)
        buttons_row.addStretch(1)

        layout.addWidget(hint)
        layout.addWidget(self.view, 1)
        layout.addLayout(preset_row)
        layout.addLayout(buttons_row)

        # Wire live events. ``window_opened`` and ``window_changed`` both
        # deliver a full ``WindowInfo``; the model's ``upsert`` handles
        # both uniformly. ``geometry_changed`` is a narrower update we
        # apply in place so scroll/selection stay put.
        backend.window_opened.connect(self._on_window_opened)
        backend.window_changed.connect(self._on_window_changed)
        backend.window_closed.connect(self._on_window_closed)
        backend.geometry_changed.connect(self._on_geometry_changed)

        # Seed the model from the backend's current snapshot.
        self._seed_initial_windows()

    # ── Initial seed ────────────────────────────────────────────────────
    def _seed_initial_windows(self) -> None:
        """Populate the model from ``backend.list_windows()``.

        Scheduled on the running asyncio loop (qasync in the live app).
        A failure here is logged but not fatal — live backend events
        still populate the table going forward. Tests that construct
        the page without a running loop skip the seed path and rely on
        ``window_opened`` signals to fill the table, matching the
        production behaviour for windows that open after dialog load.
        """
        if self._backend is None or self.model is None:
            return
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _seed() -> None:
            assert self._backend is not None
            assert self.model is not None
            try:
                windows = await self._backend.list_windows()
            except Exception:
                log.exception("WindowsPage: list_windows() failed")
                return
            self.model.set_windows(windows)

        self._seed_task: asyncio.Task[None] = loop.create_task(_seed())

    # ── Event handlers (backend → model) ────────────────────────────────
    def _on_window_opened(self, info: WindowInfo) -> None:
        if self.model is not None:
            self.model.upsert(info)

    def _on_window_changed(self, info: WindowInfo) -> None:
        if self.model is not None:
            self.model.upsert(info)

    def _on_window_closed(self, wid: WindowId) -> None:
        if self.model is not None:
            self.model.remove(wid)

    def _on_geometry_changed(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName,
        desktop: DesktopIndex,
    ) -> None:
        if self.model is not None:
            self.model.update_geometry(wid, geom, monitor, desktop)

    # ── Button actions ──────────────────────────────────────────────────
    def _current_window(self) -> WindowInfo | None:
        if self.model is None or self.view is None:
            return None
        rows = [i.row() for i in self.view.selectionModel().selectedRows()]
        if not rows:
            return None
        return self.model.window_at(rows[0])

    def _update_button_state(self) -> None:
        if self._state_store is None:
            return
        info = self._current_window()
        if info is None:
            self.save_button.setEnabled(False)
            self.forget_button.setEnabled(False)
            if self.apply_preset_button is not None:
                self.apply_preset_button.setEnabled(False)
            return
        self.save_button.setEnabled(True)
        identity = compute_identity(info)
        self.forget_button.setEnabled(
            self._state_store.get_last_seen(identity) is not None
        )
        if self.apply_preset_button is not None:
            self.apply_preset_button.setEnabled(True)

    # ── Preset handling ─────────────────────────────────────────────────
    def _populate_presets(self) -> None:
        """Fill the preset combo with built-ins + user [snaps] entries.

        Each item's ``userData`` is the preset's name (str) so the apply
        path round-trips through :class:`PresetGeometry`. User snaps are
        suffixed with "(snap)" so the user can tell them apart from the
        built-in rectangles.
        """
        if self.preset_combo is None:
            return
        from perch.core.actions import BUILTIN_PRESETS

        self.preset_combo.clear()
        for name in BUILTIN_PRESETS:
            self.preset_combo.addItem(name, name)
        for name in self._user_snaps:
            self.preset_combo.addItem(
                self.tr("{name} (snap)").format(name=name), name
            )

    def _on_apply_preset(self) -> None:
        """Resolve the selected preset against the selected window and apply.

        Runs through :func:`perch.core.resolver.resolve_action`, so the
        same percent→pixel math that the rules engine uses serves the
        dialog too. Failure (unknown output, missing snap, backend
        error) surfaces a ``QMessageBox.warning`` with the specific
        problem — the user gets a real diagnostic rather than silent
        no-op.
        """
        if self._backend is None or self.preset_combo is None:
            return
        info = self._current_window()
        if info is None:
            return
        preset_name = self.preset_combo.currentData()
        if not preset_name:
            return

        import qasync

        from perch.core.actions import ApplyAction, PresetGeometry
        from perch.core.resolver import ResolveError, resolve_action

        async def _apply() -> None:
            assert self._backend is not None  # narrowed above; re-assert for mypy
            try:
                outputs = await self._backend.list_outputs()
            except Exception as exc:
                log.exception("WindowsPage: list_outputs() failed")
                QMessageBox.warning(
                    self,
                    self.tr("Apply preset failed"),
                    self.tr("Could not read outputs: {err}").format(err=str(exc)),
                )
                return
            action = ApplyAction(geometry=PresetGeometry(preset_name))
            try:
                placement = resolve_action(
                    action, info, outputs, self._user_snaps
                )
            except ResolveError as exc:
                QMessageBox.warning(
                    self,
                    self.tr("Apply preset failed"),
                    str(exc),
                )
                return
            if placement.geometry is None or placement.monitor is None:
                QMessageBox.warning(
                    self,
                    self.tr("Apply preset failed"),
                    self.tr("Preset resolved to an empty placement."),
                )
                return
            try:
                await self._backend.set_geometry(
                    info.id, placement.geometry, placement.monitor
                )
            except Exception as exc:
                log.exception("WindowsPage: set_geometry failed")
                QMessageBox.warning(
                    self,
                    self.tr("Apply preset failed"),
                    self.tr("Backend rejected set_geometry: {err}").format(
                        err=str(exc)
                    ),
                )

        slot = qasync.asyncSlot()(_apply)
        slot()

    def _on_save_clicked(self) -> None:
        if self._state_store is None or self.model is None:
            return
        info = self._current_window()
        if info is None:
            return
        identity = compute_identity(info)
        self._state_store.record_window(
            identity, info.geometry, info.monitor, info.desktop
        )
        self._dirty = True
        self.model.refresh_last_seen()
        self._update_button_state()

    def _on_forget_clicked(self) -> None:
        if self._state_store is None or self.model is None:
            return
        info = self._current_window()
        if info is None:
            return
        identity = compute_identity(info)
        self._state_store.forget_window(identity)
        self._dirty = True
        self.model.refresh_last_seen()
        self._update_button_state()

    # ── _Page protocol ──────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        """``True`` when there are pending state-store mutations to flush."""
        return self._dirty

    def commit(self) -> None:
        """Schedule a ``StateStore`` flush so the debounced write lands.

        The store owns atomic write + debounce; here we only trip
        ``mark_dirty`` so the next loop tick (or clean shutdown) writes.
        A failure mid-flush is surfaced via the store's own log, not
        here — the dialog considers the commit successful once the
        mutation is scheduled.
        """
        if not self._dirty:
            return
        if self._state_store is not None:
            self._state_store.mark_dirty()
        self._dirty = False


_DELETE_KEYS = frozenset({int(Qt.Key.Key_Delete), int(Qt.Key.Key_Backspace)})


class _DeleteKeyTableView(QTableView):
    """``QTableView`` that invokes a callback on Delete / Backspace.

    The plain ``QTableView.keyPressEvent`` swallows Delete (it tries to
    clear the current cell via the item-delegate edit pipeline), so a
    module-scoped ``QShortcut`` with ``WidgetWithChildrenShortcut``
    context doesn't fire reliably. Overriding ``keyPressEvent`` reaches
    the event before the built-in handler and keeps the keyboard idiom
    consistent with :class:`_DeleteKeyListWidget`.
    """

    def __init__(
        self, on_delete: Callable[[], None], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._on_delete = on_delete

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if int(event.key()) in _DELETE_KEYS:
            self._on_delete()
            event.accept()
            return
        super().keyPressEvent(event)


class _DeleteKeyListWidget(QListWidget):
    """``QListWidget`` counterpart for :class:`_DeleteKeyTableView`."""

    def __init__(
        self, on_delete: Callable[[], None], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._on_delete = on_delete

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if int(event.key()) in _DELETE_KEYS:
            self._on_delete()
            event.accept()
            return
        super().keyPressEvent(event)


class RulesPage(QWidget):
    """Rules table — drag-reorder + delete. Per-cell editing lands in M3.c."""

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state

        self.model = RulesModel(state.config.rules, self)

        self.view = _DeleteKeyTableView(self._on_delete_clicked, self)
        self.view.setAccessibleName(self.tr("Rules table"))
        self.view.setAccessibleDescription(
            self.tr(
                "Rules in evaluation order. Use Delete or Backspace to remove "
                "the selected rule."
            )
        )
        self.view.setModel(self.model)
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # InternalMove must not overwrite target rows — per docs/08-ui.md
        # §Rules and the research notes from the drag-reorder spike.
        self.view.setDragDropOverwriteMode(False)
        self.view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.view.verticalHeader().setSectionsMovable(False)
        self.view.horizontalHeader().setStretchLastSection(True)

        self.delete_button = QPushButton(self.tr("Delete rule"))
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete_clicked)

        self.view.selectionModel().selectionChanged.connect(
            lambda *_: self.delete_button.setEnabled(
                bool(self.view.selectionModel().selectedRows())
            )
        )

        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        hint = QLabel(
            self.tr(
                "Rules are evaluated top-to-bottom; first match wins. Drag "
                "a row to change evaluation order."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self.view, 1)
        layout.addLayout(buttons)

    def _on_delete_clicked(self) -> None:
        rows = [i.row() for i in self.view.selectionModel().selectedRows()]
        if not rows:
            return
        # One row at a time under SingleSelection, but deleting from high
        # to low protects against index shift if this ever relaxes.
        for row in sorted(rows, reverse=True):
            self.model.remove_rule(row)

    def is_dirty(self) -> bool:
        return tuple(self.model.rules()) != self._state.original_rules

    def commit(self) -> None:
        """Apply reorder-and-delete to the tomlkit document.

        Strategy:
        1. Compare the current working rules against the original by
           identity. Each remaining rule maps back to its original
           TOML-array index via that identity.
        2. Rebuild the new TOML array of tables by picking the original
           entries in the new order. Deletes drop indices that no longer
           appear.
        """
        current = self.model.rules()
        originals = self._state.original_rules
        if current == originals:
            return

        # Identity-based mapping so duplicate-but-equal rules don't alias.
        id_to_index = {id(rule): i for i, rule in enumerate(originals)}
        survivors: list[int] = []
        for rule in current:
            idx = id_to_index.get(id(rule))
            if idx is None:
                # Shouldn't happen without per-cell editing; guard anyway.
                raise RuntimeError(
                    "rules committed that are not in the original set"
                )
            survivors.append(idx)

        # Apply deletes first (highest-index first to preserve earlier indices),
        # then reorder the survivors.
        deleted = sorted(
            set(range(len(originals))) - set(survivors), reverse=True
        )
        for idx in deleted:
            delete_rule(self._state.document, idx)

        # After deletion, indices compact. Rewrite survivors' positions
        # relative to the compacted array.
        remaining_originals = [i for i in range(len(originals)) if i not in set(deleted)]
        remap = {orig_idx: new_idx for new_idx, orig_idx in enumerate(remaining_originals)}
        new_order = [remap[i] for i in survivors]
        if new_order and new_order != list(range(len(new_order))):
            reorder_rules(self._state.document, new_order)


class ExclusionsPage(QWidget):
    """Exclusions list — drag-reorder + delete for M3.b."""

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._original = tuple(state.config.exclusions)
        # Working copy is a plain list of indices into the original —
        # reorder by shuffling indices; delete removes one.
        self._order: list[int] = list(range(len(self._original)))

        self.list = _DeleteKeyListWidget(self._on_delete_clicked, self)
        self.list.setAccessibleName(self.tr("Exclusion patterns"))
        self.list.setAccessibleDescription(
            self.tr(
                "Windows matching any pattern are ignored by Perch. Use "
                "Delete or Backspace to remove the selected pattern."
            )
        )
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._repopulate()
        self.list.model().rowsMoved.connect(self._on_rows_moved)

        self.delete_button = QPushButton(self.tr("Delete pattern"))
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.list.currentRowChanged.connect(
            lambda row: self.delete_button.setEnabled(row >= 0)
        )

        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        hint = QLabel(
            self.tr(
                "Windows matching any of these patterns are ignored by Perch."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)

    def _repopulate(self) -> None:
        self.list.clear()
        for original_index in self._order:
            pattern = self._original[original_index]
            parts: list[str] = []
            if pattern.catch_all:
                parts.append("catch_all")
            if pattern.app_id:
                parts.append(f"app_id={pattern.app_id}")
            if pattern.wm_class:
                parts.append(f"wm_class={pattern.wm_class}")
            if pattern.title is not None:
                parts.append(f"title=~{pattern.title.pattern}")
            if pattern.types:
                parts.append("type=" + ",".join(t.value for t in pattern.types))
            summary = " ".join(parts) or "<empty>"
            item = QListWidgetItem(summary)
            # Store the original index so rowsMoved can read back the new
            # order from the list's current rows.
            item.setData(Qt.ItemDataRole.UserRole, original_index)
            self.list.addItem(item)

    def _on_rows_moved(self, *_: Any) -> None:
        self._order = [
            self.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list.count())
        ]

    def _on_delete_clicked(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        del self._order[row]
        self._repopulate()

    def is_dirty(self) -> bool:
        return self._order != list(range(len(self._original)))

    def commit(self) -> None:
        if not self.is_dirty():
            return
        # Apply deletes relative to the original indices (high-first).
        original_indices = set(range(len(self._original)))
        deleted = sorted(original_indices - set(self._order), reverse=True)
        for idx in deleted:
            delete_exclusion(self._state.document, idx)

        remaining = [i for i in range(len(self._original)) if i not in set(deleted)]
        remap = {orig: new for new, orig in enumerate(remaining)}
        new_order = [remap[i] for i in self._order]
        if new_order and new_order != list(range(len(new_order))):
            reorder_exclusions(self._state.document, new_order)


class LayoutsPage(QWidget):
    """Per-layout entry editor.

    Structure:

    * Left: ``QListWidget`` of layout names + Add / Rename / Delete buttons.
    * Right: description ``QLineEdit`` + ``QTableView`` of entries with
      Add / Edit / Delete / Up / Down row actions.

    The page keeps a working copy of the layouts dict and defers
    mutation of the tomlkit document until :meth:`commit`, which
    applies the add / delete / rename + per-entry mutators in the
    correct order. Cancel discards the working copy.
    """

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        # Deep copy so Cancel doesn't leak back to the dialog's state.
        self._layouts: dict[str, Layout] = {
            name: layout for name, layout in state.config.layouts.items()
        }
        self._original_names = tuple(self._layouts.keys())
        self._original_layouts: dict[str, Layout] = dict(self._layouts)
        # Track renames so the commit path can map between old↔new names.
        self._renames: dict[str, str] = {}  # original name → current name
        for name in self._original_names:
            self._renames[name] = name

        self._user_snap_names: tuple[str, ...] = tuple(
            state.config.snaps.keys()
        )
        self._current_layout: str | None = None
        self._dirty = False

        # ── Left side: layout list ─────────────────────────────────────
        self.layouts_list = QListWidget(self)
        self.layouts_list.setAccessibleName(self.tr("Layouts"))
        self.layouts_list.setAccessibleDescription(
            self.tr("User-defined named layouts.")
        )
        for name in self._layouts:
            self.layouts_list.addItem(name)
        self.layouts_list.currentTextChanged.connect(self._on_layout_selected)

        self.add_layout_button = QPushButton(self.tr("Add layout"))
        self.rename_layout_button = QPushButton(self.tr("Rename"))
        self.delete_layout_button = QPushButton(self.tr("Delete"))
        self.add_layout_button.clicked.connect(self._on_add_layout)
        self.rename_layout_button.clicked.connect(self._on_rename_layout)
        self.delete_layout_button.clicked.connect(self._on_delete_layout)

        layout_buttons = QHBoxLayout()
        layout_buttons.addWidget(self.add_layout_button)
        layout_buttons.addWidget(self.rename_layout_button)
        layout_buttons.addWidget(self.delete_layout_button)
        layout_buttons.addStretch(1)

        left = QVBoxLayout()
        left.addWidget(QLabel(self.tr("Layouts")))
        left.addWidget(self.layouts_list, 1)
        left.addLayout(layout_buttons)

        # ── Right side: details of selected layout ─────────────────────
        self.description_edit = QLineEdit(self)
        self.description_edit.setPlaceholderText(
            self.tr("Short description of this layout (optional)")
        )
        self.description_edit.textEdited.connect(self._on_description_edited)

        self.entries_view = QTableView(self)
        self.entries_view.setAccessibleName(self.tr("Layout entries"))
        self.entries_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.entries_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.entries_view.horizontalHeader().setStretchLastSection(True)
        self.entries_view.verticalHeader().setVisible(False)
        self.entries_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.entries_view.doubleClicked.connect(lambda _i: self._on_edit_entry())
        self._entries_model: _LayoutEntriesModel | None = None

        self.add_entry_button = QPushButton(self.tr("Add entry"))
        self.edit_entry_button = QPushButton(self.tr("Edit"))
        self.delete_entry_button = QPushButton(self.tr("Delete"))
        self.up_entry_button = QPushButton(self.tr("Move up"))
        self.down_entry_button = QPushButton(self.tr("Move down"))
        self.add_entry_button.clicked.connect(self._on_add_entry)
        self.edit_entry_button.clicked.connect(self._on_edit_entry)
        self.delete_entry_button.clicked.connect(self._on_delete_entry)
        self.up_entry_button.clicked.connect(lambda: self._on_move_entry(-1))
        self.down_entry_button.clicked.connect(lambda: self._on_move_entry(+1))

        entry_buttons = QHBoxLayout()
        entry_buttons.addWidget(self.add_entry_button)
        entry_buttons.addWidget(self.edit_entry_button)
        entry_buttons.addWidget(self.delete_entry_button)
        entry_buttons.addWidget(self.up_entry_button)
        entry_buttons.addWidget(self.down_entry_button)
        entry_buttons.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(QLabel(self.tr("Description:")))
        right.addWidget(self.description_edit)
        right.addWidget(QLabel(self.tr("Entries:")))
        right.addWidget(self.entries_view, 1)
        right.addLayout(entry_buttons)

        root = QHBoxLayout(self)
        root.addLayout(left, 1)
        root.addLayout(right, 2)

        # Initial selection
        if self._layouts:
            first_name = next(iter(self._layouts))
            self.layouts_list.setCurrentRow(0)
            self._on_layout_selected(first_name)
        else:
            self._on_layout_selected("")
        self._update_button_state()

    # ── Selection / disabling ────────────────────────────────────────────
    def _update_button_state(self) -> None:
        has_layout = self._current_layout is not None
        self.rename_layout_button.setEnabled(has_layout)
        self.delete_layout_button.setEnabled(has_layout)
        self.description_edit.setEnabled(has_layout)
        self.entries_view.setEnabled(has_layout)
        self.add_entry_button.setEnabled(has_layout)
        selected = bool(
            self.entries_view.selectionModel()
            and self.entries_view.selectionModel().selectedRows()
        )
        self.edit_entry_button.setEnabled(has_layout and selected)
        self.delete_entry_button.setEnabled(has_layout and selected)
        self.up_entry_button.setEnabled(has_layout and selected)
        self.down_entry_button.setEnabled(has_layout and selected)

    def _on_layout_selected(self, name: str) -> None:
        if not name or name not in self._layouts:
            self._current_layout = None
            self._entries_model = _LayoutEntriesModel([])
            self.entries_view.setModel(self._entries_model)
            self.description_edit.clear()
            self._update_button_state()
            return
        self._current_layout = name
        layout = self._layouts[name]
        self.description_edit.blockSignals(True)
        self.description_edit.setText(layout.description)
        self.description_edit.blockSignals(False)
        self._entries_model = _LayoutEntriesModel(list(layout.windows))
        self.entries_view.setModel(self._entries_model)
        self.entries_view.selectionModel().selectionChanged.connect(
            lambda *_: self._update_button_state()
        )
        self._update_button_state()

    # ── Layout CRUD ─────────────────────────────────────────────────────
    def _on_add_layout(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            self.tr("Add layout"),
            self.tr("Layout name:"),
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(
                self,
                self.tr("Invalid name"),
                self.tr("Layout name must not be empty."),
            )
            return
        if name in self._layouts:
            QMessageBox.warning(
                self,
                self.tr("Duplicate name"),
                self.tr("A layout with that name already exists."),
            )
            return
        self._layouts[name] = Layout(name=name, description="", windows=())
        self.layouts_list.addItem(name)
        self.layouts_list.setCurrentRow(self.layouts_list.count() - 1)
        self._dirty = True

    def _on_rename_layout(self) -> None:
        if self._current_layout is None:
            return
        old = self._current_layout
        new, ok = QInputDialog.getText(
            self,
            self.tr("Rename layout"),
            self.tr("New name:"),
            text=old,
        )
        if not ok:
            return
        new = new.strip()
        if not new or new == old:
            return
        if new in self._layouts:
            QMessageBox.warning(
                self,
                self.tr("Duplicate name"),
                self.tr("A layout with that name already exists."),
            )
            return
        # Rebuild ordered dict so iteration order is preserved.
        rebuilt: dict[str, Layout] = {}
        for existing_name, layout in self._layouts.items():
            if existing_name == old:
                rebuilt[new] = Layout(
                    name=new, description=layout.description,
                    windows=layout.windows,
                )
            else:
                rebuilt[existing_name] = layout
        self._layouts = rebuilt
        # Track the rename lineage back to the original name.
        for original, current in list(self._renames.items()):
            if current == old:
                self._renames[original] = new
                break
        else:
            self._renames[new] = new
        # Refresh the list widget.
        row = self.layouts_list.currentRow()
        self.layouts_list.blockSignals(True)
        self.layouts_list.clear()
        for existing_name in self._layouts:
            self.layouts_list.addItem(existing_name)
        self.layouts_list.blockSignals(False)
        self.layouts_list.setCurrentRow(row)
        self._current_layout = new
        self._dirty = True

    def _on_delete_layout(self) -> None:
        if self._current_layout is None:
            return
        name = self._current_layout
        reply = QMessageBox.question(
            self,
            self.tr("Delete layout"),
            self.tr("Delete layout {name}?").format(name=name),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del self._layouts[name]
        # Drop the rename mapping if the deleted layout was renamed.
        for original, current in list(self._renames.items()):
            if current == name:
                del self._renames[original]
        row = self.layouts_list.currentRow()
        self.layouts_list.takeItem(row)
        self._dirty = True
        if self._layouts:
            self.layouts_list.setCurrentRow(
                min(row, self.layouts_list.count() - 1)
            )
        else:
            self._on_layout_selected("")

    def _on_description_edited(self, text: str) -> None:
        if self._current_layout is None:
            return
        layout = self._layouts[self._current_layout]
        self._layouts[self._current_layout] = Layout(
            name=layout.name, description=text, windows=layout.windows,
        )
        self._dirty = True

    # ── Entry CRUD ──────────────────────────────────────────────────────
    def _current_entries(self) -> list[LayoutEntry] | None:
        if self._current_layout is None:
            return None
        return list(self._layouts[self._current_layout].windows)

    def _write_entries(self, entries: list[LayoutEntry]) -> None:
        assert self._current_layout is not None
        layout = self._layouts[self._current_layout]
        self._layouts[self._current_layout] = Layout(
            name=layout.name,
            description=layout.description,
            windows=tuple(entries),
        )
        assert self._entries_model is not None
        self._entries_model.set_entries(entries)
        self._dirty = True
        self._update_button_state()

    def _selected_entry_row(self) -> int | None:
        sel = self.entries_view.selectionModel()
        # sel is never None once the view has a model, but the typestub
        # still annotates it as Optional — fall through explicitly.
        rows = [i.row() for i in sel.selectedRows()]
        return rows[0] if rows else None

    def _on_add_entry(self) -> None:
        entries = self._current_entries()
        if entries is None:
            return
        dialog = EntryEditorDialog(
            None, user_snaps=self._user_snap_names, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            entries.append(dialog.value())
            self._write_entries(entries)

    def _on_edit_entry(self) -> None:
        entries = self._current_entries()
        row = self._selected_entry_row()
        if entries is None or row is None:
            return
        dialog = EntryEditorDialog(
            entries[row], user_snaps=self._user_snap_names, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            entries[row] = dialog.value()
            self._write_entries(entries)

    def _on_delete_entry(self) -> None:
        entries = self._current_entries()
        row = self._selected_entry_row()
        if entries is None or row is None:
            return
        del entries[row]
        self._write_entries(entries)

    def _on_move_entry(self, delta: int) -> None:
        entries = self._current_entries()
        row = self._selected_entry_row()
        if entries is None or row is None:
            return
        new_row = row + delta
        if not 0 <= new_row < len(entries):
            return
        entries[row], entries[new_row] = entries[new_row], entries[row]
        self._write_entries(entries)
        self.entries_view.selectRow(new_row)

    # ── _Page protocol ──────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        return self._dirty

    def commit(self) -> None:
        """Replay the working-copy diffs onto the tomlkit document.

        Strategy:
        1. Deletions — any original name not in ``self._layouts`` or
           whose rename-lineage points at a deleted layout — are
           applied first.
        2. Renames — original→current mapping for surviving names.
        3. Additions — names not present in the originals.
        4. For every surviving layout: rewrite description if it
           changed; rewrite the entries array wholesale.

        The layout-entry rewrite is the loud option — rather than
        diffing per entry, we delete every existing entry and re-add
        in order. That trades minor comment loss inside
        ``[[layouts.*.windows]]`` for simpler code; top-level
        ``[layouts.*]`` comments are still preserved because the
        tables themselves aren't destroyed.
        """
        if not self._dirty:
            return
        doc = self._state.document

        # Build the final-current → current-name mapping so we know
        # which originals still exist and under what name.
        survivors_by_original: dict[str, str] = {}
        for original, current in self._renames.items():
            if current in self._layouts:
                survivors_by_original[original] = current

        # 1. Deletions.
        for original in self._original_names:
            current_name = self._renames.get(original)
            if current_name is None or current_name not in self._layouts:
                # Treat already-absent (e.g. original was later re-added
                # with the same name) as a no-op.
                with contextlib.suppress(ConfigEditError):
                    delete_layout(doc, original)

        # 2. Renames (apply before the add step so a rename-to-name-of-a-later-add doesn't collide).
        for original, current in survivors_by_original.items():
            if original != current:
                rename_layout(doc, original, current)

        # 3. Additions.
        already_written = set(survivors_by_original.values())
        for name, layout in self._layouts.items():
            if name in already_written:
                continue
            add_layout(doc, name, description=layout.description)

        # 4. Description + entries rewrite per surviving or new layout.
        for name, layout in self._layouts.items():
            # Idempotent description write — cheap and safe.
            set_layout_description(doc, name, layout.description)

            # Rewrite the entries array wholesale. The AoT has no
            # public "replace-all" so we delete and re-add. This is
            # the only section whose internal comments don't survive;
            # layout-entries are fully dialog-edited so it's acceptable.
            existing_count = _existing_entry_count(doc, name)
            for _ in range(existing_count):
                delete_layout_entry(doc, name, 0)
            for entry in layout.windows:
                add_layout_entry(doc, name, entry)

        self._dirty = False
        # Refresh the originals snapshot so subsequent Apply passes
        # don't re-diff against the pre-commit state.
        self._original_names = tuple(self._layouts.keys())
        self._renames = {name: name for name in self._layouts}


def _existing_entry_count(document: Any, layout_name: str) -> int:
    """Return the current entry count of a layout, or 0 if missing."""
    layouts = document.get("layouts")
    if layouts is None:
        return 0
    entry = layouts.get(layout_name)
    if entry is None:
        return 0
    windows = entry.get("windows")
    if windows is None:
        return 0
    return len(windows)


class _LayoutEntriesModel(QAbstractTableModel):
    """Table model for a single layout's entries (Match + Apply columns)."""

    COL_MATCH = 0
    COL_APPLY = 1
    COLUMN_COUNT = 2

    def __init__(self, entries: list[LayoutEntry]) -> None:
        super().__init__()
        self._entries: list[LayoutEntry] = list(entries)

    def set_entries(self, entries: list[LayoutEntry]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        if parent.isValid():
            return 0
        return self.COLUMN_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role != Qt.ItemDataRole.DisplayRole
            or orientation != Qt.Orientation.Horizontal
        ):
            return None
        return (
            QCoreApplication.translate("perch.ui.dialog", "Match"),
            QCoreApplication.translate("perch.ui.dialog", "Apply"),
        )[section]

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        entry = self._entries[index.row()]
        if index.column() == self.COL_MATCH:
            return summarise_match(entry.match)
        if index.column() == self.COL_APPLY:
            return summarise_apply(entry.apply)
        return None


class ProfilesPage(QWidget):
    """Per-profile topology + default_layout + overrides editor.

    Profiles are stored as an array-of-tables (``[[profiles]]``), so
    this page keeps a working copy indexed by the original position in
    the array and replays add / delete / rename / field-set /
    overrides-replace on commit.
    """

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._profiles: list[Profile] = list(state.config.profiles)
        self._originals: list[Profile] = list(state.config.profiles)
        # Deleted original indices (for the commit-time delete pass).
        self._deleted_originals: list[int] = []
        # Maps current list position → original profile index, or None
        # for freshly-added profiles that commit will ``add_profile``.
        self._origin: list[int | None] = list(range(len(self._profiles)))
        self._available_layouts: tuple[str, ...] = tuple(
            state.config.layouts.keys()
        )
        self._user_snap_names: tuple[str, ...] = tuple(
            state.config.snaps.keys()
        )
        self._current_index: int | None = None
        self._dirty = False

        # ── Left: profile list ─────────────────────────────────────────
        self.profiles_list = QListWidget(self)
        self.profiles_list.setAccessibleName(self.tr("Profiles"))
        self._repopulate_profiles_list()
        self.profiles_list.currentRowChanged.connect(self._on_profile_selected)

        self.add_profile_button = QPushButton(self.tr("Add profile"))
        self.delete_profile_button = QPushButton(self.tr("Delete"))
        self.add_profile_button.clicked.connect(self._on_add_profile)
        self.delete_profile_button.clicked.connect(self._on_delete_profile)

        profile_buttons = QHBoxLayout()
        profile_buttons.addWidget(self.add_profile_button)
        profile_buttons.addWidget(self.delete_profile_button)
        profile_buttons.addStretch(1)

        left = QVBoxLayout()
        left.addWidget(QLabel(self.tr("Profiles")))
        left.addWidget(self.profiles_list, 1)
        left.addLayout(profile_buttons)

        # ── Right: detail view ─────────────────────────────────────────
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText(self.tr("Profile name"))
        self.name_edit.editingFinished.connect(self._on_name_edited)

        self.topology_edit = QLineEdit(self)
        self.topology_edit.setPlaceholderText(
            self.tr("name:WxH@X,Y;name:WxH@X,Y (sorted, joined by ;)")
        )
        self.topology_edit.editingFinished.connect(self._on_topology_edited)

        self.default_layout_combo = QComboBox(self)
        self.default_layout_combo.addItem(self.tr("<none>"), None)
        for name in self._available_layouts:
            self.default_layout_combo.addItem(name, name)
        self.default_layout_combo.currentIndexChanged.connect(
            self._on_default_layout_changed
        )

        # Overrides table: one row per ProfileOverride.
        self.overrides_view = QTableView(self)
        self.overrides_view.setAccessibleName(self.tr("Layout overrides"))
        self.overrides_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.overrides_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.overrides_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.overrides_view.horizontalHeader().setStretchLastSection(True)
        self.overrides_view.verticalHeader().setVisible(False)
        self.overrides_view.doubleClicked.connect(
            lambda _i: self._on_edit_override()
        )
        self._overrides_model: _OverridesModel | None = None

        self.add_override_button = QPushButton(self.tr("Add override"))
        self.edit_override_button = QPushButton(self.tr("Edit"))
        self.delete_override_button = QPushButton(self.tr("Delete"))
        self.add_override_button.clicked.connect(self._on_add_override)
        self.edit_override_button.clicked.connect(self._on_edit_override)
        self.delete_override_button.clicked.connect(
            self._on_delete_override
        )

        override_buttons = QHBoxLayout()
        override_buttons.addWidget(self.add_override_button)
        override_buttons.addWidget(self.edit_override_button)
        override_buttons.addWidget(self.delete_override_button)
        override_buttons.addStretch(1)

        detail_form = QFormLayout()
        detail_form.addRow(self.tr("Name:"), self.name_edit)
        detail_form.addRow(self.tr("Topology:"), self.topology_edit)
        detail_form.addRow(
            self.tr("Default layout:"), self.default_layout_combo
        )

        right = QVBoxLayout()
        right.addLayout(detail_form)
        right.addWidget(QLabel(self.tr("Per-layout overrides:")))
        right.addWidget(self.overrides_view, 1)
        right.addLayout(override_buttons)

        root = QHBoxLayout(self)
        root.addLayout(left, 1)
        root.addLayout(right, 2)

        if self._profiles:
            self.profiles_list.setCurrentRow(0)
        else:
            self._on_profile_selected(-1)
        self._update_button_state()

    # ── Helpers ─────────────────────────────────────────────────────────
    def _repopulate_profiles_list(self) -> None:
        self.profiles_list.blockSignals(True)
        self.profiles_list.clear()
        for profile in self._profiles:
            item = QListWidgetItem(
                profile.name or self.tr("<unnamed>")
            )
            self.profiles_list.addItem(item)
        self.profiles_list.blockSignals(False)

    def _update_button_state(self) -> None:
        has_profile = self._current_index is not None
        self.delete_profile_button.setEnabled(has_profile)
        self.name_edit.setEnabled(has_profile)
        self.topology_edit.setEnabled(has_profile)
        self.default_layout_combo.setEnabled(has_profile)
        self.overrides_view.setEnabled(has_profile)
        self.add_override_button.setEnabled(has_profile)
        sel = self.overrides_view.selectionModel()
        selected = bool(sel and sel.selectedRows())
        self.edit_override_button.setEnabled(has_profile and selected)
        self.delete_override_button.setEnabled(has_profile and selected)

    def _on_profile_selected(self, index: int) -> None:
        if not 0 <= index < len(self._profiles):
            self._current_index = None
            self.name_edit.clear()
            self.topology_edit.clear()
            self.default_layout_combo.setCurrentIndex(0)
            self._overrides_model = _OverridesModel([])
            self.overrides_view.setModel(self._overrides_model)
            self._update_button_state()
            return
        self._current_index = index
        profile = self._profiles[index]
        self.name_edit.blockSignals(True)
        self.topology_edit.blockSignals(True)
        self.default_layout_combo.blockSignals(True)
        self.name_edit.setText(profile.name)
        self.topology_edit.setText(profile.topology)
        idx = self.default_layout_combo.findData(profile.default_layout)
        self.default_layout_combo.setCurrentIndex(max(idx, 0))
        self.name_edit.blockSignals(False)
        self.topology_edit.blockSignals(False)
        self.default_layout_combo.blockSignals(False)
        self._overrides_model = _OverridesModel(list(profile.overrides))
        self.overrides_view.setModel(self._overrides_model)
        self.overrides_view.selectionModel().selectionChanged.connect(
            lambda *_: self._update_button_state()
        )
        self._update_button_state()

    def _write_profile(self, index: int, profile: Profile) -> None:
        self._profiles[index] = profile
        self._dirty = True
        # Refresh the sidebar label in case the name changed.
        item = self.profiles_list.item(index)
        if item is not None:
            item.setText(profile.name or self.tr("<unnamed>"))

    # ── Profile-level actions ───────────────────────────────────────────
    def _on_add_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            self.tr("Add profile"),
            self.tr("Profile name:"),
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if any(p.name == name for p in self._profiles):
            QMessageBox.warning(
                self,
                self.tr("Duplicate name"),
                self.tr("A profile with that name already exists."),
            )
            return
        self._profiles.append(
            Profile(name=name, topology="", default_layout=None)
        )
        self._origin.append(None)  # new profile — ``add_profile`` at commit
        self._repopulate_profiles_list()
        self.profiles_list.setCurrentRow(len(self._profiles) - 1)
        self._dirty = True

    def _on_delete_profile(self) -> None:
        if self._current_index is None:
            return
        index = self._current_index
        reply = QMessageBox.question(
            self,
            self.tr("Delete profile"),
            self.tr("Delete this profile?"),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        origin = self._origin[index]
        if origin is not None:
            self._deleted_originals.append(origin)
        del self._profiles[index]
        del self._origin[index]
        self._repopulate_profiles_list()
        self._dirty = True
        if self._profiles:
            self.profiles_list.setCurrentRow(
                min(index, len(self._profiles) - 1)
            )
        else:
            self._on_profile_selected(-1)

    def _on_name_edited(self) -> None:
        if self._current_index is None:
            return
        new_name = self.name_edit.text().strip()
        profile = self._profiles[self._current_index]
        if new_name == profile.name:
            return
        # Reject duplicate in the current list.
        for i, existing in enumerate(self._profiles):
            if i != self._current_index and existing.name == new_name:
                QMessageBox.warning(
                    self,
                    self.tr("Duplicate name"),
                    self.tr("A profile with that name already exists."),
                )
                # Revert the edit visually.
                self.name_edit.setText(profile.name)
                return
        self._write_profile(
            self._current_index,
            Profile(
                name=new_name,
                topology=profile.topology,
                default_layout=profile.default_layout,
                overrides=profile.overrides,
            ),
        )

    def _on_topology_edited(self) -> None:
        if self._current_index is None:
            return
        profile = self._profiles[self._current_index]
        new_topology = self.topology_edit.text().strip()
        if new_topology == profile.topology:
            return
        self._write_profile(
            self._current_index,
            Profile(
                name=profile.name,
                topology=new_topology,
                default_layout=profile.default_layout,
                overrides=profile.overrides,
            ),
        )

    def _on_default_layout_changed(self, _idx: int) -> None:
        if self._current_index is None:
            return
        profile = self._profiles[self._current_index]
        new_default = self.default_layout_combo.currentData()
        if new_default == profile.default_layout:
            return
        self._write_profile(
            self._current_index,
            Profile(
                name=profile.name,
                topology=profile.topology,
                default_layout=new_default,
                overrides=profile.overrides,
            ),
        )

    # ── Override-level actions ──────────────────────────────────────────
    def _override_rows(self) -> list[ProfileOverride] | None:
        if self._current_index is None:
            return None
        return list(self._profiles[self._current_index].overrides)

    def _write_overrides(self, overrides: list[ProfileOverride]) -> None:
        assert self._current_index is not None
        profile = self._profiles[self._current_index]
        self._write_profile(
            self._current_index,
            Profile(
                name=profile.name,
                topology=profile.topology,
                default_layout=profile.default_layout,
                overrides=tuple(overrides),
            ),
        )
        assert self._overrides_model is not None
        self._overrides_model.set_overrides(overrides)
        self._update_button_state()

    def _selected_override_row(self) -> int | None:
        sel = self.overrides_view.selectionModel()
        rows = [i.row() for i in sel.selectedRows()]
        return rows[0] if rows else None

    def _on_add_override(self) -> None:
        overrides = self._override_rows()
        if overrides is None:
            return
        dialog = _OverrideEditorDialog(
            override=None,
            available_layouts=self._available_layouts,
            user_snaps=self._user_snap_names,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            overrides.append(dialog.value())
            self._write_overrides(overrides)

    def _on_edit_override(self) -> None:
        overrides = self._override_rows()
        row = self._selected_override_row()
        if overrides is None or row is None:
            return
        dialog = _OverrideEditorDialog(
            override=overrides[row],
            available_layouts=self._available_layouts,
            user_snaps=self._user_snap_names,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            overrides[row] = dialog.value()
            self._write_overrides(overrides)

    def _on_delete_override(self) -> None:
        overrides = self._override_rows()
        row = self._selected_override_row()
        if overrides is None or row is None:
            return
        del overrides[row]
        self._write_overrides(overrides)

    # ── _Page protocol ──────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        return self._dirty

    def commit(self) -> None:
        if not self._dirty:
            return
        from perch.config.edit import (
            add_profile,
            delete_profile,
            set_profile_field,
            set_profile_overrides,
        )

        # Pre-validate before touching the document: the loader's schema
        # rejects empty ``name`` / ``topology``, so writing one would
        # break the next startup. Raise here and the dialog's commit
        # gate leaves disk untouched with a readable error message.
        for profile in self._profiles:
            if not profile.name.strip():
                raise ConfigEditError(
                    "A profile is missing a name. Fill in the Name field "
                    "or delete the row before saving."
                )
            if not profile.topology.strip():
                raise ConfigEditError(
                    f"Profile {profile.name!r} is missing a topology. "
                    "Topology has the form 'name:WxH@X,Y;…' — fill it "
                    "in or delete the profile before saving."
                )

        doc = self._state.document

        # 1. Deletions on the original array (high indices first so the
        # remaining originals keep their positions).
        for original_idx in sorted(set(self._deleted_originals), reverse=True):
            with contextlib.suppress(ConfigEditError):
                delete_profile(doc, original_idx)

        # 2. After deletions, the surviving-originals compact. Build a
        # remap so we can still index into them for rewrites.
        remaining = [
            i for i in range(len(self._originals))
            if i not in set(self._deleted_originals)
        ]
        remap = {orig: new_pos for new_pos, orig in enumerate(remaining)}

        # 3. Apply field rewrites for each surviving profile.
        for ui_idx, profile in enumerate(self._profiles):
            origin = self._origin[ui_idx]
            if origin is None:
                continue
            doc_idx = remap[origin]
            set_profile_field(doc, doc_idx, "name", profile.name)
            set_profile_field(doc, doc_idx, "topology", profile.topology)
            set_profile_field(
                doc, doc_idx, "default_layout", profile.default_layout
            )
            set_profile_overrides(
                doc,
                doc_idx,
                [
                    (ov.layout, list(ov.windows))
                    for ov in profile.overrides
                ],
            )

        # 4. Additions (appended last so their final indices equal the
        # current doc length at that point).
        for ui_idx, profile in enumerate(self._profiles):
            if self._origin[ui_idx] is not None:
                continue
            add_profile(
                doc,
                name=profile.name,
                topology=profile.topology,
                default_layout=profile.default_layout,
            )
            # The just-added profile sits at the end of the doc's AoT.
            aot = doc.get("profiles")
            new_doc_idx = len(aot) - 1
            set_profile_overrides(
                doc,
                new_doc_idx,
                [
                    (ov.layout, list(ov.windows))
                    for ov in profile.overrides
                ],
            )

        self._dirty = False
        # Freeze the new state as the next "original" snapshot so a
        # second Apply doesn't re-diff against the pre-commit state.
        self._originals = list(self._profiles)
        self._deleted_originals = []
        self._origin = list(range(len(self._profiles)))


class _OverridesModel(QAbstractTableModel):
    """Table model for a profile's override list."""

    COL_LAYOUT = 0
    COL_ENTRIES = 1
    COLUMN_COUNT = 2

    def __init__(self, overrides: list[ProfileOverride]) -> None:
        super().__init__()
        self._overrides: list[ProfileOverride] = list(overrides)

    def set_overrides(self, overrides: list[ProfileOverride]) -> None:
        self.beginResetModel()
        self._overrides = list(overrides)
        self.endResetModel()

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._overrides)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        if parent.isValid():
            return 0
        return self.COLUMN_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role != Qt.ItemDataRole.DisplayRole
            or orientation != Qt.Orientation.Horizontal
        ):
            return None
        return (
            QCoreApplication.translate("perch.ui.dialog", "Layout"),
            QCoreApplication.translate("perch.ui.dialog", "Entries"),
        )[section]

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        override = self._overrides[index.row()]
        if index.column() == self.COL_LAYOUT:
            return override.layout
        if index.column() == self.COL_ENTRIES:
            return str(len(override.windows))
        return None


class _OverrideEditorDialog(QDialog):
    """Modal editor for a single ProfileOverride.

    Picks a layout name (from the available layouts combo), then
    maintains an entry table identical in shape to the Layouts page's
    one. Entries reuse :class:`EntryEditorDialog`.
    """

    def __init__(
        self,
        override: ProfileOverride | None,
        *,
        available_layouts: tuple[str, ...],
        user_snaps: tuple[str, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            self.tr("Edit override")
            if override is not None
            else self.tr("Add override")
        )
        self.resize(560, 540)
        self._user_snaps = user_snaps

        self._entries: list[LayoutEntry] = (
            list(override.windows) if override is not None else []
        )

        self.layout_combo = QComboBox()
        for name in available_layouts:
            self.layout_combo.addItem(name, name)
        if override is not None:
            idx = self.layout_combo.findData(override.layout)
            if idx < 0:
                self.layout_combo.addItem(override.layout, override.layout)
                idx = self.layout_combo.findData(override.layout)
            self.layout_combo.setCurrentIndex(idx)

        self.entries_view = QTableView(self)
        self.entries_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.entries_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.entries_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.entries_view.horizontalHeader().setStretchLastSection(True)
        self.entries_view.verticalHeader().setVisible(False)
        self._model = _LayoutEntriesModel(self._entries)
        self.entries_view.setModel(self._model)
        self.entries_view.doubleClicked.connect(lambda _i: self._on_edit())

        self.add_button = QPushButton(self.tr("Add entry"))
        self.edit_button = QPushButton(self.tr("Edit"))
        self.delete_button = QPushButton(self.tr("Delete"))
        self.add_button.clicked.connect(self._on_add)
        self.edit_button.clicked.connect(self._on_edit)
        self.delete_button.clicked.connect(self._on_delete)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.add_button)
        buttons_row.addWidget(self.edit_button)
        buttons_row.addWidget(self.delete_button)
        buttons_row.addStretch(1)

        ok_cancel = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok_cancel.accepted.connect(self.accept)
        ok_cancel.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("Layout:"), self.layout_combo)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel(self.tr("Override entries:")))
        root.addWidget(self.entries_view, 1)
        root.addLayout(buttons_row)
        root.addWidget(ok_cancel)

    def _selected_row(self) -> int | None:
        sel = self.entries_view.selectionModel()
        rows = [i.row() for i in sel.selectedRows()]
        return rows[0] if rows else None

    def _on_add(self) -> None:
        dialog = EntryEditorDialog(
            None, user_snaps=self._user_snaps, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._entries.append(dialog.value())
            self._model.set_entries(self._entries)

    def _on_edit(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = EntryEditorDialog(
            self._entries[row], user_snaps=self._user_snaps, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._entries[row] = dialog.value()
            self._model.set_entries(self._entries)

    def _on_delete(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        del self._entries[row]
        self._model.set_entries(self._entries)

    def value(self) -> ProfileOverride:
        return ProfileOverride(
            layout=self.layout_combo.currentData(),
            windows=tuple(self._entries),
        )


class HotkeysPage(QWidget):
    """Live :class:`HotkeyEdit` per snap preset.

    Edits mutate the tomlkit document via
    :func:`perch.config.edit.apply_snap_hotkey` on commit and take
    effect on the next Perch reload / backend restart — the registered
    transports (portal / KGlobalAccel / XGrabKey) re-read the snap
    hotkey table at backend start.
    """

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._edits: dict[str, HotkeyEdit] = {}
        self._original: dict[str, str] = {
            name: preset.hotkey or ""
            for name, preset in state.config.snaps.items()
        }

        root = QVBoxLayout(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        presets = list(state.config.snaps.values())
        if not presets:
            empty = QLabel(
                self.tr(
                    "Define snap presets under [snaps] in config.toml to "
                    "assign hotkeys here."
                )
            )
            empty.setWordWrap(True)
            root.addWidget(empty)
        else:
            hint = QLabel(
                self.tr(
                    "Bindings are saved to config.toml and picked up at "
                    "the next backend start."
                )
            )
            hint.setWordWrap(True)
            root.addWidget(hint)
            for preset in presets:
                edit = HotkeyEdit(self)
                if preset.hotkey:
                    edit.set_accel(preset.hotkey)
                self._edits[preset.name] = edit
                form.addRow(preset.name, edit)
            root.addLayout(form)
        root.addStretch(1)

    def _current_accels(self) -> dict[str, str]:
        return {name: edit.accel() for name, edit in self._edits.items()}

    def is_dirty(self) -> bool:
        return self._current_accels() != self._original

    def commit(self) -> None:
        """Write any changed bindings to ``[snaps.<name>].hotkey``."""
        from perch.config.edit import apply_snap_hotkey

        current = self._current_accels()
        for name, new_accel in current.items():
            if new_accel == self._original.get(name, ""):
                continue
            apply_snap_hotkey(self._state.document, name, new_accel or None)
        # Freeze the new bindings so a second Apply doesn't re-diff.
        self._original = current


class ImportExportPage(QWidget):
    """File-picker based config transfer with a dry-run diff panel.

    * **Export** — offers `QFileDialog.getSaveFileName`, writes the
      current on-disk ``config.toml`` (serialised from the tomlkit
      document so any pending edits from other panes are captured
      once they commit — the export button saves what's currently
      on disk, not the working copy).
    * **Import** — lets the user pick a TOML file, parses it through
      :func:`perch.config.loader._load_and_validate` to reject
      malformed input before a single byte touches disk, shows a
      unified diff of the current vs candidate file, and only on
      confirmation overwrites ``config.toml`` atomically.

    The page never sets ``is_dirty()`` — it performs its side effects
    directly rather than deferring to the Apply / OK gate. A shown
    diff is *advisory*; nothing lands until the user clicks "Confirm
    import".
    """

    def __init__(
        self,
        state: _DialogState,
        config_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._config_path = config_path

        hint = QLabel(
            self.tr(
                "Export writes the current config.toml to a file of your "
                "choice. Import loads a file, validates it, and shows a "
                "diff before replacing your current config."
            )
        )
        hint.setWordWrap(True)

        self.export_button = QPushButton(self.tr("Export…"))
        self.import_button = QPushButton(self.tr("Import…"))
        self.export_button.clicked.connect(self._on_export)
        self.import_button.clicked.connect(self._on_import)

        button_row = QHBoxLayout()
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.import_button)
        button_row.addStretch(1)

        self.diff_label = QLabel(
            self.tr(
                "Pick a file with Import… to see what would change."
            )
        )
        self.diff_label.setWordWrap(True)

        self.diff_view = QTextEdit(self)
        self.diff_view.setReadOnly(True)
        self.diff_view.setPlaceholderText(
            self.tr("Dry-run diff appears here after you pick a file.")
        )
        font = self.diff_view.font()
        font.setFamily("monospace")
        self.diff_view.setFont(font)

        self.confirm_import_button = QPushButton(self.tr("Confirm import"))
        self.cancel_import_button = QPushButton(self.tr("Cancel"))
        self.confirm_import_button.setEnabled(False)
        self.cancel_import_button.setEnabled(False)
        self.confirm_import_button.clicked.connect(self._on_confirm_import)
        self.cancel_import_button.clicked.connect(self._on_cancel_import)

        confirm_row = QHBoxLayout()
        confirm_row.addWidget(self.confirm_import_button)
        confirm_row.addWidget(self.cancel_import_button)
        confirm_row.addStretch(1)

        root = QVBoxLayout(self)
        root.addWidget(hint)
        root.addLayout(button_row)
        root.addWidget(self.diff_label)
        root.addWidget(self.diff_view, 1)
        root.addLayout(confirm_row)

        self._pending_import_path: Path | None = None
        self._pending_import_text: str | None = None

    # ── Export ──────────────────────────────────────────────────────────
    def _on_export(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        target, _filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Export config"),
            str(self._config_path.with_suffix(".exported.toml")),
            self.tr("TOML files (*.toml);;All files (*)"),
        )
        if not target:
            return
        try:
            text = self._config_path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Export failed"), str(exc)
            )
            return
        try:
            Path(target).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Export failed"), str(exc)
            )
            return
        QMessageBox.information(
            self,
            self.tr("Export complete"),
            self.tr("Wrote {target}.").format(target=target),
        )

    # ── Import ──────────────────────────────────────────────────────────
    def _on_import(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        source, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Import config"),
            str(self._config_path.parent),
            self.tr("TOML files (*.toml);;All files (*)"),
        )
        if not source:
            return
        source_path = Path(source)
        try:
            candidate_text = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Import failed"), str(exc)
            )
            return

        # Validate first. We deliberately import late so this page
        # stays importable even when perch.config.loader pulls in
        # heavy deps.
        from perch.config.loader import _load_and_validate
        from perch.config.schema import SchemaError

        try:
            _load_and_validate(source_path)
        except SchemaError as exc:
            QMessageBox.critical(
                self,
                self.tr("Invalid TOML"),
                self.tr("Schema error: {err}").format(err=str(exc)),
            )
            return
        except tomllib_exceptions() as exc:
            QMessageBox.critical(
                self,
                self.tr("Invalid TOML"),
                self.tr("Parse error: {err}").format(err=str(exc)),
            )
            return

        # Render unified diff vs the current file.
        import difflib

        try:
            current_text = self._config_path.read_text(encoding="utf-8")
        except OSError:
            current_text = ""
        diff_lines = list(
            difflib.unified_diff(
                current_text.splitlines(keepends=True),
                candidate_text.splitlines(keepends=True),
                fromfile=str(self._config_path),
                tofile=str(source_path),
            )
        )
        if not diff_lines:
            self.diff_view.setPlainText(
                self.tr("(no differences — current file and import are identical)")
            )
            self.confirm_import_button.setEnabled(False)
            self.cancel_import_button.setEnabled(False)
            self._pending_import_path = None
            self._pending_import_text = None
            return

        self.diff_view.setPlainText("".join(diff_lines))
        self.diff_label.setText(
            self.tr(
                "Pending import: {source}. Click Confirm import to replace "
                "the current config, or Cancel to discard."
            ).format(source=source_path)
        )
        self.confirm_import_button.setEnabled(True)
        self.cancel_import_button.setEnabled(True)
        self._pending_import_path = source_path
        self._pending_import_text = candidate_text

    def _on_confirm_import(self) -> None:
        if self._pending_import_path is None or self._pending_import_text is None:
            return
        try:
            # Re-use the loader's atomic write via the writer module.
            from perch.config.writer import atomic_write

            atomic_write(self._config_path, self._pending_import_text)
        except OSError as exc:
            QMessageBox.critical(
                self, self.tr("Import failed"), str(exc)
            )
            return
        QMessageBox.information(
            self,
            self.tr("Import complete"),
            self.tr(
                "Imported from {source}. Close and reopen this dialog to "
                "edit the new config."
            ).format(source=self._pending_import_path),
        )
        self._reset_pending()

    def _on_cancel_import(self) -> None:
        self._reset_pending()

    def _reset_pending(self) -> None:
        self._pending_import_path = None
        self._pending_import_text = None
        self.confirm_import_button.setEnabled(False)
        self.cancel_import_button.setEnabled(False)
        self.diff_view.clear()
        self.diff_label.setText(
            self.tr("Pick a file with Import… to see what would change.")
        )

    # ── _Page protocol ──────────────────────────────────────────────────
    def is_dirty(self) -> bool:
        # Import and Export both commit immediately via explicit buttons.
        return False

    def commit(self) -> None:
        return None


def tomllib_exceptions() -> tuple[type[BaseException], ...]:
    """Return the tomllib/tomlkit exception classes used by import validation.

    Kept as a helper so the page module doesn't unconditionally import
    ``tomllib`` / ``tomlkit`` at load time — those pull in non-trivial
    bytecode on Python 3.12+.
    """
    import tomllib

    import tomlkit.exceptions

    return (tomllib.TOMLDecodeError, tomlkit.exceptions.TOMLKitError)


class _PlaceholderPage(QWidget):
    """Stub page used for sections whose editor lands in a later milestone."""

    def __init__(
        self,
        message: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(label)

    def is_dirty(self) -> bool:
        return False

    def commit(self) -> None:
        return None


# ── Dialog shell ────────────────────────────────────────────────────────

_Page = (
    GeneralPage
    | WindowsPage
    | RulesPage
    | LayoutsPage
    | ProfilesPage
    | ExclusionsPage
    | HotkeysPage
    | ImportExportPage
    | _PlaceholderPage
)


class ConfigDialog(QDialog):
    """Sidebar-plus-stack settings dialog.

    Constructed with a loaded :class:`Config` and a path to the
    ``config.toml`` on disk. OK / Apply commits every dirty page into
    the tomlkit document (loaded lazily the first time a section
    commits) and calls ``writer.write_document`` to persist atomically.
    Cancel drops the working copy and leaves disk untouched.

    ``saved`` fires after a successful write so the tray controller can
    refresh its state snapshot.
    """

    saved = Signal()

    def __init__(
        self,
        config: Config,
        config_path: Path,
        parent: QWidget | None = None,
        *,
        backend: WindowBackend | None = None,
        state_store: StateStore | None = None,
        # Injected for tests so the "save" side-effect can be observed
        # without touching a real path; production callers leave it as
        # None and the dialog writes via ``writer.write_document``.
        save_callback: Callable[[Path, Any], None] | None = None,
        load_document_callback: Callable[[Path], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Perch — Preferences"))
        self.resize(720, 480)

        self._config_path = config_path
        self._backend = backend
        self._state_store = state_store
        load_doc = load_document_callback or load_document
        self._state = _DialogState(config=config, document=load_doc(config_path))
        self._save = save_callback or write_document

        self._sidebar = QListWidget(self)
        self._sidebar.setFixedWidth(160)
        self._sidebar.setAccessibleName(self.tr("Sections"))
        self._stack = QStackedWidget(self)
        self._pages: dict[str, _Page] = {}

        for section in SECTION_ORDER:
            item = QListWidgetItem(_section_label(section), self._sidebar)
            item.setData(Qt.ItemDataRole.UserRole, section)
            page = self._build_page(section)
            self._pages[section] = page
            self._stack.addWidget(page)

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.clicked.connect(self._on_apply)

        body = QHBoxLayout()
        body.addWidget(self._sidebar)
        body.addWidget(self._stack, 1)

        root = QVBoxLayout(self)
        root.addLayout(body, 1)
        root.addWidget(buttons)

        # Explicit tab-order so the sidebar (section picker) always
        # receives focus first, followed by the active page, then the
        # OK/Apply/Cancel row. Qt auto-derives tab-order from widget
        # construction order in most cases but the sidebar-before-stack
        # layout is load-bearing for keyboard navigation and is worth
        # pinning explicitly — see :file:`docs/08-ui.md` §Accessibility.
        self.setTabOrder(self._sidebar, self._stack)
        self.setTabOrder(self._stack, buttons)
        self._sidebar.setFocus()

    # ── Page factory ────────────────────────────────────────────────────
    def _build_page(self, section: str) -> _Page:
        if section == SECTION_GENERAL:
            return GeneralPage(self._state)
        if section == SECTION_WINDOWS:
            return WindowsPage(
                self._backend, self._state_store, self._state.config
            )
        if section == SECTION_RULES:
            return RulesPage(self._state)
        if section == SECTION_LAYOUTS:
            return LayoutsPage(self._state)
        if section == SECTION_PROFILES:
            return ProfilesPage(self._state)
        if section == SECTION_EXCLUSIONS:
            return ExclusionsPage(self._state)
        if section == SECTION_HOTKEYS:
            return HotkeysPage(self._state)
        if section == SECTION_IMPORT_EXPORT:
            return ImportExportPage(self._state, self._config_path)
        raise ValueError(f"unknown section: {section!r}")

    # ── Actions ─────────────────────────────────────────────────────────
    def select_section(self, section: str) -> None:
        """Programmatically switch to ``section`` (tray intent entry point)."""
        if section not in SECTION_ORDER:
            raise ValueError(f"unknown section: {section!r}")
        self._sidebar.setCurrentRow(SECTION_ORDER.index(section))

    def _on_apply(self) -> None:
        self._commit_and_save()

    def _on_ok(self) -> None:
        if self._commit_and_save():
            self.accept()

    def _commit_and_save(self) -> bool:
        """Commit dirty pages into the document and persist to disk.

        Returns False if persistence raised — the dialog stays open so
        the user can correct the error.
        """
        dirty_pages = [p for p in self._pages.values() if p.is_dirty()]
        if not dirty_pages:
            return True
        # Work on a deep copy so a mid-commit failure leaves the dialog's
        # document pristine. tomlkit nodes deep-copy cleanly; fall through
        # to the in-place document on success.
        staged = copy.deepcopy(self._state.document)
        original_document = self._state.document
        self._state.document = staged
        try:
            for page in dirty_pages:
                page.commit()
        except Exception:
            self._state.document = original_document
            log.exception("config dialog: commit failed")
            QMessageBox.critical(
                self,
                self.tr("Perch — save failed"),
                self.tr(
                    "Could not apply your changes to the config. See the "
                    "log for details. Your changes were not saved."
                ),
            )
            return False

        try:
            self._save(self._config_path, staged)
        except Exception:
            self._state.document = original_document
            log.exception("config dialog: write_document failed")
            QMessageBox.critical(
                self,
                self.tr("Perch — save failed"),
                self.tr(
                    "Could not write config.toml. See the log for details. "
                    "Your changes were not saved."
                ),
            )
            return False

        self.saved.emit()
        return True
