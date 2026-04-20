# 03 — Backend interface

The contract every compositor backend implements. This is the **most important doc** in the project — if the interface is wrong, every backend and every feature pays for it.

## Design rules

1. **Async by default.** All I/O methods return awaitables. Most compositor transports (D-Bus, X11 socket, IPC pipes) are async in practice; synchronous shims hide the real cost.
2. **Events flow one way.** Backends emit events to the core via a Qt signal interface. The core never polls.
3. **Capabilities are explicit.** A backend declares what it can and cannot do; the core never assumes.
4. **No silent workarounds.** If a backend is asked to do something it cannot, it raises `BackendUnsupported` — the core decides how to degrade (disable the menu entry, show a tooltip, …). Per the project rule, workarounds are documented in-code when they are genuinely unavoidable.
5. **Stable data shapes.** Backends return frozen dataclasses; no dict-of-anything bags.

## Data types

```python
# perch/backend/types.py  (indicative — final location under M1)

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, AsyncIterator

WindowId = str          # backend-chosen opaque handle; stable for the life of the window
OutputName = str        # e.g. "DP-1", "eDP-1"
DesktopIndex = int      # 0-based; -1 means "all desktops" / "sticky"


class WindowType(StrEnum):
    NORMAL   = "normal"
    DIALOG   = "dialog"
    SPLASH   = "splash"
    UTILITY  = "utility"
    TOOLBAR  = "toolbar"
    MENU     = "menu"
    DOCK     = "dock"
    DESKTOP  = "desktop"
    UNKNOWN  = "unknown"


class WindowState(StrEnum):
    NORMAL     = "normal"
    MAXIMIZED  = "maximized"
    MINIMIZED  = "minimized"
    FULLSCREEN = "fullscreen"


@dataclass(frozen=True, slots=True)
class Geometry:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True, slots=True)
class WindowInfo:
    id:          WindowId
    app_id:      str                       # Wayland app_id, or X11 WM_CLASS instance
    wm_class:    str                       # X11 class (or "" on Wayland if unknown)
    title:       str
    pid:         int | None
    type:        WindowType
    state:       WindowState
    geometry:    Geometry                  # in root / global coords
    monitor:     OutputName                # the output the window is mostly on
    desktop:     DesktopIndex              # -1 if sticky / all
    parent:      WindowId | None = None    # transient-for relationship
    role:        str = ""                  # X11 WM_WINDOW_ROLE; "" on Wayland


@dataclass(frozen=True, slots=True)
class OutputInfo:
    name:         OutputName               # "DP-1", "eDP-1"
    geometry:     Geometry                 # position + logical size in the global coord space
    work_area:    Geometry                 # geometry minus panels/struts
    scale:        float                    # e.g. 1.0, 1.5, 2.0
    refresh_mhz:  int                      # refresh rate × 1000
    is_primary:   bool
    is_connected: bool


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What this backend can and cannot do. Filled in by each backend at init."""
    can_set_position:       bool
    can_set_size:           bool
    can_set_monitor:        bool           # move a window to a specific output
    can_set_desktop:        bool
    can_set_state:          bool           # minimize/maximize/fullscreen
    can_enumerate_windows:  bool
    can_observe_geometry:   bool           # emit geometry_changed events
    can_observe_outputs:    bool           # emit output_changed events
    can_register_hotkeys:   bool
    can_preplace_windows:   bool           # apply geometry before the first paint
    notes:                  str = ""       # human-readable caveats
```

The `can_preplace_windows` bit was added during Phase 2 research. "Pre-placement" means the backend can apply remembered geometry *before* the window's first paint, so the user doesn't see it flash at its default location and then move. Only the KWin backend currently claims this, and even there it is best-effort (see [05-backend-kwin.md](05-backend-kwin.md) — KWin scripting provides no hard guarantee but in practice flicker is rarely visible). X11, Mutter, Sway, and Hyprland all return `False` — their respective protocols do not expose the hook. The core uses this bit to tell the user, up front, when Perch is running in a session where "restore on open" will be visually snappy vs. "restore on open, with a visible snap."

`WindowInfo` is always a snapshot. The core never holds a reference to a live backend object — if it wants fresh data it asks the backend again.

## Events

Backends emit events as Qt signals. The core connects handlers at startup and relies on signal/slot queuing to serialise events on the main thread.

```python
# perch/backend/base.py

from PySide6.QtCore import QObject, Signal

class WindowBackend(QObject):

    # Window lifecycle
    window_opened      = Signal(WindowInfo)
    window_closed      = Signal(WindowId)
    window_changed     = Signal(WindowInfo)   # title / type / state change; not geometry
    geometry_changed   = Signal(WindowId, Geometry, OutputName, DesktopIndex)

    # Output lifecycle
    output_added       = Signal(OutputInfo)
    output_removed     = Signal(OutputName)
    output_changed     = Signal(OutputInfo)   # resolution / position / scale / primary flag

    # Backend health
    backend_connected    = Signal()
    backend_disconnected = Signal(str)        # reason
    backend_error        = Signal(str)        # non-fatal warning
```

### Event ordering guarantees

- `window_opened` is always emitted *before* the first `geometry_changed` for that window.
- `window_closed` is terminal; no further events for that `WindowId` after it.
- Output events are emitted *before* any window events referencing a new output.
- If the compositor's native protocol cannot guarantee this ordering, the backend must buffer and reorder.

### What is *not* an event

- "Window focused" — not needed for geometry management in v1.
- "Mouse click on window" — Perch does not care.
- "Urgent hint set" — not needed.

Adding events later is allowed; removing them requires a deprecation cycle documented in [11-roadmap.md](11-roadmap.md).

## Methods

```python
class WindowBackend(QObject):

    # ── Lifecycle ──────────────────────────────────────────────────────────
    # Named ``start`` / ``stop`` rather than ``connect`` / ``disconnect`` to
    # avoid the collision with ``QObject.connect`` / ``QObject.disconnect``
    # (the Qt signal/slot staticmethods). ``backend_connected`` /
    # ``backend_disconnected`` keep their names as signals — it's the method
    # names that would have confused mypy and readers.
    async def start(self) -> None: ...
        # Open the transport, subscribe to events, emit backend_connected.
        # Raises BackendUnavailable if the transport is missing.

    async def stop(self) -> None: ...

    @property
    def capabilities(self) -> Capabilities: ...

    # ── Queries ────────────────────────────────────────────────────────────
    async def list_windows(self) -> list[WindowInfo]: ...
    async def get_window(self, wid: WindowId) -> WindowInfo: ...
        # Raises UnknownWindow.

    async def list_outputs(self) -> list[OutputInfo]: ...

    async def current_desktop(self) -> DesktopIndex: ...
    async def desktop_count(self) -> int: ...

    # ── Commands ───────────────────────────────────────────────────────────
    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None: ...
        # Atomic-ish: the backend should apply all fields in one compositor call
        # if possible.  Raises BackendUnsupported if any field cannot be set.

    async def set_state(self, wid: WindowId, state: WindowState) -> None: ...

    async def close_window(self, wid: WindowId) -> None: ...
        # Requests the window close (WM_DELETE_WINDOW / xdg_toplevel close).
        # Not used in v1 features, but cheap to implement and useful for tooling.

    # ── Hotkeys (optional) ─────────────────────────────────────────────────
    async def register_hotkey(self, accel: str, callback_id: str) -> None: ...
    async def unregister_hotkey(self, callback_id: str) -> None: ...
        # If capabilities.can_register_hotkeys is False, the core uses
        # KGlobalAccel / a local grabber instead.

    hotkey_fired = Signal(str)   # emits callback_id
```

### Hotkey accelerators

The `accel` argument to `register_hotkey` is a **QKeySequence Portable Text string** — e.g. `"Meta+Left"`, `"Ctrl+Alt+T"`, `"Ctrl+Shift+F11"`. Portable Text is what `QKeySequence.toString(QKeySequence.PortableText)` emits and what `QKeySequence.fromString` accepts; it is also the form KGlobalAccel D-Bus and the X11 `XGrabKey` path consume directly.

The `org.freedesktop.portal.GlobalShortcuts` path wants the XDG Shortcuts spec form instead — uppercase modifier names (`LOGO` instead of `Meta`, `CTRL`, `ALT`, `SHIFT`) and xkbcommon keysyms. Backends that implement the portal path (KWin when running under Flatpak, Hyprland) translate at the boundary via a `portable_to_xdg()` helper; the accelerator stored in `config.toml` stays Portable Text so swapping the transport does not rewrite the config. The XDG form is never exposed to the core or the UI.

## Errors

```python
class BackendError(Exception): ...
class BackendUnavailable(BackendError): ...   # transport missing entirely
class BackendDisconnected(BackendError): ...  # connection lost after start()
class BackendUnsupported(BackendError): ...   # capability not present
class UnknownWindow(BackendError): ...
class UnknownOutput(BackendError): ...
```

All errors carry a short human-readable message in `args[0]`. Backends must not subclass further — the core's error handling works off the four types above.

## Capability negotiation

The core reads `capabilities` once at startup and again whenever `backend_connected` fires. Every feature in the UI is conditional on a capability:

| Feature | Requires |
|---|---|
| Snap presets | `can_set_position`, `can_set_size` |
| "Send window to monitor 2" | `can_set_monitor` |
| Virtual-desktop rules | `can_set_desktop` |
| Auto-restore on open | `can_observe_geometry` + `can_set_position` + `can_set_size` |
| Pre-paint placement ("snappy restore") | `can_preplace_windows` |
| Global hotkeys (backend-registered) | `can_register_hotkeys` (else fall back) |

Disabled features render greyed out with a tooltip quoting `capabilities.notes`.

## Identity helpers

Identity (see [02-state-format.md](02-state-format.md)) is computed by the *core*, not the backend. The backend only supplies raw attributes (`app_id`, `wm_class`, `title`, `role`, `pid`). This keeps identity rules central and consistent across backends.

## Coordinate system

- All geometries are in the compositor's **global logical coordinate space**, pre-scaling.
- `Geometry` numbers are integers. Backends that receive fractional values (Wayland scale) round half-to-even.
- Output positions are likewise logical, not physical pixels.
- On X11, "logical" == physical (no per-output scaling in the protocol).

## Backend selection

`perch.backend.select()`:

1. Reads `$XDG_SESSION_TYPE`.
2. If `wayland`:
   a. Probes `$KDE_FULL_SESSION` → KWin backend.
   b. Probes `$XDG_CURRENT_DESKTOP` for `GNOME` → Mutter backend.
   c. Probes `$SWAYSOCK` → Sway backend.
   d. Probes `$HYPRLAND_INSTANCE_SIGNATURE` → Hyprland backend.
3. If `x11` or unmatched Wayland: X11 backend (works on XWayland too for legacy apps, but geometry is per-Xwayland, not the Wayland compositor).
4. Otherwise: `BackendUnavailable`, fall back to UI-only mode.

The selection can be overridden via `PERCH_BACKEND=<name>` for testing.

## Mock backend (for tests)

`perch.backend.mock.MockBackend` implements the full interface in memory:

- Has pre-seeded windows and outputs.
- Emits events when the test driver pokes them.
- Records every command call for assertions.
- Declares full capabilities by default; tests can flip flags off to exercise degraded paths.

This is what lets the core and rules engine be tested without a live compositor — important in CI.

## What goes in a backend, what does not

**In the backend:**

- Compositor-specific protocol chatter (D-Bus method names, X11 atoms, wire formats).
- Any caching needed to serve `list_windows()` cheaply.
- Translating native events to the `WindowInfo`/`Geometry` types.

**Not in the backend:**

- Identity key construction (core).
- Rule evaluation (core).
- Deciding *whether* to apply a remembered geometry (core).
- User-facing notifications (UI).
- Reading `config.toml` (core).

If you find yourself reading the config file from a backend, something is wrong — back up and rethink.

## Phase 2 resolutions

The originally open questions were resolved during Phase 2 research:

- **`focus_window(wid)`**: deferred to v1.x. Not needed for M1…M9 features (layouts can set geometry without raising a specific window; the tray's "Windows" submenu raises via the compositor's default behaviour on click). A later need for an explicit raise primitive will add the method.
- **Pre-paint placement capability**: added as `can_preplace_windows` (see above). Only KWin sets it true; all others set it false and document the visible-snap consequence.
- **Output position normalisation**: geometries in `state.json` are stored as the compositor reports them (not normalised to primary-origin). The topology key in a profile captures the output positions verbatim, so cross-topology matching already handles the "plugged monitor in the other position" case without needing normalisation. Documented in [09-layouts-profiles.md](09-layouts-profiles.md).
