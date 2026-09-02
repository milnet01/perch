# 06 — Backend stubs: Mutter, Sway, Hyprland

These three backends ship as **stubs** in v1. "Stub" means:

- The Python class exists and implements `WindowBackend`.
- `start()` works and declares honest capabilities.
- A minimum of events and commands work well enough to list windows and read/write geometry manually from the config dialog.
- Autoplacement (restore on open, pre-placement before first paint) is explicitly **unsupported** — none of the three can do it reliably.
- Each stub has a `STATUS.md` next to it describing what works and what doesn't, which `pytest -m <backend>` tests pass, and the known blockers.

This doc defines the **contract the stubs must meet** so upstream contributors know what they're signing up for. It does not reimplement [03-backend-interface.md](03-backend-interface.md); it extends it with per-compositor constraints.

This doc was substantially revised during Phase 2 research (see `11-roadmap.md`). Notable changes:

- GNOME floor raised from 45 to **48** (current distros ship 48–50).
- Pre-paint placement explicitly **unsupported** on Mutter.
- Flatpak cannot install a GNOME Shell extension — documented as a **two-step install**.
- GNOME extensions require **per-release source branches**; the stub status reflects that maintenance cost.
- Hyprland IPC is marked best-effort: socket2 event format has broken backwards across minor releases.

**Implementation status (M6, landed 2026-04-21):** all three stubs exist
under `src/perch/backend/{mutter,sway,hyprland}/`. Each ships with a
`STATUS.md` covering capabilities, what works, what doesn't, and known
skews. `perch.backend.select()` probes the session environment and picks
the right backend; the compliance suite filters by
`WindowBackend.is_available()`. Live-integration tests for the three
stubs are deferred — the unit-tested decoders + the M5
`kwin_wayland --virtual` harness pattern carry the weight until
contributors land equivalents.

## Mutter / GNOME Shell

### Transport

A bundled **GNOME Shell extension** (`perch@milnet01.github.io`) running inside `gnome-shell`, exposing a D-Bus service `io.github.milnet01.Perch.Mutter` via `Gio.DBusExportedObject.wrapJSObject(...).export(Gio.DBus.session, path)`. Python's `MutterBackend` calls into that service.

Extensions *can* register D-Bus services (confirmed pattern — `Focused Window D-Bus`, `Window Calls Extended`, `gTile` all do). There is still no in-tree Mutter scripting interface comparable to KWin's; an extension is the only mechanism available.

### Minimum GNOME version

**GNOME 48.** Raised from 45 during Phase 2 research:

- Fedora 43 (Oct 2025) ships GNOME 49.
- Debian 13 "Trixie" (Aug 2025) ships GNOME 48 — the trailing distro.
- Ubuntu 25.10 ships GNOME 49; 26.04 LTS (Apr 2026) expected on GNOME 50.
- GNOME 45 targeting is not worth the porting effort; it's effectively retired in new installs.

### Capabilities target for v1

```python
Capabilities(
    can_set_position      = True,       # via extension; Meta.Window.move_resize_frame
    can_set_size          = True,
    can_set_monitor       = True,
    can_set_desktop       = True,
    can_set_state         = True,
    can_enumerate_windows = True,
    can_observe_geometry  = True,
    can_observe_outputs   = True,
    can_register_hotkeys  = True,       # via Main.wm.addKeybinding / gsettings custom-keybindings
    can_preplace_windows  = False,      # see below
    notes = "GNOME ≥ 48 via bundled Shell extension. "
            "Pre-paint placement not supported: windows appear at their "
            "default location, then snap to the target geometry. "
            "Extension must be installed outside the Flatpak (two-step install)."
)
```

### `move_resize_frame` caveats

Phase 2 research established two constraints on `Meta.Window.move_resize_frame(user_op, x, y, w, h)`:

1. **Tiled/maximised windows ignore geometry writes.** The extension must `unmaximize()` / `unmake_tile()` first when repositioning.
2. **Racy immediately after window creation.** `window-created` on `Meta.Display` fires before Mutter is ready to honour geometry writes. The extension must `GLib.idle_add(...)` the placement call, or wait for `first-frame` / `shown`, before calling `move_resize_frame`. This is why `can_preplace_windows = False` — the user will see the window appear at its launch geometry, then move.

### Extension lifecycle across GNOME versions

Upstream GNOME extension APIs break every major release:

- GNOME 45 forced an ESM migration; every pre-45 extension broke.
- 46, 47, 48 each have a porting guide on gjs.guide.
- Well-known extensions (Dash to Dock, Just Perfection, Pop Shell) maintain *per-GNOME-version git branches* plus runtime `Config.PACKAGE_VERSION` checks.

**Practical consequence for Perch**: expect to maintain ~3 parallel source branches of the extension at any given time. The stub's `STATUS.md` must list the tested GNOME versions and the branch mapping. This is explicitly flagged in [11-roadmap.md](11-roadmap.md) as ongoing maintenance cost.

### Extension delivery and two-step install

**Flatpak Perch cannot install the extension.** There is no portal for shell-extension installation, and a Flatpak can't write into `~/.local/share/gnome-shell/extensions/` in a way GNOME will trust. Three documented user paths:

1. **Recommended**: ship the extension as a **separate distro package** — openSUSE OBS / AUR — or publish to extensions.gnome.org (EGO).
2. **Fallback**: ask the user to install it via `com.mattjakeman.ExtensionManager` from Flathub, which *can* write to `~/.local/share/gnome-shell/extensions/` because it runs with the right portal access.
3. **Dev path**: `python3 scripts/install-gnome-extension.py` copies the bundled extension into `$XDG_DATA_HOME/gnome-shell/extensions/perch@milnet01.github.io/` and prints the two steps it deliberately does not take — `gnome-extensions enable perch@milnet01.github.io`, then log out and back in. It refuses to replace an existing install unless given `--force`, since that install may be a distro package's.

Perch's first-run wizard on GNOME surfaces this explicitly: *"GNOME requires Perch's Shell extension to be installed separately. Install it via Extension Manager (recommended) or the distro package."* The tray icon shows a warning state ("Perch — awaiting GNOME extension") until the extension is enabled.

### Publishing to extensions.gnome.org

- EGO review takes weeks; every update re-enters the queue.
- Review checks for malicious code, not bugs. D-Bus services are explicitly allowed.
- Source must be readable JS (no minification).
- Acceptable, but budget the review latency in release planning.

### Hotkeys

On Mutter via the extension: `Main.wm.addKeybinding(action_id, settings, flags, modes, callback)` is the conventional path. Requires a gschema under the extension's data dir. `can_register_hotkeys = True`.

For non-Flatpak Perch installs that don't ship the extension but still want hotkeys, a fallback is to install gsettings custom-keybindings pointing at CLI invocations of Perch — documented but not automated.

### Contributor path

Owned by the community. `docs/contributing-backend-mutter.md` (to be added when a first contributor steps up) will document the GJS conventions, the per-GNOME-branch policy, and the release-to-EGO checklist.

## Sway / wlroots

### Transport

`swaymsg` / the i3-IPC socket at `$SWAYSOCK`. Python binding: **`i3ipc>=2.2.1`** (async variant — `i3ipc.aio.Connection`). Research finding (Phase 2): `i3ipc-python` is stable on Python 3.11/3.12; sway-ipc protocol hasn't changed in breaking ways.

### Capabilities target for v1

```python
Capabilities(
    can_set_position      = False,    # Sway is tiling-first; floating-only geometry
    can_set_size          = True,
    can_set_monitor       = True,     # via 'move window to output'
    can_set_desktop       = True,     # workspace
    can_set_state         = True,
    can_enumerate_windows = True,
    can_observe_geometry  = True,
    can_observe_outputs   = True,
    can_register_hotkeys  = False,    # Sway owns hotkeys via its config
    can_preplace_windows  = False,
    notes = "Sway/wlroots. Geometry applies only to floating windows; "
            "tiled windows snap to their container. Use 'make floating' "
            "in your Sway config or via Perch's 'Float this window' action."
)
```

### Design note

The mismatch between Perch's "set absolute geometry" model and Sway's tiling model is admitted: on Sway, Perch is most useful for:

- Floating windows (pop-outs, scratchpads, video call windows).
- Workspace assignment rules (*"Signal always on workspace 9"*).
- Snap presets acting as "resize floating to" presets.

For general tiling users, Sway's own `for_window` directive is already the right tool. Perch does not compete with it.

### Window state

`set_state(wid, WindowState.MINIMIZED)` maps to `move scratchpad`; `WindowState.FULLSCREEN` maps to `fullscreen enable`. `WindowState.MAXIMIZED` has no equivalent in Sway's model (tiled windows already fill their container; floating windows have no maximize toggle) and raises `BackendUnsupported`. The core engine's apply pipeline catches this and substitutes geometry equivalent to the `"maximize"` preset — see [07-rules-engine.md](07-rules-engine.md) §Apply order.

### Hotkeys

Sway hardcodes hotkeys in its config file; there is no runtime API to grab keys. `can_register_hotkeys = False`. Users who want Perch hotkeys on Sway can bind keys to `swaymsg exec` invocations of Perch's CLI (coming in v1.x) in their Sway config. This is documented in the stub's `STATUS.md`.

### Contributor path

Owned by the community. A first-pass spec is achievable because `swaymsg`'s protocol is stable and well documented; the stub exists to stop the Sway-friendly parts of Perch (workspace rules, floating geometry) being totally unusable.

## Hyprland

### Transport

`hyprctl` + the Hyprland IPC socket (`$HYPRLAND_INSTANCE_SIGNATURE` → `/tmp/hypr/$HIS/.socket.sock` for commands and `.socket2.sock` for events).

**Strategy (Phase 2 revision):**

- **Queries**: shell out to `hyprctl -j <query>` (JSON output). More robust than parsing the plain-text query socket.
- **Events**: subscribe to `.socket2.sock` directly, parse the `EVENT_NAME>>DATA\n` format line by line, **wrap in try/except + log-skip unknown events**. Phase 2 research found the event format has broken backwards across minor releases (event types added, at least one field-order shift around Hyprland 0.40). Defensive parsing is mandatory.
- **No published Python binding** is mature enough to rely on; `pyprland` is a plugin runner, not a general IPC binding.

### Minimum Hyprland version

**Hyprland ≥ 0.40.** Pinned via a version check at `start()`; below that the stub refuses to run rather than dispatching to unknown-format events.

### Capabilities target for v1

```python
Capabilities(
    can_set_position      = True,     # via 'dispatch movewindow'
    can_set_size          = True,
    can_set_monitor       = True,
    can_set_desktop       = True,     # workspace
    can_set_state         = True,
    can_enumerate_windows = True,
    can_observe_geometry  = True,
    can_observe_outputs   = True,
    can_register_hotkeys  = False,    # Hyprland owns hotkeys via its config
    can_preplace_windows  = False,
    notes = "Hyprland ≥ 0.40 via hyprctl -j + .socket2.sock events. "
            "Event parsing is defensive; unknown events are logged and skipped. "
            "Like Sway, geometry applies cleanly only to floating windows."
)
```

### Window state

Same story as Sway: `MINIMIZED` and `FULLSCREEN` map to `hyprctl` dispatches (`movetoworkspace special` and `fullscreen 1`), while `MAXIMIZED` has no Hyprland equivalent and raises `BackendUnsupported`. The core engine substitutes geometry against the work area — see [07-rules-engine.md](07-rules-engine.md) §Apply order.

### Contributor path

Community. The Hyprland ecosystem's informal IPC stability makes this the most maintenance-heavy of the three stubs; `STATUS.md` must note the tested Hyprland version range and be updated each release cycle.

## What "stub" does *not* mean

Stubs are real backends. They must:

- Never crash Perch if the compositor misbehaves.
- Never emit malformed events (use the same frozen dataclasses).
- Declare accurate capabilities so the UI can grey out impossible actions.
- Pass the full mock-backend compliance test suite (parameterised across all backends — tests that need specific capabilities skip themselves).
- Have a `STATUS.md` explaining what works, which compositor versions are tested, and any currently-known skew.

Stubs are allowed to:

- Skip pre-paint placement (all three do).
- Skip event-driven rule application if polling works acceptably.
- Not support every snap preset (but they must say which ones they support).

## Minimum backend acceptance test

Every backend (stubs included) must pass:

```
pytest tests/backend/test_compliance.py
```

The suite parameterises over every backend in `tests/backend/conftest.py::BACKEND_CLASSES`. Adding a new backend means registering it there; the existing tests then run against it automatically, skipping cases where the backend declares the relevant capability off.

The compliance suite exercises:

1. `start()` / `stop()` lifecycle.
2. `list_windows()` shape validation.
3. `list_outputs()` shape validation.
4. Announced capabilities match actual behaviour (if `can_set_position`, then setting a position actually changes it).
5. Event ordering (`window_opened` before `geometry_changed`; `window_closed` terminal).
6. Error taxonomy (unknown window → `UnknownWindow`, unsupported op → `BackendUnsupported`).

A stub that doesn't pass this is not merged, even if the rest of the backend is "mostly" written.
