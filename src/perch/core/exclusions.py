"""Exclusions — windows Perch must never manage.

Two layers, per ``docs/07-rules-engine.md`` §Evaluation order:

1. **Built-in** (:data:`BUILTIN_EXCLUDED_TYPES`): system surfaces like
   ``DESKTOP`` and ``DOCK``. Not configurable — managing the panel or the
   wallpaper would never be correct. The backends generally do not emit
   ``window_opened`` for X11 override-redirect windows or Wayland
   layer-shell surfaces in the first place; this list is a belt-and-braces
   filter for compositors that do.
2. **User** (``[exclusions].patterns`` in ``config.toml``): additional
   match patterns the user has added.
"""

from __future__ import annotations

from typing import Any

from perch.backend.types import WindowInfo, WindowType

from .matching import MatchPattern, MatchValidationError, match_window, parse_match

# System surfaces that should never be placed, resized, or remembered.
# Deliberately narrow — MENU and TOOLTIP are also system-adjacent but don't
# reach the event loop on any current backend, so the guard would be dead code.
BUILTIN_EXCLUDED_TYPES: frozenset[WindowType] = frozenset(
    {WindowType.DESKTOP, WindowType.DOCK}
)


class ExclusionValidationError(ValueError):
    """Raised when ``[exclusions].patterns`` is malformed."""


def is_builtin_excluded(window: WindowInfo) -> bool:
    """True if ``window`` is covered by the non-configurable built-in filter."""
    return window.type in BUILTIN_EXCLUDED_TYPES


def is_user_excluded(
    window: WindowInfo, patterns: list[MatchPattern]
) -> bool:
    """True if any user exclusion matches the window."""
    return any(match_window(p, window) for p in patterns)


def parse_user_exclusions(raw: list[dict[str, Any]]) -> list[MatchPattern]:
    """Turn ``[exclusions].patterns = [ ... ]`` into :class:`MatchPattern` s."""
    out: list[MatchPattern] = []
    for i, entry in enumerate(raw):
        prefix = f"[exclusions].patterns[{i}]"
        try:
            pattern = parse_match(entry, prefix)
        except MatchValidationError as exc:
            raise ExclusionValidationError(str(exc)) from exc
        if pattern.is_empty() and not pattern.catch_all:
            raise ExclusionValidationError(
                f"{prefix}: exclusion pattern must specify at least one "
                "match field (an empty exclusion would ignore every window)"
            )
        out.append(pattern)
    return out
