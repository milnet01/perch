# 05 — Backend: KWin / Plasma Wayland

Primary Wayland target. KWin also runs on X11, but Perch uses the X11 backend ([04-backend-x11.md](04-backend-x11.md)) there; this doc is the Wayland path.

This doc was substantially revised during Phase 2 research (see `11-roadmap.md`). Key changes from the original design:

- **JS scripts cannot register D-Bus services.** The Python side now owns the service; the JS script calls *out* to it.
- Plasma 5 → 6 renamed `client*` to `window*` across the scripting API; all references here use the Plasma 6 names.
- `metadata.desktop` in KWin script packages is deprecated in favour of `metadata.json`.
- Hotkeys should prefer the **`org.freedesktop.portal.GlobalShortcuts`** portal (especially under Flatpak) with KGlobalAccel as a non-Flatpak fallback.
- Pre-paint placement is **best-effort**, not guaranteed — the docs no longer promise "no visible flash."

## Why KWin first

- KDE Plasma is the project's primary desktop (the maintainer's daily driver, and the desktop with the best Wayland story for window scripting today).
- KWin is the only mainstream Wayland compositor that exposes a stable, in-tree scripting interface (the KWin Scripting API) — nothing comparable exists for Mutter or wlroots.
- That scripting API is what makes Wayland window management possible from an out-of-process tool at all. Without it, pure Wayland gives no way for a third-party program to set another window's geometry.

## Architecture: two halves, one backend

```
Perch (Python)                      KWin (compositor)
──────────────                      ─────────────────

┌───────────────────────┐
│ Python                │
│   owns                │   ← outbound D-Bus from JS arrives here
│     io.github.milnet01.Perch
│                       │
│  ┌─────────────────┐  │
│  │ KWinBackend     │  │
│  │  (sdbus-python) │  │    session bus
│  └────┬────────────┘  │◀────────────────┐
│       │                │                 │
│       │ D-Bus calls    │ ┌───────────────┴──────────────┐
│       └───────────────▶│ │ org.kde.KWin                  │
│                        │ │   /Scripting  (loadScript…)   │
│                        │ │   /KWin       (general API)   │
│                        │ └──────────────────────────────┘
│                        │
│                        │ ┌──────────────────────────────┐
│                        │ │ bundled JS script            │
│                        │ │   runs inside KWin           │
│                        │ │   subscribes to workspace.*  │
│                        │ │   calls out via callDBus to  │
│                        │ │   io.github.milnet01.Perch   │
│                        │ └──────────────────────────────┘
└────────────────────────┘
```

Two key D-Bus surfaces:

- **`org.kde.KWin` (KWin → Perch calls into KWin)** — the built-in service. Used to load/unload scripts and query session-wide info. Method `org.kde.KWin.Scripting.loadScript(path)` is how we install our JS.
- **`io.github.milnet01.Perch` (JS script → Perch calls into Python)** — our own service, owned by the Perch Python process. The bundled JS script uses `callDBus("io.github.milnet01.Perch", "/KWin", "io.github.milnet01.Perch.KWin1", "WindowAdded", …)` to notify us of compositor events.

The JS script does *not* register a D-Bus service. KWin's JS sandbox only exposes `callDBus(service, path, iface, method, ...args)` for outbound calls.

## The bundled KWin script

**Location in repo:** `perch/backend/kwin/script/`

Contents (indicative):

```
perch/backend/kwin/script/
├── metadata.json              ← KPackage metadata (JSON; .desktop is deprecated)
├── contents/
│   └── code/
│       └── main.js            ← the script
└── README.md
```

### What the script does

The script's job is to be KWin's *in-process eyes and hands* on Perch's behalf.

**Inbound (what Perch asks KWin to do via the script):**

The script cannot export a D-Bus method, so Python→script commands flow via **long-poll with callback chaining** (kdotool-style; validated in Phase 2.5 against real Plasma 6 scripts).

1. At startup the script makes a `callDBus(PERCH, /KWin, ..., "PollCommand", callback)` call.
2. Python **holds the reply** until a command is queued, or up to a heartbeat ceiling of ~5 s (after which it returns `{"nop": true}` so KWin doesn't GC the pending callback).
3. When the callback fires, the script parses the JSON command, executes it (e.g. `w.frameGeometry = Qt.rect(...)`), calls `CommandDone(seq, "ok")`, and **re-arms the long-poll** by calling `PollCommand` again.

Why long-poll, not tight polling:

- Zero wasted wakeups — KWin only runs JS when Perch has something to say.
- Latency is a single D-Bus round-trip (sub-millisecond), not a polling interval.
- Validated in the wild: `kdotool` uses the same pattern and it's known to work across Plasma 6.0–6.4.
- The original Phase-1 design used 50 ms polling; it was replaced during Phase 2.5 research because long-poll is demonstrably better and no more complex to implement.

For bulk operations (apply a whole layout), Python emits a single command with a `batch: [...]` array and the script runs all sub-ops in one tick, landing in the same compositor frame.

**JSON strings end-to-end, not typed D-Bus arguments.** `callDBus` in KWin's JS sandbox has a known footgun (KWin bug 486024): variadic args go through Qt's best-guess type coercion, which breaks for numeric D-Bus signatures (`i`, `u` vs. JS's unified `double`). Perch sidesteps this by making every argument to `WindowAdded` / `PollCommand` / `CommandDone` etc. a **string** (JSON-encoded payload, decoded on the Python side). Adds a few μs per call — negligible — and makes the script robust against KWin marshalling quirks.

**Outbound (what the script tells Perch):**

The script subscribes to `workspace.windowAdded`, `workspace.windowRemoved`, per-window `frameGeometryChanged`/`captionChanged`/`fullScreenChanged`/`minimizedChanged`/`maximizedChanged`/`desktopsChanged`/`outputChanged`, and `workspace.screensChanged`, and `callDBus`es each one into Perch.

Every method on `io.github.milnet01.Perch.KWin1` has signature `s` (one JSON-encoded string) — see "JSON strings end-to-end" below — so the D-Bus layer stays dumb about payload shape. The table below gives the JSON fields each method delivers:

| KWin signal (Plasma 6) | Perch D-Bus method (`s` payload) | Payload fields |
|---|---|---|
| `workspace.windowAdded(window)` | `WindowAdded` | `id, app_id, wm_class, title, pid, type, state, x, y, w, h, output, desktop, role` |
| `workspace.windowRemoved(window)` | `WindowRemoved` | `id` |
| `window.frameGeometryChanged(old)` | `WindowGeometryChanged` (debounced 50 ms) | same as `WindowAdded` (full snapshot) |
| `window.captionChanged()` (and other property signals) | `WindowPropertiesChanged` | same as `WindowAdded` |
| `workspace.screensChanged()` | `OutputsChanged` | empty string (Perch re-queries via `queryOutputs` command) |

`id` is `window.internalId.toString()` (a QUuid), stable for the window's lifetime. `desktop` is 0-based (`-1` = sticky / all desktops); the script converts from KWin's 1-based `x11DesktopNumber` at the boundary.

### Pre-placement hook (best-effort)

The script subscribes to `workspace.windowAdded` and, in the *same event tick*, calls out to Perch asking "is there a remembered geometry for this identity?" (`QueryPlacement(json)`). The reply races the first paint.

**No hard guarantee.** Confirmed in Phase 2 + 2.5 research: there is no `workspace.windowAboutToBeAdded` signal, and even setting `window.frameGeometry` synchronously inside the `windowAdded` handler can be visibly late on XWayland clients or on apps that call `xdg_surface.set_window_geometry` *after* mapping.

**De-facto mitigation: temporarily set `window.keepAbove = true`** while applying geometry, then clear it once the first frame has been painted. This doesn't prevent a mis-placed first paint but reduces the perceived "jump" because the window is stacked predictably during the transition. Used by several Plasma 6 tilers.

Perch declares `can_preplace_windows = True` on this backend with a note honestly describing the best-effort semantics. X11 / GNOME / Sway / Hyprland set it to `False`.

## The Python side (`KWinBackend`)

Uses **`sdbus-python`** for D-Bus. The backend owns the `io.github.milnet01.Perch` service name on the session bus and exports `io.github.milnet01.Perch.KWin1` on `/KWin`.

### Lifecycle

1. `start()`:
   a. Probe `$KDE_SESSION_VERSION` ≥ 6 and `$XDG_SESSION_TYPE` ≥ `wayland`. Refuse older Plasmas (Plasma 5 support is out of v1 scope; see [11-roadmap.md](11-roadmap.md)).
   b. Acquire the bus name `io.github.milnet01.Perch` (release it in `stop`).
   c. Install the bundled script:
      - For Flatpak installs, ensure the script is copied to the host's `~/.local/share/kwin/scripts/org.milnet01.perch/` (see [10-packaging.md](10-packaging.md)). KWin runs on the host and cannot read Flatpak's `/app/` path — or its sandboxed `$XDG_DATA_HOME`.
      - Call `org.kde.KWin.Scripting.loadScript(path, pluginId)` → `run()`. The two-argument form is required so `unloadScript(pluginId)` later works; the single-argument form loads anonymously and cannot be unloaded cleanly.
   d. Wait up to 2 s for the first `WindowAdded` or `OutputsChanged` to confirm the script is alive and wired.
   e. Emit `backend_connected`.
2. `stop()`:
   a. **Invalidate in-flight `PollCommand` awaiters** (see "Poll invalidation" below). Without this, an orphan awaiter from the previous JS instance consumes the next queued command and routes its reply to a KWin callback that no longer exists.
   b. Unload the script via `Scripting.unloadScript(pluginId)` (returns `bool`).
   c. Release the bus name.
3. If the script disappears (KWin crash/restart): invalidate polls (same reason), re-install and re-subscribe. Re-emit `backend_connected`. Window state is not lost because `state.json` on disk is authoritative.

### Poll invalidation

Bug surfaced by the M2.5 spike and fixed there before the real backend inherits it (see [`experiments/kwin_ipc_spike/SPIKE_RESULTS.md`](../experiments/kwin_ipc_spike/SPIKE_RESULTS.md) §cycle probe).

When `unloadScript` is called, the JS callback chain dies, but any Python coroutines that are currently inside a `PollCommand` method handler are still `await`ing the command queue. The next command Perch queues (after reload) gets handed to one of those orphans, which sends its reply back over D-Bus to a callback ID KWin has already freed — so the *new* script instance never sees the command. Symptom: first echo after reload hangs until its 5 s timeout.

The fix is a generation-gated `PollCommand`:

1. `KWinBackend` holds an `asyncio.Event` (`_invalidated`).
2. Each `PollCommand` snapshots `self._invalidated` at entry and races `queue.get()` against `invalidated.wait()` (plus the 5 s heartbeat ceiling).
3. On unload / reload, `stop()` calls `invalidate_polls()`: atomically swaps in a fresh `Event` and signals the old one. All orphan awaiters bound to the old event immediately return `{"nop": true, "reason": "invalidated"}`; all new `PollCommand` calls see the fresh event.

Inbound ordering: `stop()` must call `invalidate_polls()` *before* `unloadScript`, to guarantee orphans are drained before KWin tears down the callbacks.

### Script installation strategy

All install modes mirror the bundled script into the same destination:
`$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/`, which defaults to
`~/.local/share/kwin/scripts/org.milnet01.perch/`. KWin on Wayland runs
on the host and only reads scripts from the standard search path — so a
dev checkout in the repo, a Flatpak container's `/app/` path, and an RPM's
`/usr/share/` path all need the same copy-out step.

Inside a Flatpak, `$XDG_DATA_HOME` is redirected into the sandbox and is
**not** honoured: the target is resolved from `$HOME` so it lands on the
host, where KWin can read it. `PERCH_KWIN_SCRIPT_TARGET` overrides the
whole resolution, sandbox included.

Only the *source* differs:

- **Packaged install (RPM/AUR)**: source tree is shipped as package
  data under the installed `perch` Python package. The backend reads it
  via :data:`perch.backend.kwin.BUNDLED_SCRIPT_DIR`. No additional
  system-wide `/usr/share/perch/kwin/` path is created — the package
  directory is the source of truth.
- **Flatpak** (see [10-packaging.md](10-packaging.md)): source is the
  Flatpak-private package directory (same
  `BUNDLED_SCRIPT_DIR` read from inside the sandbox). The Flatpak
  manifest grants `--filesystem=xdg-data/kwin/scripts:create` so the
  mirror step can write the host-visible copy.
- **Dev install** (`pip install --user --break-system-packages -e .`):
  source is the in-tree `src/perch/backend/kwin/script/` directory; target
  is unchanged. ``PERCH_KWIN_SCRIPT_TARGET`` can redirect the target
  (tests use this; end users shouldn't).

The mirror is handled by :func:`perch.backend.kwin.install.ensure_installed`.
It's idempotent when the on-disk version already matches the bundled
version, and will tear down / rewrite a stale install otherwise.

The script is **versioned** (in `metadata.json` `KPlugin.Version` — see
:data:`perch.backend.kwin.BUNDLED_SCRIPT_VERSION`) and **pinned** by the
Python backend — Perch refuses to load a script whose version isn't the
bundled one, to avoid behaviour drift between JS and Python halves.
:class:`perch.backend.kwin.install.ScriptVersionMismatch` is raised if
after install the on-disk version still doesn't match (shipped package
is broken or filesystem intervened).

### Outputs

`workspace.screens` on Plasma 6 returns `QList<KWin::Output*>`. The script exports an `Outputs()` method (poll-reply, not a live D-Bus method) returning a JSON blob. Perch also listens to `workspace.screensChanged` to trigger re-enumeration.

The legacy `org.kde.KWin.Management.screens` D-Bus interface exists but is less complete than the script-sourced path; prefer the script.

### Virtual desktops

`org.kde.KWin` exposes `currentDesktop()`, `numberOfDesktops()`, and signal `currentDesktopChanged(int)` (1-based). Perch converts to 0-based `DesktopIndex` at the boundary.

### Hotkeys

Two providers share the :class:`HotkeyProvider` protocol in
`src/perch/backend/kwin/hotkeys.py`; `choose_provider()` picks one at
startup.

**Preferred path: `org.freedesktop.portal.GlobalShortcuts`.** Used when
the portal is reachable and either we're inside a Flatpak sandbox
(`/.flatpak-info` is present) or the caller explicitly injects a portal
factory. Flow:

1. `CreateSession(options)` returns a Request path; Perch subscribes to
   `org.freedesktop.portal.Request.Response` on that path and reads the
   resulting `session_handle`.
2. `BindShortcuts(session_handle, shortcuts, parent_window, options)`
   registers each `(id, {preferred_trigger, description})` tuple.
   Triggers are translated into XDG form (`CTRL+SHIFT+Q`) by
   `_portable_to_xdg_accel` at the boundary.
3. `GlobalShortcuts.Activated(session_handle, id, timestamp, opts)`
   fires on every press; Perch dispatches by id to the registered
   callback.

The portal path covers the full xkbcommon keysym range (no Fn / letter
/ digit restriction) and works sandboxed. Unbind is modelled as a
local-map eviction because the portal doesn't expose `UnbindShortcuts`
— the portal's session-close is the authoritative cleanup; closing the
session at `stop()` releases every binding at once.

**Fallback: direct KGlobalAccel** (`org.kde.kglobalaccel` on the
session bus). Used when the portal probe fails — non-Flatpak
installs on Plasma without xdg-desktop-portal-kde ≥ 6, or lean sessions
where only KGlobalAccel is available. Hotkeys show up in *System
Settings → Shortcuts* under the "Perch" component.

- Register via `KGlobalAccel.setShortcutKeys(action_id, keys, loading)`
  (`setShortcut` is deprecated since KF 5.90). `action_id` is a 4-tuple
  `[component_unique, action_unique, component_friendly,
  action_friendly]`; Perch uses
  `[perch, <callback_id>, Perch, <description>]`.
- `keys` is a list of ints in Qt's packed "modifiers | key" encoding.
  KGlobalAccel's encoder supports letters, digits, and F1..F35; named
  special keys (Return, Escape, …) are portal-only — users who hit that
  on a KGlobalAccel-only install rebind via System Settings.
- Signal: `globalShortcutPressed(component, action_id, timestamp)` —
  filters on `component == "perch"` and routes `action_id` to the
  callback.
- Conflicts: if the key is already grabbed, `setShortcutKeys` returns a
  different keysym. Perch detects the mismatch and raises
  `HotkeyBusyError`, which the backend translates into a `backend_error`
  signal.

**Env override for tests and unusual installs**:
`PERCH_HOTKEY_PROVIDER=mock|portal|kglobalaccel` short-circuits the
probe.

`can_register_hotkeys = True` on this backend.

## Capabilities declared

```python
Capabilities(
    can_set_position      = True,
    can_set_size          = True,
    can_set_monitor       = True,
    can_set_desktop       = True,
    can_set_state         = True,
    can_enumerate_windows = True,
    can_observe_geometry  = True,
    can_observe_outputs   = True,
    can_register_hotkeys  = True,
    can_preplace_windows  = True,   # best-effort; occasional flicker acceptable
    notes = "KWin scripting on Plasma ≥ 6 via bundled script "
            "+ GlobalShortcuts portal (KGlobalAccel fallback). "
            "Pre-paint placement is best-effort; occasional first-frame "
            "flicker is possible but usually imperceptible."
)
```

## Identity sourcing

| Field | KWin source (via script, Plasma 6 API) |
|---|---|
| `app_id` | `window.resourceName` (Wayland) — same field name for X11 `WM_CLASS.instance` under KWin |
| `wm_class` | `window.resourceClass` |
| `title` | `window.caption` |
| `pid` | `window.pid` |
| `type` | `window.windowType` → mapped to `WindowType` |
| `state` | Composed from `window.fullScreen`, `window.minimized`, `window.maximizeMode` |

Plasma 6 scripting renamed `client*` properties and signals to `window*` across the API; use the new names. Any KWin documentation that still says `client.caption` is stale.

## Plasma 5 vs Plasma 6

Perch targets **Plasma 6** as the minimum. Plasma 5 support would require a substantially different JS script (`clientAdded` vs `windowAdded`, `clientList` vs `windowList`, etc.) and is explicitly excluded from v1. Plasma 6 is the current shipping version on every modern distro and has been since late 2023.

If/when Plasma 5 support is added (post-v1), it ships as a *second* bundled script selected at install time by KWin version detection. This doc is updated then.

## Edge cases

- **Window with no `app_id`** (some Java / Electron apps early in startup): the script withholds `WindowAdded` until `app_id` is non-empty, with a 1 s fallback after which it fires with `app_id=""` and the core uses title-based identity.
- **XWayland clients** are reported by KWin alongside native Wayland windows. They have `resourceClass` set and often empty `resourceName`; the core handles identity uniformly.
- **Per-output scaling**: KWin reports logical coordinates; Perch stores them as-is.
- **Decorations**: the script's `frameGeometry` values include server-side decorations. Numbers are directly comparable to what the X11 backend produces *after* `_NET_FRAME_EXTENTS` subtraction — documented so cross-session-type continuity works.
- **API break on 6.x.y minor releases**: KWin scripting has no formal stability promise. Each point release should be smoke-tested. See [11-roadmap.md](11-roadmap.md) risks list.

## Testing strategy

- **Unit tests** against `MockBackend` (same as all backends).
- **M2.5 spike**: [`experiments/kwin_ipc_spike/`](../experiments/kwin_ipc_spike/) — a ~30-line JS script + sdbus-python host + measurement harness that exercises the long-poll round-trip, **done 2026-04-20 on Plasma 6.6.4**. See [`SPIKE_RESULTS.md`](../experiments/kwin_ipc_spike/SPIKE_RESULTS.md) for the recorded numbers (p50 = 138 µs, p99 = 452 µs over 10 000 round-trips; reload/recovery clean after the orphan-awaiter fix). Plasma 6.2 / 6.3 / Neon-unstable runs are deferred to M5-prep.
- **Integration test (M5)**: spin up `kwin_wayland --virtual` in CI, install the script, drive scripted window lifecycles, assert round-trip. Command: `dbus-run-session -- kwin_wayland --virtual --width 1920 --height 1080 --exit-with-session <test-runner>`. Packages: `kwin-wayland` on Fedora/openSUSE, `kwin-wayland + kwin-wayland-backend-virtual` on Debian. Ubuntu 24.04 runner's `kwin-wayland` is 1-2 minor versions behind KDE upstream; a Fedora container (`registry.fedoraproject.org/fedora:42` or `ghcr.io/kdeneon/plasma:unstable`) is more reliable for edge-version testing.
- **CI cadence**: the headless KWin test is a **nightly job**, not a per-PR gate. Phase 2.5 finding: `kwin_wayland --virtual` in GitHub Actions is fragile (needs `libseat`/`seatd` or `--no-lockscreen`, writable `XDG_RUNTIME_DIR`, and the upstream-vs-distro version skew). Gating every PR on it would cause frequent false-red builds. PRs run the mock-backend compliance suite; the nightly job runs the real-KWin integration.
- **Manual test checklist** in `docs/testing/kwin-checklist.md` (created in M5).

## Out of scope

- Activities (KDE's grouping above virtual desktops). Activity-scoped rules are a v2 feature.
- Plasma's own "Special Window Rules" — Perch does its own thing rather than wrap KWin's rules editor.
- Plasma 5.
