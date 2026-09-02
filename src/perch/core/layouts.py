"""Named layouts — ``[layouts.<name>]`` + ``[[layouts.<name>.windows]]``.

Spec in ``docs/09-layouts-profiles.md`` §Layouts. A layout is an ordered
list of (match, apply) pairs; when activated, the engine walks the list
top-to-bottom per window and the **last** matching entry wins — the
opposite of ``[[rules]]``, where the first does.

Preferring the most-recently-focused window when several match one entry
is specified there and not implemented: no backend reports a focus order.
Tracked as PERC-0066 in ``ROADMAP.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .actions import ActionValidationError, ApplyAction, parse_action
from .matching import (
    MatchPattern,
    MatchValidationError,
    match_signature,
    parse_match,
)


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

    def with_overrides(
        self, overrides: tuple[LayoutEntry, ...]
    ) -> Layout:
        """Return a new :class:`Layout` with ``overrides`` substituted in.

        Per ``docs/09-layouts-profiles.md`` §Per-profile overrides for
        layouts: each override entry replaces a base entry whose match
        compares equal (via :func:`match_signature`). Overrides whose
        match doesn't correspond to a base entry are appended at the end,
        so a profile can extend as well as replace.
        """
        if not overrides:
            return self
        by_sig = {match_signature(e.match): e for e in overrides}
        replaced_sigs: set[tuple[object, ...]] = set()
        merged: list[LayoutEntry] = []
        for entry in self.windows:
            sig = match_signature(entry.match)
            override = by_sig.get(sig)
            if override is not None:
                merged.append(override)
                replaced_sigs.add(sig)
            else:
                merged.append(entry)
        for override in overrides:
            if match_signature(override.match) not in replaced_sigs:
                merged.append(override)
        return Layout(
            name=self.name, description=self.description, windows=tuple(merged)
        )


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


def parse_layout_window(prefix: str, raw: Any) -> LayoutEntry:
    """Parse one ``{match, geometry/snap/monitor/desktop/maximized}`` table.

    Exposed publicly so that profile-override ``windows`` entries can be
    parsed at config load time (see :class:`perch.core.profiles.ProfileOverride`).
    """
    return _parse_window(prefix, raw)


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
