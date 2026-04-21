# Hyprland backend — status

**Stub.** Implements `WindowBackend` honestly but with narrower capabilities
than the X11 / KWin backends. Authoritative design:
`docs/06-backend-stubs.md` §Hyprland.

## Capabilities (as of v1)

| Capability | Value | Notes |
|---|---|---|
| `can_set_position` | True | `hyprctl dispatch moveactive exact X Y,address:0x…`. Applies cleanly only to floating windows. |
| `can_set_size` | True | `resizeactive exact W H,address:0x…`. |
| `can_set_monitor` | True | `movewindow mon:<NAME>,address:0x…`. |
| `can_set_desktop` | True | `movetoworkspacesilent N,address:0x…` (1-based). |
| `can_set_state` | True | `MINIMIZED` → move to `special` workspace; `FULLSCREEN` → `fullscreen 1`; `NORMAL` → `fullscreen 0`. `MAXIMIZED` raises `BackendUnsupported` (rules engine substitutes work-area geometry). |
| `can_enumerate_windows` | True | `hyprctl -j clients`. |
| `can_observe_geometry` | True | `.socket2.sock` event stream; events trigger re-queries rather than parsing each event's field layout (shifts across minor releases). |
| `can_observe_outputs` | True | `monitoradded` / `monitorremoved` events trigger re-queries of `hyprctl -j monitors`. |
| `can_register_hotkeys` | **False** | Hyprland owns hotkeys via its config. |
| `can_preplace_windows` | False | No pre-paint placement hook in the protocol. |

## Minimum version

**Hyprland ≥ 0.40.** `start()` runs `hyprctl version -j` and refuses to
proceed on anything below that. Rationale: the `.socket2.sock` event
format has shifted across minor releases and at least one field-order
change landed around 0.40. Dispatching to unknown-format events is worse
than a clean "unsupported" message.

## What works

- Enumeration (`list_windows`, `list_outputs`, `current_desktop`,
  `desktop_count`).
- Commands (`set_geometry`, `set_state`, `close_window`).
- Lifecycle: `start()` opens the event stream and primes window/output
  caches; `stop()` cancels the reader task.
- Event handling: defensive — unknown event names are logged at DEBUG
  and skipped. See `_dispatch_event_line` in `backend.py`.

## What does not work (by design)

- **Pre-paint placement.** Windows appear at Hyprland's default location
  and then move once Perch's rule fires.
- **Hotkeys.** Users wanting Perch hotkeys on Hyprland bind keys to
  `exec perch ...` in their Hyprland config. `register_hotkey` raises
  `BackendUnsupported`.
- **Tiled-window geometry.** Geometry dispatches against tiled windows
  are no-ops — the compositor snaps them back to their container.
  Perch on Hyprland is most useful for floating windows and
  workspace-assignment rules.
- **`NORMAL` after `MINIMIZED`.** Hyprland's special workspace has no
  "un-minimise to previous workspace" dispatch. The core typically pairs
  `WindowState.NORMAL` with a `set_geometry` that names the target
  workspace; on Hyprland this is the recommended path.

## Known skews

- **Event schema.** The `.socket2.sock` event format has shifted across
  Hyprland minor releases. We handle this by treating events as
  *notifications* only and re-querying `hyprctl -j` for the canonical
  state. If a new event type appears, `log.debug` records it without
  crashing.
- **Address vs window-id.** Hyprland's stable window handle is the
  `address` hex string (e.g. `"0x55a..."`). `WindowId` is that string;
  don't confuse it with the X11 `0x…` WID on the KWin-X11 side.
- **Workspace numbering.** Hyprland workspace IDs are 1-based and sparse
  (user can jump from 1 to 5 to 9). `desktop_count()` reports the count
  of *active* workspaces, which may be less than the highest ID.
- **Socket path.** Hyprland 0.39.x moved the IPC sockets from
  `/tmp/hypr/$HIS/` to `$XDG_RUNTIME_DIR/hypr/$HIS/`. `is_available()`
  checks both.

## Tested Hyprland versions

None yet — this is the landing commit. Community contributors running
Hyprland should exercise the backend against their installed Hyprland
version and report findings (IPC skews, event-format shifts) in an
issue.

## Contributing

See `CONTRIBUTING.md` §Contributing a backend. The compliance suite
(`tests/backend/test_compliance.py`) is the acceptance bar.
