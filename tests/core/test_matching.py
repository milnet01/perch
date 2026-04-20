"""Tests for :mod:`perch.core.matching` — parse + match."""

from __future__ import annotations

import pytest

from perch.backend.types import Geometry, WindowInfo, WindowState, WindowType
from perch.core.matching import (
    MatchValidationError,
    match_window,
    parse_match,
)


def _w(
    *,
    app_id: str = "firefox",
    wm_class: str = "firefox",
    title: str = "Mozilla Firefox",
    pid: int = 1000,
    type_: WindowType = WindowType.NORMAL,
) -> WindowInfo:
    return WindowInfo(
        id="w",
        app_id=app_id,
        wm_class=wm_class,
        title=title,
        pid=pid,
        type=type_,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 800, 600),
        monitor="DP-1",
        desktop=0,
    )


# ── parse_match: happy paths ───────────────────────────────────────────────
def test_parse_empty_is_empty_pattern() -> None:
    p = parse_match({}, "x")
    assert p.is_empty()
    assert not p.catch_all


def test_parse_catch_all_is_catch_all() -> None:
    p = parse_match({"catch_all": True}, "x")
    assert p.catch_all is True


def test_parse_all_fields_present() -> None:
    p = parse_match(
        {
            "app_id": "firefox",
            "wm_class": "Firefox*",
            "title": r"^Private",
            "pid": 1234,
            "type": "normal,dialog",
        },
        "x",
    )
    assert p.app_id == "firefox"
    assert p.wm_class == "Firefox*"
    assert p.title is not None and p.title.pattern == r"^Private"
    assert p.pid == 1234
    assert p.types == (WindowType.NORMAL, WindowType.DIALOG)


# ── parse_match: rejections ────────────────────────────────────────────────
def test_parse_non_dict_rejected() -> None:
    with pytest.raises(MatchValidationError, match="must be a table"):
        parse_match("nope", "x")


def test_parse_unknown_key_rejected() -> None:
    with pytest.raises(MatchValidationError, match="unknown keys"):
        parse_match({"classname": "firefox"}, "x")


def test_parse_non_string_app_id_rejected() -> None:
    with pytest.raises(MatchValidationError, match="must be a string"):
        parse_match({"app_id": 42}, "x")


def test_parse_bool_pid_rejected() -> None:
    """``pid = true`` would silently pass ``isinstance(int)`` — reject it."""
    with pytest.raises(MatchValidationError, match="must be an integer"):
        parse_match({"pid": True}, "x")


def test_parse_invalid_regex_rejected() -> None:
    with pytest.raises(MatchValidationError, match="not a valid regex"):
        parse_match({"title": r"[unclosed"}, "x")


def test_parse_unknown_type_rejected() -> None:
    with pytest.raises(MatchValidationError, match="not a known window type"):
        parse_match({"type": "window"}, "x")


def test_parse_empty_type_string_rejected() -> None:
    with pytest.raises(MatchValidationError, match="must not be empty"):
        parse_match({"type": ""}, "x")


def test_parse_non_bool_catch_all_rejected() -> None:
    with pytest.raises(MatchValidationError, match="catch_all must be a boolean"):
        parse_match({"catch_all": "yes"}, "x")


# ── match_window: behaviour ─────────────────────────────────────────────────
def test_catch_all_matches_everything() -> None:
    p = parse_match({"catch_all": True}, "x")
    assert match_window(p, _w(app_id="anything"))


def test_empty_pattern_matches_nothing_meaningfully() -> None:
    """An empty pattern with no catch_all trivially matches anything — but
    the rules/exclusions parsers refuse to construct one, so this path is
    only reachable by direct construction."""
    from perch.core.matching import MatchPattern

    assert match_window(MatchPattern(), _w())


def test_app_id_glob_match() -> None:
    p = parse_match({"app_id": "fire*"}, "x")
    assert match_window(p, _w(app_id="firefox"))
    assert not match_window(p, _w(app_id="chromium"))


def test_wm_class_glob_match() -> None:
    p = parse_match({"wm_class": "Plasma*"}, "x")
    assert match_window(p, _w(wm_class="Plasmashell"))
    assert not match_window(p, _w(wm_class="Chromium"))


def test_title_regex_uses_search_not_match() -> None:
    p = parse_match({"title": r"Private"}, "x")
    assert match_window(p, _w(title="Mozilla Firefox (Private Browsing)"))
    assert not match_window(p, _w(title="Mozilla Firefox"))


def test_title_regex_anchored_by_user() -> None:
    """``^`` and ``$`` anchors are the user's responsibility per docs/07."""
    p = parse_match({"title": r"^Private$"}, "x")
    assert match_window(p, _w(title="Private"))
    assert not match_window(p, _w(title="Mozilla (Private)"))


def test_pid_exact_match() -> None:
    p = parse_match({"pid": 1234}, "x")
    assert match_window(p, _w(pid=1234))
    assert not match_window(p, _w(pid=9999))


def test_types_comma_list_any_of() -> None:
    p = parse_match({"type": "dialog,utility"}, "x")
    assert match_window(p, _w(type_=WindowType.DIALOG))
    assert match_window(p, _w(type_=WindowType.UTILITY))
    assert not match_window(p, _w(type_=WindowType.NORMAL))


def test_and_semantics_across_fields() -> None:
    p = parse_match(
        {"app_id": "firefox", "title": r"Private"}, "x"
    )
    assert match_window(p, _w(app_id="firefox", title="Private Browsing"))
    assert not match_window(p, _w(app_id="firefox", title="Normal"))
    assert not match_window(p, _w(app_id="chromium", title="Private"))
