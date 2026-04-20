# 04 — Backend: X11 / EWMH

Reference implementation target for any non-Wayland desktop. Works on Xfce, MATE, Cinnamon, LXQt, i3, bspwm, fluxbox, Openbox, and Plasma-X11. Also usable under XWayland for X11-only apps on Wayland compositors — but that is *not* how we support Wayland compositors; see [05-backend-kwin.md](05-backend-kwin.md) and [06-backend-stubs.md](06-backend-stubs.md).

This doc was updated during Phase 2 research. Notable changes:

- Switched from `python-ewmh` to `python-xlib` + an in-tree EWMH helper (`python-ewmh` is unmaintained since 2017 and not packaged on Fedora/openSUSE).
- Added a "WM quirks" subsection (i3 tiled-window gravity, Openbox map race, Plasma-X11 GTK shadows).
- Added XWayland caveats (synthetic output names, fractional scale invisible).

## Protocol used

- **EWMH** (Extended Window Manager Hints) — the de-facto standard set of X11 properties for window-manager interaction.
- **ICCCM** — for legacy bits EWMH doesn't cover (e.g. `WM_CLASS`, `WM_TRANSIENT_FOR`).
- **XRandR** — for output/monitor enumeration and change events.

Perch does not speak any WM-specific extension on X11. Anything WM-specific is a bug in our side of the API.

## Transport

- One X11 connection via **`python-xlib`** directly. A small in-tree EWMH helper (`perch/backends/x11/ewmh.py`) wraps atoms we actually use (`_NET_WM_STATE`, `_NET_MOVERESIZE_WINDOW`, `_NET_WM_DESKTOP`, `_NET_FRAME_EXTENTS`, `_NET_WM_WINDOW_TYPE`, `_NET_CURRENT_DESKTOP`, `_NET_NUMBER_OF_DESKTOPS`, `_NET_WM_PID`, `_NET_WM_NAME`). Scope is deliberately narrow — we don't reimplement a full EWMH library.
- Event loop integration via `QSocketNotifier(conn.fileno(), Read)` → dispatch pending events in the Qt main thread.
- No threads. X11 is single-connection, single-reader; we keep it that way. `python-xlib`'s `Display` is not thread-safe; if background work is ever needed, open a **second** `Display()` in the worker — never share.

### Drain loop and flushing

Confirmed in Phase 2.5 research:

- `QSocketNotifier` is level-triggered on POSIX — correct for the X socket.
- **One readable wakeup can cover multiple queued events.** Always drain with `while d.pending_events(): handle(d.next_event())`.
- **Call `d.flush()` after sending requests** from non-event contexts (outbound geometry writes, property reads). `python-xlib` buffers writes; without the flush, requests sit in userspace.
- **Never call `d.sync()` on the main thread.** It's a round-trip that blocks until the server replies. `d.flush()` is non-blocking and is what we want.
- **Never call `d.next_event()` without `pending_events()` first.** It blocks the Qt thread.

```python
def _drain(self) -> None:
    while self.d.pending_events():
        self._handle(self.d.next_event())
# Flush at the end of any sync request batch outside the drain loop:
self.d.flush()
```

## Window lifecycle

| Native | Perch event |
|---|---|
| `CreateNotify` → `MapNotify` on root with `override_redirect = False` | `window_opened` |
| `UnmapNotify` / `DestroyNotify` | `window_closed` |
| `PropertyNotify` on `WM_NAME`, `_NET_WM_NAME`, `_NET_WM_STATE`, `WM_STATE` | `window_changed` |
| `ConfigureNotify` | `geometry_changed` |

`override_redirect=True` windows (tooltips, menus, splash screens that bypass the WM) are ignored unconditionally.

## Reading geometry

X11 `ConfigureNotify` reports coordinates *relative to the parent*, which for reparenting WMs is the WM's decoration frame, not the root. To get the real screen coords, Perch uses the **gravity-adjusted** method:

1. Translate `(0,0)` of the window to root coords via `XTranslateCoordinates`.
2. Subtract `_NET_FRAME_EXTENTS` if present so the stored geometry refers to the *client area*, consistent with what `_NET_MOVERESIZE_WINDOW` expects.

## Setting geometry

EWMH offers `_NET_MOVERESIZE_WINDOW` with explicit gravity bits. Perch uses `StaticGravity` (top-left of client area) so:

- Restore to `(x=100, y=40)` puts the client-area top-left at `(100, 40)` regardless of frame thickness.
- Values are independent of the WM's decoration theme.

For `can_set_state`:

- **Maximize** — set `_NET_WM_STATE_MAXIMIZED_HORZ` + `_NET_WM_STATE_MAXIMIZED_VERT` via `_NET_WM_STATE` client message.
- **Fullscreen** — `_NET_WM_STATE_FULLSCREEN`.
- **Minimize** — `_NET_WM_STATE_HIDDEN` + `XIconifyWindow`.

## Monitors (XRandR)

`list_outputs()` queries XRandR:

- `xrandr.get_screen_resources_current()` for the list.
- Per output: `get_output_info()`, then `get_crtc_info()` for the position/size of the active CRTC.
- Scale is always `1.0` on native X11. (Fractional scaling in X exists only via toolkit magic; there is no per-output scale in the protocol.)
- `is_primary` via `xrandr.get_output_primary()`.

`output_added` / `output_removed` / `output_changed` are emitted on `RRScreenChangeNotify` + `RRCrtcChangeNotify`. Perch debounces these (200 ms) so unplugging a cable that triggers three sub-events is reported once.

## Virtual desktops

- `current_desktop()` → `_NET_CURRENT_DESKTOP`.
- `desktop_count()` → `_NET_NUMBER_OF_DESKTOPS`.
- Setting a window's desktop: `_NET_WM_DESKTOP` client message. `0xFFFFFFFF` is sticky/all.

Some WMs (i3, bspwm) model workspaces non-linearly. Perch treats the EWMH desktop list as a flat 0..N-1 array; users on workspace WMs may find the mapping awkward, documented in the manual.

## Hotkeys

X11 global hotkeys use `XGrabKey` on the root window, with a **lock-mask fan-out** so the grab covers every combination of `NumLock` / `CapsLock` / `ScrollLock` the user might have set when pressing the key:

```python
lock_masks = [0, X.LockMask, mod2_mask, X.LockMask | mod2_mask]  # Mod2 ≈ NumLock on most layouts
for extra in lock_masks:
    root.grab_key(keycode, mods | extra, 1, X.GrabModeAsync, X.GrabModeAsync)
```

`mod2_mask` must be resolved dynamically at startup via `d.get_modifier_mapping()` — on some layouts NumLock lives under a different Mod bit.

Perch:

- Registers via `grab_key` with `GrabModeAsync`, `owner_events=True`.
- Handles `KeyPress` on root → fires `hotkey_fired(callback_id)`.
- Advertises `can_register_hotkeys = True`.

Caveats:

- If another application has already grabbed the same key (common under Plasma-X11, which has KGlobalAccel grabbing many combos), `grab_key` raises `BadAccess`. Perch catches it and surfaces "hotkey unavailable: <accel>" to the user rather than silently failing.
- Key repeat delivers a rapid `KeyRelease`+`KeyPress` pair with matching timestamps; filter these when we only want one fire per press.

## Capabilities declared

```python
Capabilities(
    can_set_position      = True,
    can_set_size          = True,
    can_set_monitor       = True,    # via coordinate math; no dedicated API
    can_set_desktop       = True,
    can_set_state         = True,
    can_enumerate_windows = True,
    can_observe_geometry  = True,
    can_observe_outputs   = True,
    can_register_hotkeys  = True,
    can_preplace_windows  = False,   # X11 has no "position before first map" primitive
    notes = "X11/EWMH via python-xlib + in-tree EWMH helper. "
            "override_redirect windows are ignored. "
            "i3 tiled windows ignore geometry writes; Perch skips them."
)
```

## Identity sourcing

| `WindowInfo` field | X11 source |
|---|---|
| `app_id` | `WM_CLASS` *instance* (first of the two strings). Lowercased for stability. |
| `wm_class` | `WM_CLASS` *class* (second string), verbatim. |
| `title` | `_NET_WM_NAME` if UTF-8, else `WM_NAME`. |
| `pid` | `_NET_WM_PID`, else `None`. |
| `type` | `_NET_WM_WINDOW_TYPE` → map to `WindowType`. |
| `state` | `_NET_WM_STATE` flags → pick one per priority: fullscreen > maximised > minimised > normal. |
| `role` | `WM_WINDOW_ROLE`. |
| `parent` | `WM_TRANSIENT_FOR`. |

## Window subscription pattern

Healthy EWMH clients (wmctrl, tint2, polybar) all do this:

1. On the root window, select `SubstructureNotifyMask | PropertyChangeMask` — catches `_NET_CLIENT_LIST`, `_NET_CURRENT_DESKTOP`, `_NET_ACTIVE_WINDOW` changes.
2. For every top-level listed in `_NET_CLIENT_LIST`, select `PropertyChangeMask` so we get `PropertyNotify` for `_NET_WM_STATE`, `_NET_FRAME_EXTENTS`, `WM_CLASS`, `WM_NAME`.
3. On `PropertyNotify(_NET_CLIENT_LIST)` on root, diff old/new list and `change_attributes` on the newcomers. `DestroyNotify` cleans up naturally.

**Always guard per-window calls for `BadWindow` / `BadMatch`** — windows vanish mid-request and the `change_attributes` call races their destruction:

```python
for w in client_list():
    try:
        w.change_attributes(event_mask=X.PropertyChangeMask)
    except (Xlib.error.BadWindow, Xlib.error.BadMatch):
        pass  # window died between list read and attribute set
```

## Edge cases and known workarounds

- **Chromium / Electron apps** set `WM_CLASS` late. Perch re-reads `WM_CLASS` on each `PropertyNotify` matching that atom, retrying up to **5 times over ~2 s**. After that it gives up and uses whatever the current value is (likely empty); identity then falls back to title-based matching. Still current in 2026 (Electron inherits Chromium's X11 code path).
- **Steam client** reparents itself; early `ConfigureNotify` events arrive with nonsense parents. Perch filters events until `_NET_WM_STATE` is first set (marks WM has claimed the window). Comment in-code documents this.
- **GTK CSD windows** draw their own decorations but report `_NET_FRAME_EXTENTS` anyway (often zeros). Subtracting zero is a no-op; this is fine.
- **Fullscreen flicker on restore** — some WMs briefly place the window at its constructor-coords before `_NET_MOVERESIZE_WINDOW` takes effect. There is no X11 way to "pre-position before map," so `can_preplace_windows = False` on this backend.

## WM quirks

Phase 2 research confirmed these are worth documenting:

- **i3 — tiled windows ignore gravity bits.** `_NET_MOVERESIZE_WINDOW` with `StaticGravity` is honoured only for floating windows; tiled windows snap to their container regardless. Perch's response: when running under i3, skip geometry restore for windows in tiled state. Detected via `_NET_WM_STATE` and i3-ipc-free heuristics (i3 does not expose its state via EWMH).
- **Openbox map race.** If `_NET_FRAME_EXTENTS` has not been set at the point `MapNotify` fires, subtraction can miscalculate the client-area origin. Perch retries the geometry read once after a 50 ms delay when `_NET_FRAME_EXTENTS` is absent at first sight, and only then settles on the initial geometry.
- **Plasma-X11 — GTK shadow margins on some apps.** KWin applies client-side-shadow margins when reporting frame extents for some GTK apps, which makes the client-area rect larger than the visible window. Not a Perch bug; results in geometry values that are "correct" but look slightly off to the eye. Documented as-is; no workaround attempted.
- **XWayland under Plasma/GNOME Wayland.** XRandR reports outputs as `XWAYLAND0`, `XWAYLAND1`, … with positions that *usually* match the Wayland compositor's logical layout. Fractional scale is invisible from X11 — coordinates are in logical pixels, not physical. Perch's output-name matching correlates by geometry/position when the Wayland backend is also known, so a user who named a profile under Plasma Wayland ("Docked") can reuse it from an X11 Perch session with matching topology. This correlation is best-effort and documented in `09-layouts-profiles.md`.

## Testing strategy

- **Unit tests** against `MockBackend` cover the core's assumptions.
- **Integration tests** spin up an `Xvfb` server and a lightweight WM (`openbox` is 800 KB and behaves as an EWMH-compliant reference). A pytest fixture starts Xvfb on `:99`, starts openbox, and Perch's X11 backend connects to `:99` with a throwaway config. CI runs these under `pytest -m x11`.
- Known window managers tested: openbox (reference), i3 (workspace WM), Plasma-X11 (heavyweight). The test matrix lives in CI config, not in this doc.
- **Openbox status**: upstream is dormant (last release 3.6.1, 2015) but openbox remains packaged on every relevant distro and is still the de-facto reference EWMH WM for headless Xvfb testing. Keep using it; flag for revisit in the roadmap if that ever changes.

## Out of scope

- EWMH properties not related to geometry: `_NET_WM_USER_TIME`, `_NET_WM_STRUT_PARTIAL`, `_NET_WM_STRUT` — Perch ignores them.
- GTK/KDE-toolkit-level hints (`_GTK_FRAME_EXTENTS`, `_KDE_NET_WM_FRAME_STRUT`) — not needed; EWMH equivalents are enough.
- XInput2 devices — mouse/keyboard discovery, multi-seat. Perch does not care.
