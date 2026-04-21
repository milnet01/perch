"""Tests for ProfilesPage — profile CRUD + overrides editor wiring."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit

from perch.config.loader import load_or_create
from perch.config.writer import load_document
from perch.core.actions import ApplyAction, PresetGeometry
from perch.core.layouts import LayoutEntry
from perch.core.matching import MatchPattern
from perch.core.profiles import Profile, ProfileOverride
from perch.ui.dialog import SECTION_PROFILES, ConfigDialog, ProfilesPage

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _open_dialog(
    tmp_path: Path, xdg_env: Path, toml: str
) -> ConfigDialog:
    (xdg_env / "config" / "perch").mkdir(parents=True, exist_ok=True)
    path = xdg_env / "config" / "perch" / "config.toml"
    path.write_text(toml, encoding="utf-8")
    config = load_or_create(path)

    def fake_save(p: Path, document: object) -> None:
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

[layouts.coding]
description = "Coding layout"
  [[layouts.coding.windows]]
  match = { app_id = "code" }
  geometry = "maximize"

[layouts.media]
description = "Media layout"

[[profiles]]
name = "Laptop only"
topology = "eDP-1:1920x1200@0,0"
default_layout = "coding"
"""


def test_profiles_page_lists_existing(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)
    assert page.profiles_list.count() == 1
    assert page.profiles_list.item(0).text() == "Laptop only"


def test_profiles_page_loads_selected_profile_fields(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)
    assert page.name_edit.text() == "Laptop only"
    assert page.topology_edit.text() == "eDP-1:1920x1200@0,0"
    assert page.default_layout_combo.currentData() == "coding"


def test_editing_name_marks_dirty_and_updates_sidebar(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)
    page.name_edit.setText("Mobile")
    page._on_name_edited()
    assert page.is_dirty()
    assert page.profiles_list.item(0).text() == "Mobile"


def test_editing_topology_commits_to_toml(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)

    page.topology_edit.setText("HDMI-1:2560x1440@0,0")
    page._on_topology_edited()
    page.commit()

    out = tomlkit.dumps(dialog._state.document)
    assert "HDMI-1" in out
    assert "eDP-1:1920x1200@0,0" not in out


def test_add_override_persists_on_commit(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)

    overrides = page._override_rows()
    assert overrides is not None
    overrides.append(
        ProfileOverride(
            layout="coding",
            windows=(
                LayoutEntry(
                    match=MatchPattern(app_id="konsole"),
                    apply=ApplyAction(
                        geometry=PresetGeometry("bottom-half"),
                    ),
                ),
            ),
        )
    )
    page._write_overrides(overrides)
    page.commit()

    out = tomlkit.dumps(dialog._state.document)
    assert "[[profiles.override]]" in out
    assert "konsole" in out
    assert "bottom-half" in out


def test_delete_profile_removes_from_toml(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)

    # Simulate delete bypassing the confirmation dialog.
    page._deleted_originals.append(0)
    del page._profiles[0]
    del page._origin[0]
    page._dirty = True
    page.commit()

    out = tomlkit.dumps(dialog._state.document)
    assert "Laptop only" not in out


def test_add_profile_then_commit_appends_aot_entry(
    qtbot: QtBot, tmp_path: Path, xdg_env: Path
) -> None:
    dialog = _open_dialog(tmp_path, xdg_env, SIMPLE)
    qtbot.addWidget(dialog)
    dialog.select_section(SECTION_PROFILES)
    page = dialog._pages[SECTION_PROFILES]
    assert isinstance(page, ProfilesPage)

    page._profiles.append(
        Profile(
            name="Docked",
            topology="DP-1:3840x2160@0,0",
            default_layout="media",
        )
    )
    page._origin.append(None)
    page._dirty = True
    page.commit()

    out = tomlkit.dumps(dialog._state.document)
    assert "Docked" in out
    assert "DP-1:3840x2160@0,0" in out
