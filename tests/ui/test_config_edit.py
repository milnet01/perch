"""Tests for the config-mutation helpers used by the dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import tomlkit

from perch.config.edit import (
    ConfigEditError,
    apply_general,
    delete_exclusion,
    delete_rule,
    reorder_exclusions,
    reorder_rules,
)

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
        )


def test_apply_general_creates_section_when_absent() -> None:
    doc = tomlkit.parse("schema_version = 1\n")
    apply_general(
        doc,
        start_at_login=True,
        restore_on_open=False,
        notify_on_restore=True,
        theme="dark",
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
    )
    delete_exclusion(doc, 0)
    out = tomlkit.dumps(doc)
    # Major comment anchors survive every operation above.
    assert "Top-of-file comment — must survive round-trip." in out
    assert "# Exclusions section — mid-document comment." in out
    assert "# Comment inside the snaps table." in out
    assert "# A representative rule." in out
