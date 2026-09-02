"""End-to-end tests for :mod:`perch.core.engine` — decision order."""

from __future__ import annotations

from typing import Any

from perch.backend.types import Geometry, WindowInfo, WindowState, WindowType
from perch.core.actions import PresetGeometry
from perch.core.engine import (
    ApplyActionDecision,
    Ignore,
    RestoreLastSeen,
    TriggerEvent,
    evaluate,
)
from perch.core.exclusions import parse_user_exclusions
from perch.core.layouts import parse_layouts
from perch.core.rules import parse_rules


def _w(
    *,
    app_id: str = "firefox",
    title: str = "Mozilla Firefox",
    type_: WindowType = WindowType.NORMAL,
) -> WindowInfo:
    return WindowInfo(
        id="w",
        app_id=app_id,
        wm_class=app_id,
        title=title,
        pid=1000,
        type=type_,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 800, 600),
        monitor="DP-1",
        desktop=0,
    )


_DEFAULT_KW: dict[str, Any] = {
    "rules": [],
    "user_exclusions": [],
    "active_layout": None,
    "active_profile_name": None,
    "active_layout_name": None,
    "current_desktop": 0,
    "has_last_seen": False,
    "restore_on_open": True,
}


# ── Built-in exclusion wins everything ────────────────────────────────────
def test_builtin_exclusion_wins_over_rule() -> None:
    rules = parse_rules(
        [{"match": {"app_id": "plasmashell"}, "apply": {"geometry": "maximize"}}]
    )
    d = evaluate(
        _w(app_id="plasmashell", type_=WindowType.DOCK),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "rules": rules},
    )
    assert isinstance(d, Ignore) and d.source == "builtin-exclusion"


# ── User exclusions beat rules ─────────────────────────────────────────────
def test_user_exclusion_wins_over_rule() -> None:
    rules = parse_rules(
        [{"match": {"app_id": "firefox"}, "apply": {"geometry": "maximize"}}]
    )
    exclusions = parse_user_exclusions([{"app_id": "firefox"}])
    d = evaluate(
        _w(app_id="firefox"),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "rules": rules, "user_exclusions": exclusions},
    )
    assert isinstance(d, Ignore) and d.source == "user-exclusion"


# ── Rules beat layouts (explicit user intent) ──────────────────────────────
def test_rule_wins_over_layout() -> None:
    rules = parse_rules(
        [
            {
                "name": "firefox pinned",
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "left-half"},
            }
        ]
    )
    layouts = parse_layouts(
        {
            "coding": {
                "windows": [
                    {
                        "match": {"app_id": "firefox"},
                        "geometry": "right-half",
                    }
                ],
            }
        }
    )
    d = evaluate(
        _w(app_id="firefox"),
        TriggerEvent.OPENED,
        **{
            **_DEFAULT_KW,
            "rules": rules,
            "active_layout": layouts["coding"],
            "active_layout_name": "coding",
        },
    )
    assert isinstance(d, ApplyActionDecision)
    assert d.source == "rule:firefox pinned"


def test_unnamed_rule_source_uses_index() -> None:
    rules = parse_rules(
        [{"match": {"app_id": "firefox"}, "apply": {"geometry": "maximize"}}]
    )
    d = evaluate(
        _w(app_id="firefox"),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "rules": rules},
    )
    assert isinstance(d, ApplyActionDecision)
    assert d.source == "rule:[0]"


# ── First match wins among rules ──────────────────────────────────────────
def test_first_matching_rule_wins_even_if_less_specific() -> None:
    rules = parse_rules(
        [
            {
                "name": "any firefox",
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "left-half"},
            },
            {
                "name": "private firefox",
                "match": {"app_id": "firefox", "title": "Private"},
                "apply": {"geometry": "right-half"},
            },
        ]
    )
    d = evaluate(
        _w(title="Private Browsing"),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "rules": rules},
    )
    assert isinstance(d, ApplyActionDecision)
    assert d.source == "rule:any firefox"


# ── Context-gated rules ────────────────────────────────────────────────────
def test_context_gated_rule_skipped_on_wrong_profile() -> None:
    rules = parse_rules(
        [
            {
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "maximize"},
                "context": {"profile": "Docked"},
            }
        ]
    )
    d = evaluate(
        _w(),
        TriggerEvent.OPENED,
        **{
            **_DEFAULT_KW,
            "rules": rules,
            "active_profile_name": "Laptop",
        },
    )
    # No rule matches; no layout; restore_on_open true but no last-seen.
    assert isinstance(d, Ignore) and d.source == "no-match"


def test_context_gated_rule_fires_on_right_profile() -> None:
    rules = parse_rules(
        [
            {
                "name": "firefox docked",
                "match": {"app_id": "firefox"},
                "apply": {"geometry": "maximize"},
                "context": {"profile": "Docked"},
            }
        ]
    )
    d = evaluate(
        _w(),
        TriggerEvent.OPENED,
        **{
            **_DEFAULT_KW,
            "rules": rules,
            "active_profile_name": "Docked",
        },
    )
    assert isinstance(d, ApplyActionDecision)


# ── Layout matches when no rule does ──────────────────────────────────────
def test_layout_applies_when_no_rule_matches() -> None:
    layouts = parse_layouts(
        {
            "coding": {
                "windows": [
                    {"match": {"app_id": "firefox"}, "geometry": "maximize"},
                ]
            }
        }
    )
    d = evaluate(
        _w(),
        TriggerEvent.OPENED,
        **{
            **_DEFAULT_KW,
            "active_layout": layouts["coding"],
            "active_layout_name": "coding",
        },
    )
    assert isinstance(d, ApplyActionDecision)
    assert d.source == "layout:coding"


# ── Last-seen restore ──────────────────────────────────────────────────────
def test_last_seen_fires_on_open_when_enabled() -> None:
    d = evaluate(
        _w(),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "has_last_seen": True, "restore_on_open": True},
    )
    assert isinstance(d, RestoreLastSeen)


def test_last_seen_suppressed_when_restore_on_open_false() -> None:
    d = evaluate(
        _w(),
        TriggerEvent.OPENED,
        **{
            **_DEFAULT_KW,
            "has_last_seen": True,
            "restore_on_open": False,
        },
    )
    assert isinstance(d, Ignore) and d.source == "no-match"


def test_last_seen_does_not_fire_on_changed() -> None:
    d = evaluate(
        _w(),
        TriggerEvent.CHANGED,
        **{**_DEFAULT_KW, "has_last_seen": True, "restore_on_open": True},
    )
    assert isinstance(d, Ignore) and d.source == "no-match"


def test_last_seen_fires_on_user_trigger() -> None:
    d = evaluate(
        _w(),
        TriggerEvent.USER_TRIGGER,
        **{**_DEFAULT_KW, "has_last_seen": True, "restore_on_open": True},
    )
    assert isinstance(d, RestoreLastSeen)


# ── No-match fallthrough ───────────────────────────────────────────────────
def test_no_match_emits_ignore_no_match() -> None:
    d = evaluate(_w(), TriggerEvent.OPENED, **_DEFAULT_KW)
    assert isinstance(d, Ignore) and d.source == "no-match"


# ── Layout entry order ────────────────────────────────────────────────────
def test_layout_last_matching_entry_wins() -> None:
    """docs/09 §Layouts: entries are walked top-to-bottom, last match wins.

    The opposite of ``[[rules]]``, where the first match wins. Each document
    states its own half, and the asymmetry is deliberate.
    """
    layouts = parse_layouts(
        {
            "coding": {
                "windows": [
                    {"match": {"app_id": "firefox"}, "geometry": "left-half"},
                    {"match": {"app_id": "firefox"}, "geometry": "right-half"},
                ]
            }
        }
    )
    d = evaluate(
        _w(app_id="firefox"),
        TriggerEvent.OPENED,
        **{**_DEFAULT_KW, "active_layout": layouts["coding"]},
    )
    assert isinstance(d, ApplyActionDecision)
    assert d.action.geometry == PresetGeometry(name="right-half")
