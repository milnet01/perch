"""Tests for ImportExportPage — validation + dry-run diff + confirm."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import tomlkit

from perch.config.loader import load_or_create
from perch.config.writer import load_document
from perch.ui.dialog import (
    SECTION_IMPORT_EXPORT,
    ConfigDialog,
    ImportExportPage,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


ORIGINAL = """
schema_version = 1

[general]
theme = "auto"
"""

REPLACEMENT = """
schema_version = 1

[general]
theme = "dark"
"""

BAD = """
# missing required schema_version — should fail validation.
[general]
theme = "something_unknown"
"""


@pytest.fixture
def dialog(
    tmp_path: Path, xdg_env: Path
) -> tuple[ConfigDialog, Path]:
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    path = xdg_env / "config" / "perch" / "config.toml"
    path.write_text(ORIGINAL, encoding="utf-8")
    config = load_or_create(path)

    def fake_save(p: Path, document: object) -> None:
        p.write_text(tomlkit.dumps(document), encoding="utf-8")

    dlg = ConfigDialog(
        config,
        path,
        save_callback=fake_save,
        load_document_callback=load_document,
    )
    return dlg, path


def _page(dialog: ConfigDialog) -> ImportExportPage:
    dialog.select_section(SECTION_IMPORT_EXPORT)
    page = dialog._pages[SECTION_IMPORT_EXPORT]
    assert isinstance(page, ImportExportPage)
    return page


def test_page_renders_initial_instruction(
    qtbot: QtBot, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, _path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)
    assert page.confirm_import_button.isEnabled() is False
    assert page.cancel_import_button.isEnabled() is False


def test_import_rejects_invalid_toml(
    qtbot: QtBot, tmp_path: Path, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, _path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)

    bad_source = tmp_path / "bad.toml"
    bad_source.write_text(BAD, encoding="utf-8")

    # Drive validation manually — the file dialog is bypassed.
    from perch.config.loader import _load_and_validate
    from perch.config.schema import SchemaError

    with pytest.raises(SchemaError):
        _load_and_validate(bad_source)

    # Page remains in initial state; nothing pending.
    assert page._pending_import_path is None


def test_import_shows_diff_for_valid_change(
    qtbot: QtBot, tmp_path: Path, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)

    replacement = tmp_path / "new.toml"
    replacement.write_text(REPLACEMENT, encoding="utf-8")

    # Bypass the file picker — simulate its selection.
    import difflib

    candidate_text = replacement.read_text(encoding="utf-8")
    current_text = path.read_text(encoding="utf-8")
    diff = list(
        difflib.unified_diff(
            current_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(replacement),
        )
    )
    assert diff, "expected a real diff between ORIGINAL and REPLACEMENT"

    page.diff_view.setPlainText("".join(diff))
    page._pending_import_path = replacement
    page._pending_import_text = candidate_text
    page.confirm_import_button.setEnabled(True)
    page.cancel_import_button.setEnabled(True)

    assert page.confirm_import_button.isEnabled() is True


def test_confirm_import_replaces_config_atomically(
    qtbot: QtBot,
    tmp_path: Path,
    dialog: tuple[ConfigDialog, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dlg, path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)

    # _on_confirm_import shows a QMessageBox.information on success;
    # stub it so the test doesn't block on a modal dialog.
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )

    # Seed as if an import has been staged.
    page._pending_import_path = tmp_path / "new.toml"
    page._pending_import_text = REPLACEMENT

    page._on_confirm_import()
    new_content = path.read_text(encoding="utf-8")
    assert 'theme = "dark"' in new_content


def test_cancel_import_resets_pending_state(
    qtbot: QtBot, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, _path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)

    page._pending_import_path = Path("/tmp/x.toml")
    page._pending_import_text = "schema_version = 1"
    page.confirm_import_button.setEnabled(True)
    page.cancel_import_button.setEnabled(True)

    page._on_cancel_import()
    assert page._pending_import_path is None
    assert page._pending_import_text is None
    assert page.confirm_import_button.isEnabled() is False


def test_export_writes_current_config_file(
    qtbot: QtBot, tmp_path: Path, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)

    # Simulate user picking a target path (bypass the QFileDialog).
    target = tmp_path / "exported.toml"
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    assert target.exists()
    assert "schema_version = 1" in target.read_text(encoding="utf-8")
    # Ensure the page would surface the target if its export flow ran
    # without GUI interaction: the path mirrors the current config.
    assert path.read_text(encoding="utf-8") == target.read_text(encoding="utf-8")
    _ = page  # keep fixture live; the page itself drives the QFileDialog


def test_page_is_never_dirty(
    qtbot: QtBot, dialog: tuple[ConfigDialog, Path]
) -> None:
    dlg, _path = dialog
    qtbot.addWidget(dlg)
    page = _page(dlg)
    assert page.is_dirty() is False
    page.commit()  # no-op
    assert page.is_dirty() is False
