"""Frozen dataclasses and enums exchanged across the backend boundary.

Shapes mirror ``docs/03-backend-interface.md`` §Data types. These types are the
stable contract every backend honours; the core and the rules engine build on
them and never touch backend-private state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

WindowId = str
OutputName = str
DesktopIndex = int  # -1 means "all desktops" / "sticky"


class WindowType(StrEnum):
    NORMAL = "normal"
    DIALOG = "dialog"
    SPLASH = "splash"
    UTILITY = "utility"
    TOOLBAR = "toolbar"
    MENU = "menu"
    DOCK = "dock"
    DESKTOP = "desktop"
    UNKNOWN = "unknown"


class WindowState(StrEnum):
    NORMAL = "normal"
    MAXIMIZED = "maximized"
    MINIMIZED = "minimized"
    FULLSCREEN = "fullscreen"


@dataclass(frozen=True, slots=True)
class Geometry:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True, slots=True)
class WindowInfo:
    id: WindowId
    app_id: str
    wm_class: str
    title: str
    pid: int | None
    type: WindowType
    state: WindowState
    geometry: Geometry
    monitor: OutputName
    desktop: DesktopIndex
    parent: WindowId | None = None
    role: str = ""


@dataclass(frozen=True, slots=True)
class OutputInfo:
    name: OutputName
    geometry: Geometry
    work_area: Geometry
    scale: float
    refresh_mhz: int
    is_primary: bool
    is_connected: bool


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What this backend can and cannot do. Filled in by each backend at init."""

    can_set_position: bool
    can_set_size: bool
    can_set_monitor: bool
    can_set_desktop: bool
    can_set_state: bool
    can_enumerate_windows: bool
    can_observe_geometry: bool
    can_observe_outputs: bool
    can_register_hotkeys: bool
    can_preplace_windows: bool
    notes: str = ""
