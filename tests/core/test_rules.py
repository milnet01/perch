"""Tests for :mod:`perch.core.rules`."""

from __future__ import annotations

import pytest

from perch.core.rules import (
    Context,
    RuleValidationError,
    parse_rules,
)


def test_parse_minimal_rule() -> None:
    [r] = parse_rules(
        [
            {
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "maximize"},
            }
        ]
    )
    assert r.name is None
    assert r.match.app_id == "firefox"
    assert r.context.is_any()


def test_parse_rule_with_context() -> None:
    [r] = parse_rules(
        [
            {
                "name": "Editor on DP-1 when docked",
                "match": {"app_id": "code"},
                "apply": {"geometry": "maximize", "monitor": "DP-1"},
                "context": {"profile": "Docked", "layout": "coding", "desktop": 1},
            }
        ]
    )
    assert r.name == "Editor on DP-1 when docked"
    assert r.context == Context(profile="Docked", layout="coding", desktop=1)


def test_missing_match_rejected() -> None:
    with pytest.raises(RuleValidationError, match="missing 'match'"):
        parse_rules([{"apply": {"geometry": "maximize"}}])


def test_missing_apply_rejected() -> None:
    with pytest.raises(RuleValidationError, match="missing 'apply'"):
        parse_rules([{"match": {"app_id": "firefox"}}])


def test_empty_match_rejected() -> None:
    with pytest.raises(RuleValidationError, match="empty match"):
        parse_rules([{"match": {}, "apply": {"geometry": "maximize"}}])


def test_catch_all_match_accepted() -> None:
    [r] = parse_rules(
        [
            {
                "match": {"catch_all": True},
                "apply": {"geometry": "maximize"},
            }
        ]
    )
    assert r.match.catch_all is True


def test_unknown_key_rejected() -> None:
    with pytest.raises(RuleValidationError, match="unknown keys"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "typo": True,
                }
            ]
        )


def test_non_table_rejected() -> None:
    with pytest.raises(RuleValidationError, match="must be a table"):
        parse_rules(["a string"])  # type: ignore[list-item]


def test_non_string_name_rejected() -> None:
    with pytest.raises(RuleValidationError, match="name must be a string"):
        parse_rules(
            [
                {
                    "name": 42,
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        )


def test_context_unknown_key_rejected() -> None:
    with pytest.raises(RuleValidationError, match="unknown keys"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": {"activity": "work"},
                }
            ]
        )


def test_context_non_int_desktop_rejected() -> None:
    with pytest.raises(RuleValidationError, match="desktop must be an integer"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": {"desktop": "current"},
                }
            ]
        )


def test_context_negative_desktop_rejected() -> None:
    with pytest.raises(RuleValidationError, match="desktop index must be non-negative"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": {"desktop": -1},
                }
            ]
        )


# ── Context.matches ────────────────────────────────────────────────────────
def test_context_matches_unspecified_is_wildcard() -> None:
    c = Context()
    assert c.matches("AnyProfile", "AnyLayout", 0)


def test_context_profile_gates() -> None:
    c = Context(profile="Docked")
    assert c.matches("Docked", None, 0)
    assert not c.matches("Laptop", None, 0)


def test_context_layout_gates() -> None:
    c = Context(layout="coding")
    assert c.matches(None, "coding", 0)
    assert not c.matches(None, "writing", 0)


def test_context_desktop_gates() -> None:
    c = Context(desktop=2)
    assert c.matches(None, None, 2)
    assert not c.matches(None, None, 1)


def test_context_all_fields_must_match() -> None:
    c = Context(profile="Docked", layout="coding", desktop=1)
    assert c.matches("Docked", "coding", 1)
    assert not c.matches("Docked", "coding", 2)
    assert not c.matches("Docked", "writing", 1)
    assert not c.matches("Laptop", "coding", 1)


def test_action_error_wrapped_into_rule_error() -> None:
    """The parser must rewrap :class:`ActionValidationError` as
    :class:`RuleValidationError` so callers have a single exception to catch."""
    with pytest.raises(RuleValidationError, match="contradiction"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"maximized": True, "geometry": "maximize"},
                }
            ]
        )


def test_match_error_wrapped_into_rule_error() -> None:
    with pytest.raises(RuleValidationError, match="not a valid regex"):
        parse_rules(
            [
                {
                    "match": {"title": r"[unclosed"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        )
