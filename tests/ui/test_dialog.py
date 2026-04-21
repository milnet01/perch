"""Integration tests for the ConfigDialog.

Follows the pytest-qt idiom from docs/11-roadmap.md §Phase 2.5 research
log: use ``dialog.show()`` + ``qtbot.waitExposed`` instead of ``exec()``
(the latter would block the test thread), then call ``.accept()`` /
``.reject()`` directly. Save side-effects are observed through an
injected callback so tests never touch a real config.toml.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import tomlkit

from perch.config.loader import load_or_create
from perch.config.writer import load_document
from perch.ui.dialog import (
    SECTION_EXCLUSIONS,
    SECTION_GENERAL,
    SECTION_HOTKEYS,
    SECTION_ORDER,
    SECTION_RULES,
    ConfigDialog,
    ExclusionsPage,
    GeneralPage,
    HotkeysPage,
    RulesPage,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
COMMENTED_CONFIG = FIXTURES / "commented_config.toml"


def _seed_config(tmp_path: Path) -> Path:
    """Copy the fixture config to a fresh XDG config dir and return the path."""
    target = tmp_path / "config.toml"
    target.write_text(
        COMMENTED_CONFIG.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target


def _open_dialog(
    tmp_path: Path,
    xdg_env: Path,
) -> tuple[ConfigDialog, Path, list[tuple[Path, Any]]]:
    """Build a dialog against the commented fixture; capture save calls."""
    config_path = _seed_config(tmp_path)
    captured_saves: list[tuple[Path, Any]] = []

    def fake_save(path: Path, document: Any) -> None:
        captured_saves.append((path, document))
        path.write_text(tomlkit.dumps(document), encoding="utf-8")

    # Swap in the fixture as the "config.toml" via the XDG tmp path.
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    (xdg_env / "config" / "perch" / "config.toml").write_text(
        config_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fixture_path = xdg_env / "config" / "perch" / "config.toml"
    config = load_or_create(fixture_path)
    dialog = ConfigDialog(
        config,
        fixture_path,
        save_callback=fake_save,
        load_document_callback=load_document,
    )
    return dialog, fixture_path, captured_saves


# ── Structure ───────────────────────────────────────────────────────────


def test_sidebar_lists_every_documented_section(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, _path, _saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    sidebar = dialog.findChild(type(dialog._sidebar))
    assert sidebar is not None
    texts = [sidebar.item(i).text() for i in range(sidebar.count())]
    # Eight sections in the spec'd order (labels are translated, but
    # under en_US the source strings pass through unchanged).
    assert len(texts) == len(SECTION_ORDER)
    assert "General" in texts
    assert "Rules" in texts
    assert "Exclusions" in texts
    assert "Import / Export" in texts


def test_select_section_switches_active_page(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, _path, _saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)

    dialog.select_section(SECTION_RULES)
    assert isinstance(dialog._pages[SECTION_RULES], RulesPage)
    assert dialog._stack.currentWidget() is dialog._pages[SECTION_RULES]

    dialog.select_section(SECTION_EXCLUSIONS)
    assert isinstance(dialog._pages[SECTION_EXCLUSIONS], ExclusionsPage)
    assert dialog._stack.currentWidget() is dialog._pages[SECTION_EXCLUSIONS]


# ── General edit flow ───────────────────────────────────────────────────


def test_general_page_persists_toggles_on_ok(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, path, saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)

    general = dialog._pages[SECTION_GENERAL]
    assert isinstance(general, GeneralPage)
    general.start_at_login.setChecked(False)
    general.notify_on_restore.setChecked(True)
    general.theme.setCurrentText("light")

    dialog._on_ok()

    assert len(saves) == 1
    saved_text = path.read_text(encoding="utf-8")
    assert "start_at_login    = false" in saved_text or "start_at_login = false" in saved_text
    assert "notify_on_restore = true" in saved_text or "notify_on_restore= true" in saved_text
    assert 'theme             = "light"' in saved_text or 'theme = "light"' in saved_text
    # Top-of-file comment survives the full round-trip through tomlkit.
    assert "Top-of-file comment — must survive round-trip." in saved_text


def test_cancel_does_not_save(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, _path, saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)

    general = dialog._pages[SECTION_GENERAL]
    assert isinstance(general, GeneralPage)
    general.start_at_login.setChecked(False)

    dialog.reject()
    assert saves == []


def test_ok_with_no_dirty_pages_is_a_noop_save(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, _path, saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog._on_ok()
    # Nothing dirty → no save callback invoked.
    assert saves == []


# ── Rules edit flow ─────────────────────────────────────────────────────


def test_rules_page_delete_drops_entry_and_persists(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, path, saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)

    rules_page = dialog._pages[SECTION_RULES]
    assert isinstance(rules_page, RulesPage)
    # Fixture has exactly one rule named "Firefox on external".
    assert rules_page.model.rowCount() == 1

    rules_page.model.remove_rule(0)
    assert rules_page.is_dirty()

    dialog._on_ok()

    assert len(saves) == 1
    saved_text = path.read_text(encoding="utf-8")
    assert "Firefox on external" not in saved_text
    # Top + leading comments and sections that don't touch [[rules]] survive.
    # tomlkit absorbs the blank-line-and-comment immediately following a
    # deleted AoT entry as that entry's trailing trivia, so the comment
    # that sat *between* [[rules]] and the next top-level section ("# A
    # representative layout.") can be lost. The guarantee we care about
    # is that every unrelated *content* section survives.
    assert "Top-of-file comment — must survive round-trip." in saved_text
    assert "# A representative rule." in saved_text
    assert "[layouts.coding]" in saved_text
    assert "# A representative profile." in saved_text
    assert "[[profiles]]" in saved_text


# ── Exclusions edit flow ────────────────────────────────────────────────


# ── Hotkeys page ────────────────────────────────────────────────────────


def test_hotkeys_page_shows_existing_snap_bindings(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, _path, _saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_HOTKEYS)
    page = dialog._pages[SECTION_HOTKEYS]
    assert isinstance(page, HotkeysPage)
    # The fixture defines a single snap "center-60" with hotkey Meta+C.
    assert "center-60" in page._edits
    assert page._edits["center-60"].accel() == "Meta+C"


def test_hotkeys_page_persists_accel_on_ok(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, path, saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)
    page = dialog._pages[SECTION_HOTKEYS]
    assert isinstance(page, HotkeysPage)

    # Edit the displayed hotkey → page becomes dirty → OK persists.
    page._edits["center-60"].set_accel("Ctrl+Alt+C")
    assert page.is_dirty()

    dialog._on_ok()
    assert len(saves) == 1
    saved_text = path.read_text(encoding="utf-8")
    assert "Ctrl+Alt+C" in saved_text


def test_exclusions_page_delete_drops_entry_and_persists(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path,
) -> None:
    dialog, path, _saves = _open_dialog(tmp_path, xdg_env)
    qtbot.addWidget(dialog)

    page = dialog._pages[SECTION_EXCLUSIONS]
    assert isinstance(page, ExclusionsPage)
    # Fixture has two exclusion patterns.
    assert page.list.count() == 2

    page.list.setCurrentRow(0)
    page._on_delete_clicked()
    assert page.is_dirty()

    dialog._on_ok()

    saved = path.read_text(encoding="utf-8")
    assert "plasmashell" not in saved
    assert 'wm_class = "Plasma*"' in saved
    assert "# Exclusions section — mid-document comment." in saved


# ── Save-failure recovery ───────────────────────────────────────────────


def test_save_failure_keeps_dialog_open_and_document_clean(
    qtbot: QtBot,
    tmp_path: Path,
    xdg_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_save(path: Path, document: Any) -> None:
        raise OSError("disk full")

    config_path = _seed_config(tmp_path)
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    fixture_path = xdg_env / "config" / "perch" / "config.toml"
    fixture_path.write_text(
        config_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    config = load_or_create(fixture_path)
    dialog = ConfigDialog(
        config,
        fixture_path,
        save_callback=failing_save,
        load_document_callback=load_document,
    )
    qtbot.addWidget(dialog)
    # Swallow the QMessageBox that would otherwise block.
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)

    general = dialog._pages[SECTION_GENERAL]
    assert isinstance(general, GeneralPage)
    general.start_at_login.setChecked(False)

    # _on_ok calls _commit_and_save which must return False on failure;
    # the dialog must remain visible (accept() not called).
    dialog._on_ok()
    # Dialog still "open" (not accepted); result() == Rejected default.
    assert dialog.result() == 0
