"""UI → core intents.

Per ``docs/01-architecture.md`` §UI layer the UI never calls backend methods
directly — it emits typed intents that the core translates into reducer /
backend work. Keeping intents as a small frozen ADT means the reducer can
match on them exhaustively (mypy --strict catches a forgotten branch) and
the tray / dialog tests can assert on the intent without touching a real
backend.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActivateLayout:
    """Switch the active layout. ``name=None`` deactivates the current one."""

    name: str | None


@dataclass(frozen=True, slots=True)
class SnapFocused:
    """Apply a snap preset (builtin or user-defined) to the focused window."""

    preset: str


@dataclass(frozen=True, slots=True)
class TogglePause:
    """Toggle the "Pause Perch" flag (middle-click / menu toggle).

    When paused, the reducer drops every placement decision — rules,
    layouts, and last-seen restore — so no window is moved automatically.
    Manual snap is unaffected (it bypasses the reducer). See
    ``docs/08-ui.md`` §Menu structure.
    """


@dataclass(frozen=True, slots=True)
class ReapplyRules:
    """Re-evaluate every known window under the current profile + layout."""


@dataclass(frozen=True, slots=True)
class OpenConfigDialog:
    """Open the config dialog. The section name preselects a sidebar row."""

    section: str | None = None


@dataclass(frozen=True, slots=True)
class OpenConfigFolder:
    """Reveal the XDG config directory in the user's file manager."""


@dataclass(frozen=True, slots=True)
class OpenUrl:
    """Open a URL in the user's browser.

    Under Flatpak this resolves to the ``org.freedesktop.portal.OpenURI``
    portal, which needs no extra manifest permission.
    """

    url: str


@dataclass(frozen=True, slots=True)
class ShowAbout:
    """Open the About dialog."""


@dataclass(frozen=True, slots=True)
class Quit:
    """Shut Perch down cleanly."""


Intent = (
    ActivateLayout
    | SnapFocused
    | TogglePause
    | ReapplyRules
    | OpenConfigDialog
    | OpenConfigFolder
    | OpenUrl
    | ShowAbout
    | Quit
)
