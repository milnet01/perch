"""Tests for the config-mutation helpers used by the dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import tomlkit

from perch.config.edit import (
    ConfigEditError,
    add_layout,
    add_layout_entry,
    apply_general,
    apply_snap_hotkey,
    delete_exclusion,
    delete_layout,
    delete_layout_entry,
    delete_rule,
    rename_layout,
    reorder_exclusions,
    reorder_layout_entries,
    reorder_rules,
    set_layout_description,
    update_layout_entry,
)
from perch.core.actions import (
    AbsoluteGeometry,
    ApplyAction,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.layouts import LayoutEntry
from perch.core.matching import MatchPattern

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
COMMENTED_CONFIG = FIXTURES / "commented_config.toml"


def _load_fixture() -> tomlkit.toml_document.TOMLDocument:
    return tomlkit.parse(COMMENTED_CONFIG.read_text(encoding="utf-8"))


# ── apply_general ───────────────────────────────────────────────────────


def test_apply_general_flips_toggles_and_preserves_comments() -> None:
    doc = _load_fixture()
    apply_general(
        doc,
        start_at_login=False,
        restore_on_open=False,
        notify_on_restore=True,
        theme="light",
        onboarding_completed=False,
    )
    out = tomlkit.dumps(doc)
    assert "Top-of-file comment — must survive round-trip." in out
    assert "# Comment directly above [general]." in out
    assert "start_at_login    = false" in out or "start_at_login = false" in out
    assert 'theme             = "light"' in out or 'theme = "light"' in out
    # Inline comments on the edited keys survive tomlkit's in-place rewrite.
    assert "inline comment on start_at_login" in out
    assert "inline comment on theme" in out


def test_apply_general_rejects_unknown_theme() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        apply_general(
            doc,
            start_at_login=True,
            restore_on_open=True,
            notify_on_restore=False,
            theme="solarized",
            onboarding_completed=False,
        )


def test_apply_general_creates_section_when_absent() -> None:
    doc = tomlkit.parse("schema_version = 1\n")
    apply_general(
        doc,
        start_at_login=True,
        restore_on_open=False,
        notify_on_restore=True,
        theme="dark",
        onboarding_completed=True,
    )
    rendered = tomlkit.dumps(doc)
    assert "[general]" in rendered
    assert 'theme = "dark"' in rendered


# ── reorder_rules / delete_rule ─────────────────────────────────────────


def _two_rule_doc() -> tomlkit.toml_document.TOMLDocument:
    return tomlkit.parse(
        "# top comment\n"
        "schema_version = 1\n"
        "\n"
        "[[rules]]\n"
        'name = "first"\n'
        'match = { app_id = "firefox" }\n'
        'apply = { geometry = "maximize" }\n'
        "\n"
        "[[rules]]\n"
        'name = "second"\n'
        'match = { app_id = "konsole" }\n'
        'apply = { geometry = "left-half" }\n'
    )


def test_reorder_rules_swaps_entries() -> None:
    doc = _two_rule_doc()
    reorder_rules(doc, [1, 0])
    rules = doc.get("rules")
    assert rules is not None
    assert rules[0]["name"] == "second"
    assert rules[1]["name"] == "first"


def test_reorder_rules_rejects_invalid_permutation() -> None:
    doc = _two_rule_doc()
    with pytest.raises(ConfigEditError):
        reorder_rules(doc, [0, 0])
    with pytest.raises(ConfigEditError):
        reorder_rules(doc, [0, 1, 2])


def test_delete_rule_drops_entry_and_preserves_others() -> None:
    doc = _two_rule_doc()
    delete_rule(doc, 0)
    rules = doc.get("rules")
    assert rules is not None
    assert len(rules) == 1
    assert rules[0]["name"] == "second"


def test_delete_rule_rejects_out_of_range_index() -> None:
    doc = _two_rule_doc()
    with pytest.raises(ConfigEditError):
        delete_rule(doc, 5)


# ── reorder_exclusions / delete_exclusion ───────────────────────────────


def test_reorder_exclusions_swaps_entries() -> None:
    doc = _load_fixture()
    # fixture has two exclusion patterns.
    reorder_exclusions(doc, [1, 0])
    exclusions: Any = doc["exclusions"]
    patterns: Any = exclusions["patterns"]
    assert patterns[0]["wm_class"] == "Plasma*"
    assert patterns[1]["app_id"] == "plasmashell"


def test_delete_exclusion_drops_entry() -> None:
    doc = _load_fixture()
    delete_exclusion(doc, 0)  # drop the plasmashell entry
    exclusions: Any = doc["exclusions"]
    patterns = exclusions["patterns"]
    assert len(patterns) == 1
    assert patterns[0]["wm_class"] == "Plasma*"


def test_delete_exclusion_rejects_out_of_range_index() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        delete_exclusion(doc, 10)


def test_fixture_file_round_trips_after_edits() -> None:
    """Whole-doc round-trip: mutate + serialise + ensure comments survive."""
    doc = _load_fixture()
    apply_general(
        doc,
        start_at_login=False,
        restore_on_open=True,
        notify_on_restore=False,
        theme="auto",
        onboarding_completed=False,
    )
    delete_exclusion(doc, 0)
    out = tomlkit.dumps(doc)
    # Major comment anchors survive every operation above.
    assert "Top-of-file comment — must survive round-trip." in out
    assert "# Exclusions section — mid-document comment." in out
    assert "# Comment inside the snaps table." in out
    assert "# A representative rule." in out


# ── Layout mutators ─────────────────────────────────────────────────────


def _entry(app_id: str, preset: str) -> LayoutEntry:
    return LayoutEntry(
        match=MatchPattern(app_id=app_id),
        apply=ApplyAction(geometry=PresetGeometry(preset)),
    )


def test_add_layout_creates_new_table() -> None:
    doc = _load_fixture()
    add_layout(doc, "media", description="Media layout")
    out = tomlkit.dumps(doc)
    assert "[layouts.media]" in out
    assert 'description = "Media layout"' in out


def test_add_layout_rejects_duplicate() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        add_layout(doc, "coding")


def test_add_layout_rejects_empty_name() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        add_layout(doc, "   ")


def test_rename_layout_swaps_key_preserves_entries() -> None:
    doc = _load_fixture()
    rename_layout(doc, "coding", "dev")
    out = tomlkit.dumps(doc)
    assert "[layouts.dev]" in out
    assert "[layouts.coding]" not in out
    # The sub-table entry survives the rename.
    assert '"code"' in out or "'code'" in out


def test_rename_layout_rejects_missing_source() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        rename_layout(doc, "nope", "something")


def test_rename_layout_rejects_colliding_target() -> None:
    doc = _load_fixture()
    add_layout(doc, "dev")
    with pytest.raises(ConfigEditError):
        rename_layout(doc, "coding", "dev")


def test_delete_layout_removes_table() -> None:
    doc = _load_fixture()
    delete_layout(doc, "coding")
    out = tomlkit.dumps(doc)
    assert "[layouts.coding]" not in out


def test_set_layout_description_rewrites_in_place() -> None:
    doc = _load_fixture()
    set_layout_description(doc, "coding", "Two panes")
    out = tomlkit.dumps(doc)
    assert 'description = "Two panes"' in out


def test_add_layout_entry_appends() -> None:
    doc = _load_fixture()
    add_layout_entry(doc, "coding", _entry("firefox", "right-half"))
    out = tomlkit.dumps(doc)
    assert "firefox" in out
    assert "right-half" in out


def test_update_layout_entry_replaces_at_index() -> None:
    doc = _load_fixture()
    update_layout_entry(doc, "coding", 0, _entry("neovim", "left-half"))
    out = tomlkit.dumps(doc)
    assert "neovim" in out
    assert "left-half" in out


def test_update_layout_entry_rejects_out_of_range() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        update_layout_entry(doc, "coding", 99, _entry("x", "maximize"))


def test_delete_layout_entry_removes_at_index() -> None:
    doc = _load_fixture()
    add_layout_entry(doc, "coding", _entry("zzz-added-then-deleted", "right-half"))
    delete_layout_entry(doc, "coding", 1)
    out = tomlkit.dumps(doc)
    assert "zzz-added-then-deleted" not in out


def test_reorder_layout_entries_respects_permutation() -> None:
    doc = _load_fixture()
    add_layout_entry(doc, "coding", _entry("firefox", "right-half"))
    add_layout_entry(doc, "coding", _entry("konsole", "bottom-half"))
    reorder_layout_entries(doc, "coding", [2, 0, 1])
    out = tomlkit.dumps(doc)
    # The first entry should now be konsole.
    first_after = out.index("konsole")
    first_code = out.index('"code"') if '"code"' in out else out.index("'code'")
    assert first_after < first_code


def test_reorder_layout_entries_rejects_bad_permutation() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        reorder_layout_entries(doc, "coding", [0, 0])


def test_layout_entry_with_percent_geometry_roundtrips() -> None:
    doc = _load_fixture()
    add_layout_entry(
        doc,
        "coding",
        LayoutEntry(
            match=MatchPattern(wm_class="Emacs"),
            apply=ApplyAction(
                geometry=PercentGeometry(0.0, 0.0, 0.5, 1.0),
                monitor="primary",
            ),
        ),
    )
    out = tomlkit.dumps(doc)
    assert "Emacs" in out
    assert "50%" in out
    assert "primary" in out


def test_layout_entry_with_absolute_geometry_roundtrips() -> None:
    doc = _load_fixture()
    add_layout_entry(
        doc,
        "coding",
        LayoutEntry(
            match=MatchPattern(app_id="term"),
            apply=ApplyAction(
                geometry=AbsoluteGeometry(x=10, y=20, w=800, h=600),
            ),
        ),
    )
    out = tomlkit.dumps(doc)
    assert '"term"' in out or "'term'" in out
    assert "800" in out
    assert "600" in out


# ── apply_snap_hotkey ───────────────────────────────────────────────────


def test_apply_snap_hotkey_sets_new_binding() -> None:
    doc = _load_fixture()
    apply_snap_hotkey(doc, "center-60", "Meta+Shift+C")
    out = tomlkit.dumps(doc)
    assert 'hotkey   = "Meta+Shift+C"' in out or '"Meta+Shift+C"' in out


def test_apply_snap_hotkey_none_removes_key() -> None:
    doc = _load_fixture()
    apply_snap_hotkey(doc, "center-60", None)
    out = tomlkit.dumps(doc)
    assert "hotkey" not in out.split("[snaps.\"center-60\"]")[1].split("[")[0]


def test_apply_snap_hotkey_missing_snap_raises() -> None:
    doc = _load_fixture()
    with pytest.raises(ConfigEditError):
        apply_snap_hotkey(doc, "no-such-snap", "Meta+X")


# ── Profile mutators ────────────────────────────────────────────────────


def _profile_doc() -> tomlkit.toml_document.TOMLDocument:
    return tomlkit.parse(
        "schema_version = 1\n"
        "\n"
        "[[profiles]]\n"
        'name = "Laptop only"\n'
        'topology = "eDP-1:1920x1200@0,0"\n'
        'default_layout = "coding"\n'
    )


def test_add_profile_appends_new_table() -> None:
    doc = _profile_doc()
    from perch.config.edit import add_profile

    add_profile(doc, name="Docked", topology="DP-1:1920x1080@0,0")
    out = tomlkit.dumps(doc)
    assert "Docked" in out
    assert "DP-1" in out


def test_add_profile_rejects_duplicate_name() -> None:
    doc = _profile_doc()
    from perch.config.edit import add_profile

    with pytest.raises(ConfigEditError):
        add_profile(doc, name="Laptop only", topology="DP-1:1920x1080@0,0")


def test_add_profile_rejects_duplicate_topology() -> None:
    doc = _profile_doc()
    from perch.config.edit import add_profile

    with pytest.raises(ConfigEditError):
        add_profile(
            doc, name="Second", topology="eDP-1:1920x1200@0,0"
        )


def test_rename_profile_changes_name_in_place() -> None:
    doc = _profile_doc()
    from perch.config.edit import rename_profile

    rename_profile(doc, 0, "Mobile")
    out = tomlkit.dumps(doc)
    assert "Mobile" in out
    assert "Laptop only" not in out


def test_delete_profile_drops_array_entry() -> None:
    doc = _profile_doc()
    from perch.config.edit import add_profile, delete_profile

    add_profile(doc, name="Docked", topology="DP-1:1920x1080@0,0")
    delete_profile(doc, 0)  # drop the laptop entry
    out = tomlkit.dumps(doc)
    assert "Laptop only" not in out
    assert "Docked" in out


def test_set_profile_field_rewrites_topology() -> None:
    doc = _profile_doc()
    from perch.config.edit import set_profile_field

    set_profile_field(doc, 0, "topology", "HDMI-1:2560x1440@0,0")
    out = tomlkit.dumps(doc)
    assert "HDMI-1" in out
    assert "eDP-1" not in out


def test_set_profile_field_none_removes_default_layout() -> None:
    doc = _profile_doc()
    from perch.config.edit import set_profile_field

    set_profile_field(doc, 0, "default_layout", None)
    out = tomlkit.dumps(doc)
    assert "default_layout" not in out


def test_set_profile_overrides_replaces_wholesale() -> None:
    doc = _profile_doc()
    from perch.config.edit import set_profile_overrides

    set_profile_overrides(
        doc,
        0,
        [
            (
                "coding",
                [
                    LayoutEntry(
                        match=MatchPattern(app_id="code"),
                        apply=ApplyAction(
                            geometry=PresetGeometry("maximize"),
                            monitor="DP-1",
                        ),
                    ),
                ],
            ),
        ],
    )
    out = tomlkit.dumps(doc)
    assert "[[profiles.override]]" in out
    assert "maximize" in out
    assert "DP-1" in out


def test_set_profile_overrides_empty_clears_the_array() -> None:
    doc = _profile_doc()
    from perch.config.edit import set_profile_overrides

    # First add something.
    set_profile_overrides(
        doc,
        0,
        [("coding", [LayoutEntry(MatchPattern(app_id="code"),
                                  ApplyAction(geometry=PresetGeometry("maximize")))])],
    )
    # Then clear it.
    set_profile_overrides(doc, 0, [])
    out = tomlkit.dumps(doc)
    assert "[[profiles.override]]" not in out
