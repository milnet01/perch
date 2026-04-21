"""Config dialog — QListWidget sidebar + QStackedWidget pages.

Layout per ``docs/08-ui.md`` §Config dialog. M3.b ships a runnable dialog
with:

* General section — the four toggles / combo edit-and-save round-trip.
* Rules section — read-only summary rows, drag-reorder + delete driven
  by :class:`RulesModel`; full per-cell editing lands in M3.c.
* Exclusions section — stub list with delete + drag-reorder.
* Windows / Layouts / Profiles / Hotkeys / Import-Export — pages exist
  (so the sidebar renders every documented row) but carry a "Coming in a
  later milestone" placeholder. Wiring them up is scheduled work; see
  ``docs/11-roadmap.md`` M3.c and the roadmap post-M3 list.

Save path: the dialog holds the tomlkit :class:`TOMLDocument` parsed from
``config.toml`` at open time and mutates it via :mod:`perch.config.edit`.
``writer.write_document`` then performs the atomic-replace recipe. The
user's comments survive.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from perch.config import Config
from perch.config.edit import (
    apply_general,
    delete_exclusion,
    delete_rule,
    reorder_exclusions,
    reorder_rules,
)
from perch.config.schema import VALID_THEMES
from perch.config.writer import load_document, write_document
from perch.core.rules import Rule

from .rules_model import RulesModel
from .widgets import HotkeyEdit

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


class HotkeysPage(QWidget):
    """Hotkeys section — live :class:`HotkeyEdit` next to each snap preset.

    M3.c ships the widget + a browse-and-rebind UX inside the dialog's
    working copy; the actual registration path (KGlobalAccel on Plasma,
    GlobalShortcuts portal on Flathub, ``XGrabKey`` on X11) lands with
    the real backends in M4 / M5. Until those arrive the working-copy
    edits round-trip through the dialog but are **not yet persisted** —
    the page is visibly not-dirty on close so Cancel and OK both leave
    disk alone. A visible banner at the top makes that contract
    explicit to avoid a silent "why isn't my hotkey working" surprise.
    """

    def __init__(
        self, state: _DialogState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._edits: dict[str, HotkeyEdit] = {}

        root = QVBoxLayout(self)
        notice = QLabel(
            self.tr(
                "Previewing hotkey bindings. Edits made here are not yet "
                "saved to config.toml — the registration transports "
                "(KGlobalAccel, portal, XGrabKey) land with the real "
                "backends in M4 / M5."
            )
        )
        notice.setWordWrap(True)
        root.addWidget(notice)

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
            for preset in presets:
                edit = HotkeyEdit(self)
                if preset.hotkey:
                    edit.set_accel(preset.hotkey)
                self._edits[preset.name] = edit
                form.addRow(preset.name, edit)
            root.addLayout(form)
        root.addStretch(1)

    def is_dirty(self) -> bool:
        # M3.c scope: preview-only. See the class docstring.
        return False

    def commit(self) -> None:
        return None


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

_Page = GeneralPage | RulesPage | ExclusionsPage | HotkeysPage | _PlaceholderPage


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
        if section == SECTION_RULES:
            return RulesPage(self._state)
        if section == SECTION_EXCLUSIONS:
            return ExclusionsPage(self._state)
        if section == SECTION_HOTKEYS:
            return HotkeysPage(self._state)
        placeholders = {
            SECTION_WINDOWS: self.tr(
                "The live window list arrives with the real backend in "
                "M4 (X11) and M5 (KWin)."
            ),
            SECTION_LAYOUTS: self.tr(
                "The per-rule layout editor uses the new match and "
                "geometry widgets; it lands alongside the real backend "
                "in M4 / M5."
            ),
            SECTION_PROFILES: self.tr(
                "The profile editor surfaces the match and geometry "
                "widgets per monitor topology; it lands alongside the "
                "real backend in M4 / M5."
            ),
            SECTION_IMPORT_EXPORT: self.tr(
                "Config import / export + dry-run diff viewer land in a "
                "follow-up UX milestone."
            ),
        }
        return _PlaceholderPage(placeholders[section])

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
