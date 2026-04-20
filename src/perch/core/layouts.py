"""Named layouts — ``[layouts.<name>]`` + ``[[layouts.<name>.windows]]``.

Spec in ``docs/09-layouts-profiles.md`` §Layouts. A layout is an ordered
list of (match, apply) pairs; when activated, the reducer (M2.d) walks the
list top-to-bottom and applies the action to the matching window — or the
most-recently-focused window, when multiple match a single entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .actions import ActionValidationError, ApplyAction, parse_action
from .matching import MatchPattern, MatchValidationError, parse_match


class LayoutValidationError(ValueError):
    """Raised when a ``[layouts.<name>]`` entry is malformed."""


@dataclass(frozen=True, slots=True)
class LayoutEntry:
    """One (match, apply) pair inside a layout."""

    match: MatchPattern
    apply: ApplyAction


@dataclass(frozen=True, slots=True)
class Layout:
    name: str
    description: str = ""
    windows: tuple[LayoutEntry, ...] = field(default=())


def parse_layouts(raw: dict[str, Any]) -> dict[str, Layout]:
    """Validate and convert ``[layouts.<name>]`` tables into :class:`Layout`."""
    out: dict[str, Layout] = {}
    for name, entry in raw.items():
        if not name:
            raise LayoutValidationError("[layouts.<name>] key must not be empty")
        prefix = f"[layouts.{name!r}]"
        if not isinstance(entry, dict):
            raise LayoutValidationError(f"{prefix} must be a table")

        known = {"description", "windows"}
        unknown = set(entry.keys()) - known
        if unknown:
            raise LayoutValidationError(
                f"{prefix}: unknown keys {sorted(unknown)!r}"
            )

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise LayoutValidationError(
                f"{prefix}.description must be a string "
                f"(got {type(description).__name__})"
            )

        windows_raw = entry.get("windows", [])
        if not isinstance(windows_raw, list):
            raise LayoutValidationError(
                f"{prefix}.windows must be an array of tables"
            )
        windows = tuple(
            _parse_window(f"{prefix}.windows[{i}]", w)
            for i, w in enumerate(windows_raw)
        )

        out[name] = Layout(name=name, description=description, windows=windows)
    return out


def _parse_window(prefix: str, raw: Any) -> LayoutEntry:
    if not isinstance(raw, dict):
        raise LayoutValidationError(f"{prefix} must be a table")

    # Layout windows can write geometry/snap/monitor/desktop/maximized
    # directly at the entry level (no separate ``apply`` wrapper in the
    # layout TOML — that's a doc-sample convention). The entry still has
    # to include a match block.
    known = {
        "match", "geometry", "snap", "monitor", "desktop", "maximized",
    }
    unknown = set(raw.keys()) - known
    if unknown:
        raise LayoutValidationError(
            f"{prefix}: unknown keys {sorted(unknown)!r}"
        )

    if "match" not in raw:
        raise LayoutValidationError(f"{prefix}: missing 'match'")
    try:
        pattern = parse_match(raw["match"], f"{prefix}.match")
    except MatchValidationError as exc:
        raise LayoutValidationError(str(exc)) from exc
    if pattern.is_empty() and not pattern.catch_all:
        raise LayoutValidationError(
            f"{prefix}.match: empty match blocks are rejected — set "
            "catch_all = true if you really want to match every unmatched window"
        )

    action_raw = {
        k: v
        for k, v in raw.items()
        if k in ("geometry", "snap", "monitor", "desktop", "maximized")
    }
    try:
        action = parse_action(action_raw, prefix)
    except ActionValidationError as exc:
        raise LayoutValidationError(str(exc)) from exc

    return LayoutEntry(match=pattern, apply=action)
