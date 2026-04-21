# Sway / wlroots backend — status

**Stub.** Implements `WindowBackend` honestly but with narrower capabilities
than the X11 / KWin backends. Authoritative design: `docs/06-backend-stubs.md`
§Sway.

## Capabilities (as of v1)

| Capability | Value | Notes |
|---|---|---|
| `can_set_position` | **False** | Sway is tiling-first; position writes are only meaningful on floating windows. |
| `can_set_size` | True | `resize set <W>px <H>px` via i3-IPC `[con_id=N]`. |
| `can_set_monitor` | True | `move container to output <NAME>`. |
| `can_set_desktop` | True | `move container to workspace number <N+1>`. |
| `can_set_state` | True | `MINIMIZED` → `move scratchpad`; `FULLSCREEN` → `fullscreen enable`; `NORMAL` → `fullscreen disable`. `MAXIMIZED` raises `BackendUnsupported` (rules engine substitutes work-area geometry). |
| `can_enumerate_windows` | True | `get_tree()` + `leaves()` filter. |
| `can_observe_geometry` | True | i3-IPC `window` event stream. |
| `can_observe_outputs` | True | i3-IPC `output` event stream. |
| `can_register_hotkeys` | **False** | Sway owns hotkeys via its config; no runtime grab API. |
| `can_preplace_windows` | False | No pre-paint placement hook in the protocol. |

## What works

- Enumeration (`list_windows`, `list_outputs`, `current_desktop`, `desktop_count`).
- Commands (`set_geometry`, `set_state`, `close_window`) against `[con_id=N]`.
- Lifecycle: `start()` opens the async i3-IPC connection; `stop()` tears it down.

## What does not work (by design)

- **Pre-paint placement.** Windows appear at Sway's default position, then
  move to the target geometry when Perch's rule fires. No protocol hook
  exposes a pre-paint callback.
- **Hotkeys.** Users wanting Perch hotkeys on Sway bind keys to
  `swaymsg exec perch ...` (or a future `perch-cli` invocation) in their
  Sway config. `register_hotkey` raises `BackendUnsupported`.
- **Position writes on tiled windows.** Sway's IPC accepts the `move
  position` command for any con, but the compositor ignores it for tiled
  windows. Perch is most useful on Sway for floating windows
  (pop-outs, scratchpads, video-call windows), workspace-assignment rules
  (e.g. "Signal always on workspace 9"), and snap-preset-style resize.

## Known skews

- **i3ipc Python binding:** pinned to `>= 2.2.1, < 3`. Ships as the
  `perch[sway]` optional extra; `SwayBackend.is_available()` returns True
  only when `$SWAYSOCK` is set. `start()` raises `BackendUnavailable` if
  the binding is not installed.
- **Workspace numbering:** Sway allows named-only workspaces (no `num`).
  We report those as desktop index 0. The i3-IPC `num` field is used for
  numeric workspaces.
- **Output `refresh_mhz`:** populated from the `current_mode.refresh`
  field, which Sway reports in Hz on some versions and mHz on others.
  Downstream code only uses this for display, so the unit mismatch is
  cosmetic. Consider normalising if an actual consumer of the field
  appears.

## Tested Sway versions

None yet — this is the landing commit. Community contributors running
Sway should exercise the `pytest -m sway` marker (to be added when the
first live test lands) and report their Sway + i3ipc versions in an
issue.

## Contributing

See `CONTRIBUTING.md` §Contributing a backend. The compliance suite
(`tests/backend/test_compliance.py`) is the acceptance bar.
