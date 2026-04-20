"""Defensive-input coverage for the core parsers.

Each parser in :mod:`perch.core` validates its own inputs rather than
trusting upstream callers — this keeps error messages pinpoint when a
user crafts an unusual TOML document, and it lets us swap callers later
without re-auditing the parse chain. These tests exercise the defensive
branches that are unreachable from the normal parse pipeline but still
need coverage per the M2 roadmap ("Rules engine has 100% line coverage").
"""

from __future__ import annotations

import pytest

from perch.core.actions import ActionValidationError, parse_action, parse_monitor
from perch.core.layouts import LayoutValidationError, parse_layout_window
from perch.core.matching import MatchValidationError, parse_match
from perch.core.rules import RuleValidationError, parse_rules


# ── parse_match ────────────────────────────────────────────────────────────
def test_parse_match_none_becomes_empty() -> None:
    p = parse_match(None, "x")
    assert p.is_empty() and not p.catch_all


def test_parse_match_non_string_title_rejected() -> None:
    with pytest.raises(MatchValidationError, match="regex string"):
        parse_match({"title": 42}, "x")


def test_parse_match_non_string_type_rejected() -> None:
    with pytest.raises(MatchValidationError, match="comma-separated"):
        parse_match({"type": 3}, "x")


# ── parse_action ───────────────────────────────────────────────────────────
def test_parse_action_none_becomes_empty_raises_no_effect() -> None:
    with pytest.raises(ActionValidationError, match="no effect"):
        parse_action(None, "x")


def test_parse_action_geometry_mixed_string_reported_as_non_percent() -> None:
    # When one "value" is a non-matching string, the classifier no longer sees
    # all values as percent, so it falls through to the "mixing" error.
    with pytest.raises(ActionValidationError, match=r"all integers.*percent"):
        parse_action(
            {"geometry": {"x": "0%", "y": "0%", "w": "0%", "h": "zz"}},
            "x",
        )


def test_parse_action_snap_non_string_rejected() -> None:
    with pytest.raises(ActionValidationError, match="must be a string"):
        parse_action({"snap": 42}, "x")


# ── parse_monitor (public) ─────────────────────────────────────────────────
def test_parse_monitor_empty_string_rejected() -> None:
    with pytest.raises(ActionValidationError, match="must not be empty"):
        parse_monitor("", "x")


def test_parse_monitor_list_rejected() -> None:
    with pytest.raises(ActionValidationError, match="string or integer"):
        parse_monitor([1, 2], "x")


# ── desktop parser (inside parse_action) ───────────────────────────────────
def test_parse_desktop_bool_rejected() -> None:
    with pytest.raises(ActionValidationError, match="integer index"):
        parse_action({"desktop": True}, "x")


def test_parse_desktop_list_rejected() -> None:
    with pytest.raises(ActionValidationError, match="string or integer"):
        parse_action({"desktop": [1, 2]}, "x")


# ── parse_rules / context ──────────────────────────────────────────────────
def test_parse_rules_non_dict_entry_rejected() -> None:
    with pytest.raises(RuleValidationError, match="must be a table"):
        parse_rules([42])  # type: ignore[list-item]


def test_parse_rules_context_non_dict_rejected() -> None:
    with pytest.raises(RuleValidationError, match="must be a table"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": "nope",
                }
            ]
        )


def test_parse_rules_context_non_string_profile_rejected() -> None:
    with pytest.raises(RuleValidationError, match="profile must be a string"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": {"profile": 42},
                }
            ]
        )


def test_parse_rules_context_non_string_layout_rejected() -> None:
    with pytest.raises(RuleValidationError, match="layout must be a string"):
        parse_rules(
            [
                {
                    "match": {"app_id": "x"},
                    "apply": {"geometry": "maximize"},
                    "context": {"layout": 42},
                }
            ]
        )


# ── parse_layout_window ────────────────────────────────────────────────────
def test_parse_layout_window_non_dict_rejected() -> None:
    with pytest.raises(LayoutValidationError, match="must be a table"):
        parse_layout_window("x", "not a table")
