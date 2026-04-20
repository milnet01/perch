"""Tests for :mod:`perch.core.exclusions`."""

from __future__ import annotations

import pytest

from perch.backend.types import Geometry, WindowInfo, WindowState, WindowType
from perch.core.exclusions import (
    BUILTIN_EXCLUDED_TYPES,
    ExclusionValidationError,
    is_builtin_excluded,
    is_user_excluded,
    parse_user_exclusions,
)


def _w(type_: WindowType) -> WindowInfo:
    return WindowInfo(
        id="w",
        app_id="plasmashell",
        wm_class="plasmashell",
        title="",
        pid=10,
        type=type_,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 100, 100),
        monitor="DP-1",
        desktop=0,
    )


def test_builtin_covers_desktop_and_dock() -> None:
    assert frozenset(
        {WindowType.DESKTOP, WindowType.DOCK}
    ) == BUILTIN_EXCLUDED_TYPES


def test_is_builtin_excluded_positive() -> None:
    assert is_builtin_excluded(_w(WindowType.DESKTOP))
    assert is_builtin_excluded(_w(WindowType.DOCK))


def test_is_builtin_excluded_negative() -> None:
    assert not is_builtin_excluded(_w(WindowType.NORMAL))
    assert not is_builtin_excluded(_w(WindowType.DIALOG))


def test_parse_user_exclusions_happy_path() -> None:
    patterns = parse_user_exclusions(
        [
            {"app_id": "plasmashell"},
            {"wm_class": "Plasma*", "type": "splash"},
        ]
    )
    assert len(patterns) == 2
    assert patterns[0].app_id == "plasmashell"


def test_parse_user_exclusions_rejects_empty_pattern() -> None:
    """An empty pattern would silently exclude every window."""
    with pytest.raises(ExclusionValidationError, match="at least one match field"):
        parse_user_exclusions([{}])


def test_parse_user_exclusions_rejects_bad_field() -> None:
    with pytest.raises(ExclusionValidationError, match="unknown keys"):
        parse_user_exclusions([{"app_id": "x", "bogus": True}])


def test_is_user_excluded_matches_any() -> None:
    patterns = parse_user_exclusions(
        [{"app_id": "plasmashell"}, {"app_id": "firefox"}]
    )
    window = _w(WindowType.NORMAL)
    assert is_user_excluded(window, patterns)


def test_is_user_excluded_no_match() -> None:
    patterns = parse_user_exclusions([{"app_id": "konsole"}])
    window = _w(WindowType.NORMAL)
    assert not is_user_excluded(window, patterns)
