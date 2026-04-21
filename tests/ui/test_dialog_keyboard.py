"""Keyboard navigation tests for the config dialog (M7.b).

Covers the accessibility-audit items from :file:`docs/08-ui.md`
§Accessibility: initial focus sits on the section picker; Delete /
Backspace on the Rules table + Exclusions list removes the selected row;
the explicit tab chain walks sidebar → page → buttons.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomlkit
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox

from perch.config.loader import load_or_create
from perch.config.writer import load_document
from perch.ui.dialog import (
    SECTION_EXCLUSIONS,
    SECTION_RULES,
    ConfigDialog,
    ExclusionsPage,
    RulesPage,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
COMMENTED_CONFIG = FIXTURES / "commented_config.toml"


def _open_dialog(tmp_path: Path, xdg_env: Path) -> ConfigDialog:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        COMMENTED_CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    fixture_path = xdg_env / "config" / "perch" / "config.toml"
    fixture_path.write_text(
        config_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    def fake_save(path: Path, document: Any) -> None:
        path.write_text(tomlkit.dumps(document), encoding="utf-8")

    config = load_or_create(fixture_path)
    return ConfigDialog(
        config,
        fixture_path,
        save_callback=fake_save,
        load_document_callback=load_document,
    )


# ── Initial focus ───────────────────────────────────────────────────────


def test_dialog_initial_focus_is_on_sidebar(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    # The sidebar picker is where keyboard users land first; Tab from
    # there walks into the active page, then into the button box.
    assert dialog.focusWidget() is dialog._sidebar


# ── Tab order ───────────────────────────────────────────────────────────


def test_dialog_tab_chain_is_sidebar_then_stack_then_buttons(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    # After the explicit setTabOrder, ``nextInFocusChain`` from the
    # sidebar eventually reaches the stack, and from the stack eventually
    # reaches the button box. We walk a bounded chain and assert the
    # ordering rather than exact hops (Qt inserts internal viewport /
    # scrollbar children between user widgets).
    from PySide6.QtWidgets import QWidget
    chain: list[object] = []
    w: QWidget = dialog._sidebar
    for _ in range(200):
        nxt = w.nextInFocusChain()
        if nxt is None:
            break
        w = nxt
        chain.append(w)
        if w is dialog._sidebar:
            break
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    stack_index = next(
        (i for i, x in enumerate(chain) if x is dialog._stack), -1
    )
    buttons_index = next(
        (
            i
            for i, x in enumerate(chain)
            if x is buttons or getattr(x, "parent", lambda: None)() is buttons
        ),
        -1,
    )
    assert stack_index != -1, "stack not reachable via Tab"
    assert buttons_index != -1, "button box not reachable via Tab"
    assert stack_index < buttons_index, "sidebar → stack → buttons expected"


# ── Delete key on rules / exclusions ───────────────────────────────────


def test_delete_key_on_rules_view_removes_selected_row(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.select_section(SECTION_RULES)
    page = dialog._pages[SECTION_RULES]
    assert isinstance(page, RulesPage)
    assert page.model.rowCount() == 1

    page.view.setFocus()
    page.view.selectRow(0)
    QTest.keyClick(page.view, Qt.Key.Key_Delete)

    assert page.model.rowCount() == 0


def test_backspace_on_rules_view_removes_selected_row(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.select_section(SECTION_RULES)
    page = dialog._pages[SECTION_RULES]
    assert isinstance(page, RulesPage)

    page.view.setFocus()
    page.view.selectRow(0)
    QTest.keyClick(page.view, Qt.Key.Key_Backspace)

    assert page.model.rowCount() == 0


def test_delete_key_on_exclusions_list_removes_selected_row(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.select_section(SECTION_EXCLUSIONS)
    page = dialog._pages[SECTION_EXCLUSIONS]
    assert isinstance(page, ExclusionsPage)
    assert page.list.count() == 2

    page.list.setFocus()
    page.list.setCurrentRow(0)
    QTest.keyClick(page.list, Qt.Key.Key_Delete)

    assert page.list.count() == 1


def test_backspace_on_exclusions_list_removes_selected_row(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.select_section(SECTION_EXCLUSIONS)
    page = dialog._pages[SECTION_EXCLUSIONS]
    assert isinstance(page, ExclusionsPage)

    page.list.setFocus()
    page.list.setCurrentRow(0)
    QTest.keyClick(page.list, Qt.Key.Key_Backspace)

    assert page.list.count() == 1


# ── Accessible names (screen-reader coverage) ───────────────────────────


def test_dialog_sidebar_and_edit_surfaces_have_accessible_names(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    assert dialog._sidebar.accessibleName() == "Sections"
    rules = dialog._pages[SECTION_RULES]
    assert isinstance(rules, RulesPage)
    assert rules.view.accessibleName() == "Rules table"
    assert rules.view.accessibleDescription()
    exclusions = dialog._pages[SECTION_EXCLUSIONS]
    assert isinstance(exclusions, ExclusionsPage)
    assert exclusions.list.accessibleName() == "Exclusion patterns"
    assert exclusions.list.accessibleDescription()
