# Mutter / GNOME Shell backend — status

**Stub.** Implements `WindowBackend` against a bundled GNOME Shell
extension that exports `io.github.milnet01.Perch.Mutter1` on the session
bus. Authoritative design: `docs/06-backend-stubs.md` §Mutter / GNOME Shell.

## Capabilities (as of v1)

| Capability | Value | Notes |
|---|---|---|
| `can_set_position` | True | `Meta.Window.move_resize_frame(true, x, y, w, h)` via extension. |
| `can_set_size` | True | Same call; width/height in the same message. |
| `can_set_monitor` | True | `Meta.Window.move_to_monitor(index)`. |
| `can_set_desktop` | True | `Meta.Window.change_workspace(ws)`. |
| `can_set_state` | True | `maximize` / `unmaximize` / `minimize` / `make_fullscreen`. |
| `can_enumerate_windows` | True | `global.display.list_all_windows()`. |
| `can_observe_geometry` | True | Window signals on `Meta.Display` (landing in a follow-up). |
| `can_observe_outputs` | True | `Meta.MonitorManager` change signals. |
| `can_register_hotkeys` | True | `Main.wm.addKeybinding(...)` via the extension, backed by a gschema. |
| `can_preplace_windows` | **False** | `window-created` fires before Mutter is ready to honour geometry writes; extension must idle-add the call, producing a visible snap. |

## Architecture

Two halves shipped from the same Python package:

- **Python** (`backend.py`) — opens the session bus, proxies
  `io.github.milnet01.Perch.Mutter1`, translates replies.
- **GJS** (`extension/`) — `metadata.json` + `extension.js`. Runs inside
  `gnome-shell`. Performs all `Meta.Window` work.

## Minimum GNOME version

**GNOME 48.** Raised from 45 during Phase 2 research:

- Fedora 43 (Oct 2025) ships GNOME 49.
- Debian 13 "Trixie" (Aug 2025) ships GNOME 48 — the trailing distro.
- Ubuntu 25.10 ships GNOME 49; 26.04 LTS (Apr 2026) expected on GNOME 50.

`extension/metadata.json` lists `shell-version: ["48", "49", "50"]`.
Unsupported versions must register a separate git branch (see below).

## Two-step install

**Flatpak Perch cannot install the extension.** There is no portal for
shell-extension installation, and a Flatpak can't write into
`~/.local/share/gnome-shell/extensions/` in a way GNOME will trust.

Three user paths (order of preference):

1. **Distro package** — openSUSE OBS / AUR ship the
   extension alongside Perch.
2. **Extension Manager** — `com.mattjakeman.ExtensionManager` from
   Flathub can write to `~/.local/share/gnome-shell/extensions/`.
3. **Dev path** — Perch ships a helper that copies
   `extension/` into `~/.local/share/gnome-shell/extensions/perch@milnet01.github.io/`
   and prints instructions to run
   `gnome-extensions enable perch@milnet01.github.io` and log out / in.

Until the extension is enabled, `MutterBackend.start()` raises
`BackendUnavailable` with the instruction string from `backend.py`.

## Extension lifecycle across GNOME versions

Upstream GNOME extension APIs break every major release:

- GNOME 45 forced an ESM migration; every pre-45 extension broke.
- 46, 47, 48 each have a porting guide on gjs.guide.
- Well-known extensions (Dash to Dock, Just Perfection, Pop Shell)
  maintain *per-GNOME-version git branches* plus runtime
  `Config.PACKAGE_VERSION` checks.

**Practical consequence:** expect to maintain ~3 parallel source
branches of `extension/` at any given time. This STATUS.md lists the
tested GNOME versions + the branch mapping when the first maintainer
takes it on.

## Schema

Registering hotkeys via `Main.wm.addKeybinding` requires a gschema.
The landing scaffold in `extension.js` calls `getSettings()` but the
schema file — normally `org.gnome.shell.extensions.perch.gschema.xml`
compiled to `gschemas.compiled` — is **not** shipped yet. Registering
a hotkey therefore fails with
`{"ok": false, "error": "unsupported", ...}` until that schema lands in
a follow-up PR or is provided by the per-GNOME packaging.

## What works (in the scaffold)

- D-Bus shape: `metadata.json` + `extension.js` export the
  `Mutter1` interface documented in `backend.py`.
- Window enumeration + describe shape matches the decoders in
  `backend.py`.
- Geometry writes with the unmaximize-then-move dance.
- State transitions (normal / maximized / minimized / fullscreen).

## What does not work (by design / by deferral)

- **Live event observation.** Extension-side hooks into
  `workspace.window_added` / `geometry-changed` are not wired. Until
  they land in a follow-up, the Python side polls via `list_windows`
  for reconciliation.
- **Pre-paint placement.** See docs/06 — Mutter's `window-created`
  signal fires before the window is ready to honour geometry writes.
- **Hotkeys.** Schema blocking — see above.

## Tested GNOME versions

None yet — this is the landing commit. Community contributors
running GNOME should install the dev-path scaffold and verify basic
round-trip with a minimal test.

## Contributing

See `CONTRIBUTING.md` §Contributing a backend. This stub has the
highest ongoing maintenance cost of the three M6 stubs — GNOME API
churn across releases is the primary reason.
