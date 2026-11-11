"""Exclusions — windows Perch must never manage.

Two layers, per ``docs/07-rules-engine.md`` §Evaluation order:

1. **Built-in** (:data:`BUILTIN_EXCLUDED_TYPES`): system surfaces like
   ``DESKTOP`` and ``DOCK``, plus menus and splash screens. Not
   configurable — managing the panel or a popup menu would never be
   correct. The backends generally do not emit ``window_opened`` for X11
   override-redirect windows or Wayland layer-shell surfaces in the first
   place; this list is a belt-and-braces filter for compositors that do.
2. **User** (``[exclusions].patterns`` in ``config.toml``): additional
   match patterns the user has added.
"""

from __future__ import annotations

from typing import Any

from perch.backend.types import WindowInfo, WindowType

from .matching import MatchPattern, MatchValidationError, match_window, parse_match

# Surfaces that should never be placed, resized, or remembered. MENU covers
# popup menus: the KWin backend reports them (a tray icon's menu is one), and
# moving one puts it far from the click. A splash screen closes on its own.
BUILTIN_EXCLUDED_TYPES: frozenset[WindowType] = frozenset(
    {WindowType.DESKTOP, WindowType.DOCK, WindowType.MENU, WindowType.SPLASH}
)


class ExclusionValidationError(ValueError):
    """Raised when ``[exclusions].patterns`` is malformed."""


def is_builtin_excluded(window: WindowInfo) -> bool:
    """True if ``window`` is covered by the non-configurable built-in filter."""
    return window.type in BUILTIN_EXCLUDED_TYPES


def is_main_window(window: WindowInfo) -> bool:
    """True if ``window`` is an ordinary top-level window, not a dialog.

    Last-seen geometry is keyed by application, so only this kind may write
    or receive it: a dialog given the main window's geometry, or the reverse,
    is wrong whichever way round it happens (``docs/07-rules-engine.md``
    §Evaluation order, step 5).
    """
    return window.type is WindowType.NORMAL and not window.parent


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
