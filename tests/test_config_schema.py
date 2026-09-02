"""Schema validation tests."""

from __future__ import annotations

import pytest

from perch.config.schema import CURRENT_SCHEMA_VERSION, SchemaError, validate


def test_empty_document_validates_to_defaults() -> None:
    config = validate({})
    assert config.schema_version == CURRENT_SCHEMA_VERSION
    assert config.general.start_at_login is True
    assert config.general.theme == "auto"
    assert config.exclusions == []
    assert config.rules == []


def test_future_schema_version_rejected() -> None:
    with pytest.raises(SchemaError, match="newer than this Perch"):
        validate({"schema_version": CURRENT_SCHEMA_VERSION + 1})


def test_non_integer_schema_version_rejected() -> None:
    with pytest.raises(SchemaError, match="must be an integer"):
        validate({"schema_version": "1"})


def test_zero_schema_version_rejected() -> None:
    with pytest.raises(SchemaError, match=">= 1"):
        validate({"schema_version": 0})


def test_invalid_theme_rejected() -> None:
    with pytest.raises(SchemaError, match=r"\[general\].theme"):
        validate({"general": {"theme": "sepia"}})


def test_non_bool_toggle_rejected() -> None:
    with pytest.raises(SchemaError, match="must be a boolean"):
        validate({"general": {"start_at_login": "yes"}})


def test_onboarding_completed_defaults_false_when_absent() -> None:
    """An upgrading user's config lacks the key; it must parse, not raise.

    Same default as a freshly-seeded config, so both audiences see the
    first-run wizard exactly once.
    """
    config = validate({"general": {"start_at_login": True}})
    assert config.general.onboarding_completed is False


def test_onboarding_completed_is_read_back() -> None:
    """Without this the wizard's write is never read and it shows every launch."""
    config = validate({"general": {"onboarding_completed": True}})
    assert config.general.onboarding_completed is True


def test_unknown_general_key_rejected() -> None:
    with pytest.raises(SchemaError, match="unknown keys"):
        validate({"general": {"bogus": True}})


def test_rules_must_be_array_of_tables() -> None:
    with pytest.raises(SchemaError, match=r"\[\[rules\]\]"):
        validate({"rules": {"not": "a list"}})


def test_layouts_must_be_table_of_tables() -> None:
    with pytest.raises(SchemaError, match=r"\[layouts\.coding\]"):
        validate({"layouts": {"coding": "not a table"}})


def test_exclusions_patterns_must_be_list() -> None:
    with pytest.raises(SchemaError, match="patterns"):
        validate({"exclusions": {"patterns": "not a list"}})


def test_representative_full_config_validates() -> None:
    document = {
        "schema_version": 1,
        "general": {
            "start_at_login": True,
            "restore_on_open": True,
            "notify_on_restore": False,
            "theme": "dark",
        },
        "exclusions": {"patterns": [{"app_id": "plasmashell"}]},
        "snaps": {
            "center-60": {
                "geometry": {
                    "x": "20%", "y": "20%", "w": "60%", "h": "60%",
                    "monitor": "current",
                },
                "hotkey": "Meta+C",
            }
        },
        "rules": [
            {
                "name": "Firefox",
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "maximize", "monitor": "HDMI-1"},
            }
        ],
        "layouts": {"coding": {"description": "x"}},
        "profiles": [{"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"}],
    }
    config = validate(document)
    assert config.general.theme == "dark"
    assert len(config.exclusions) == 1
    assert "center-60" in config.snaps
    assert len(config.rules) == 1
    assert config.rules[0].name == "Firefox"
    assert "coding" in config.layouts
    assert len(config.profiles) == 1


def test_profile_default_layout_must_name_a_declared_layout() -> None:
    """A dangling ``default_layout`` would otherwise fail only at runtime.

    docs/09 §Activation applies it when the profile activates, so the
    config loader is the last place a typo can be reported to the user.
    """
    with pytest.raises(SchemaError, match="not a declared layout"):
        validate(
            {
                "profiles": [
                    {
                        "name": "Docked",
                        "topology": "DP-1:2560x1440@0,0",
                        "default_layout": "codign",
                    }
                ]
            }
        )


def test_boolean_schema_version_is_rejected() -> None:
    """``bool`` is an ``int`` in Python, so the isinstance check alone let
    ``schema_version = true`` through and then compared it as 1."""
    with pytest.raises(SchemaError, match="schema_version"):
        validate({"schema_version": True})


def test_unknown_top_level_table_is_rejected() -> None:
    """docs/07 §Validation: Perch does not silently drop bad rules.

    Unknown keys inside [general] and [exclusions] were already rejected;
    a typo'd top-level table was a whole section going unread.
    """
    with pytest.raises(SchemaError, match="unknown top-level"):
        validate({"rule": [{"match": {"app_id": "firefox"}}]})
