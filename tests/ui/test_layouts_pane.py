"""Tests for LayoutsPage and its entry editor."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomlkit

from perch.config.loader import load_or_create
from perch.config.writer import load_document
from perch.core.actions import ApplyAction, PresetGeometry
from perch.core.matching import MatchPattern
from perch.ui.dialog import SECTION_LAYOUTS, ConfigDialog, LayoutsPage
from perch.ui.entry_editor import summarise_apply, summarise_match

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _seed_config(tmp_path: Path, toml: str) -> Path:
    target = tmp_path / "config.toml"
    target.write_text(toml, encoding="utf-8")
    return target


def _open_dialog(
    tmp_path: Path, xdg_env: Path, toml: str
) -> ConfigDialog:
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    path = xdg_env / "config" / "perch" / "config.toml"
    path.write_text(toml, encoding="utf-8")
    config = load_or_create(path)

    def fake_save(p: Path, document: Any) -> None:
        p.write_text(tomlkit.dumps(document), encoding="utf-8")

    return ConfigDialog(
        config,
        path,
        save_callback=fake_save,
        load_document_callback=load_document,
    )


SIMPLE = """
[general]
theme = "auto"

[snaps.custom]
geometry = { x = "0%", y = "0%", w = "40%", h = "100%" }

[layouts.coding]
description = "Coding layout"
  [[layouts.coding.windows]]
  match = { app_id = "code" }
  geometry = "maximize"

[layouts.media]
description = "Media layout"
"""


def test_layouts_page_initial_selection_shows_first(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_LAYOUTS)
    page = dialog._pages[SECTION_LAYOUTS]
    assert isinstance(page, LayoutsPage)
    assert page._current_layout == "coding"
    assert page.description_edit.text() == "Coding layout"


def test_layouts_page_lists_every_layout_in_order(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_LAYOUTS)
    page = dialog._pages[SECTION_LAYOUTS]
    assert isinstance(page, LayoutsPage)
    names = [
        page.layouts_list.item(i).text()
        for i in range(page.layouts_list.count())
    ]
    assert names == ["coding", "media"]


def test_add_entry_then_commit_persists_to_toml(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_LAYOUTS)
    page = dialog._pages[SECTION_LAYOUTS]
    assert isinstance(page, LayoutsPage)

    # Programmatically drive "Add entry" so we don't pop a modal dialog.
    from perch.core.layouts import LayoutEntry

    entries = page._current_entries()
    assert entries is not None
    entries.append(
        LayoutEntry(
            match=MatchPattern(app_id="firefox"),
            apply=ApplyAction(geometry=PresetGeometry("left-half")),
        )
    )
    page._write_entries(entries)
    assert page.is_dirty()

    page.commit()
    saved_text = tomlkit.dumps(dialog._state.document)
    assert "firefox" in saved_text
    assert "left-half" in saved_text


def test_delete_layout_removes_from_toml(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_LAYOUTS)
    page = dialog._pages[SECTION_LAYOUTS]
    assert isinstance(page, LayoutsPage)

    # Delete "media" without the confirm-dialog blocking.
    del page._layouts["media"]
    # Drop the rename mapping for the deleted layout so commit doesn't
    # try to re-add it as a "survivor".
    del page._renames["media"]
    page._dirty = True
    page.commit()

    saved = tomlkit.dumps(dialog._state.document)
    assert "[layouts.media]" not in saved
    assert "[layouts.coding]" in saved


def test_rename_layout_preserves_entries(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_LAYOUTS)
    page = dialog._pages[SECTION_LAYOUTS]
    assert isinstance(page, LayoutsPage)

    # Simulate rename of "coding" → "dev".
    from perch.core.layouts import Layout

    rebuilt: dict[str, Layout] = {}
    for name, lay in page._layouts.items():
        if name == "coding":
            rebuilt["dev"] = Layout(
                name="dev", description=lay.description, windows=lay.windows,
            )
        else:
            rebuilt[name] = lay
    page._layouts = rebuilt
    page._renames["coding"] = "dev"
    page._dirty = True
    page.commit()

    saved = tomlkit.dumps(dialog._state.document)
    assert "[layouts.dev]" in saved
    assert "[layouts.coding]" not in saved
    assert "\"code\"" in saved or "'code'" in saved  # entry survived


def test_summarise_helpers_produce_non_empty_strings() -> None:
    match = MatchPattern(app_id="firefox", pid=42)
    action = ApplyAction(
        geometry=PresetGeometry("maximize"),
        monitor="DP-1",
        desktop=1,
    )
    assert "app_id=firefox" in summarise_match(match)
    assert "preset:maximize" in summarise_apply(action)
    assert "mon:DP-1" in summarise_apply(action)
    assert "desktop:1" in summarise_apply(action)
