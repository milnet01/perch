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
        "snaps": {"center-60": {"geometry": {}, "hotkey": "Meta+C"}},
        "rules": [{"name": "Firefox", "match": {"app_id": "firefox"}, "apply": {}}],
        "layouts": {"coding": {"description": "x"}},
        "profiles": [{"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"}],
    }
    config = validate(document)
    assert config.general.theme == "dark"
    assert len(config.exclusions) == 1
    assert len(config.rules) == 1
    assert "coding" in config.layouts
    assert len(config.profiles) == 1
