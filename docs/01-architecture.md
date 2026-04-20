# 01 — Architecture

## Shape of the program

Perch is a single long-running user-session process with this internal layout:

```
                       ┌──────────────────────────────────────┐
                       │             Perch (one process)      │
                       │                                      │
  ┌────────┐  Qt sig   │  ┌────────┐   ┌──────────────────┐   │
  │ Tray   │◀──────────┤  │  UI    │   │  Config dialog   │   │
  │ icon   │──────────▶│  │ layer  │◀─▶│  (Qt Widgets)    │   │
  └────────┘  actions  │  └────┬───┘   └──────────────────┘   │
                       │       │                              │
                       │       ▼                              │
                       │  ┌──────────────────┐                │
                       │  │   Core service   │                │
                       │  │  (state +        │                │
                       │  │   rules engine + │                │
                       │  │   hotkeys)       │                │
                       │  └───────┬──────────┘                │
                       │          │ WindowBackend API         │
                       │          ▼                           │
                       │  ┌─────────────────────────────────┐ │
                       │  │      Active backend (one)       │ │
                       │  │  X11 / KWin / Mutter / Sway …   │ │
                       │  └──────────────┬──────────────────┘ │
                       └─────────────────┼────────────────────┘
                                         │ compositor-specific
                                         ▼ (X11 / D-Bus / IPC)
                                 ┌───────────────┐
                                 │  Compositor   │
                                 └───────────────┘
```

There is **one** process, **one** active backend, and **one** Qt event loop.

## Why one process

- Tray icons are tied to a toolkit — with PySide6 that means a Qt event loop in the same process that shows the icon.
- Geometry restore must happen *fast* after a window appears (ideally before the user sees it in the wrong place). Going through extra IPC hops adds latency and failure modes.
- Perch's resource footprint is small; there is no CPU-bound work that justifies splitting.

The "tray frontend + core daemon" split is explicitly rejected for v1. If a future backend is so chatty that it must run in its own process (e.g. a GNOME Shell extension), the core talks to *it* over D-Bus — but the Perch process itself stays single.

## Layers

### UI layer

- `QSystemTrayIcon` for the tray presence.
- Qt Widgets for the config dialog.
- Pure-Qt, no direct compositor calls. The UI emits *intents* ("apply layout X", "add rule Y") which the core layer handles.
- See [08-ui.md](08-ui.md) for the widget inventory.

### Core service

The compositor-agnostic middle of the program. It owns:

- **Configuration** — parsed from disk, edited via the UI, written back atomically. See [02-state-format.md](02-state-format.md).
- **State** — the current set of known-managed windows, last-seen geometries, active profile, active layout.
- **Rules engine** — evaluates rules on window events and emits geometry actions. See [07-rules-engine.md](07-rules-engine.md).
- **Hotkey dispatcher** — subscribes to global hotkeys (via the backend or via `KGlobalAccel` on Plasma) and translates them into snap actions.
- **Event reducer** — consumes backend events (`window_opened`, `window_closed`, `geometry_changed`, `output_changed`), updates state, and decides what, if anything, to push back to the backend.

The core has no direct dependency on any compositor library. It only talks to a `WindowBackend` instance.

### Backend layer

Exactly one backend is active per session. The backend:

- Enumerates windows and outputs.
- Emits events for window-open, window-close, geometry-change, output-change.
- Accepts geometry-set and desktop-move commands.
- Advertises its capabilities (e.g. "I can set position," "I cannot enumerate windows across desktops").

The interface is defined in [03-backend-interface.md](03-backend-interface.md). Concrete backends are documented in 04–06.

## Process model

### Startup

1. Parse CLI args (none in v1; `--version`, `--debug` later).
2. Load config; if absent, create defaults.
3. Detect the session:
   - `$XDG_SESSION_TYPE` — `x11` vs `wayland`.
   - On Wayland, look for `$KDE_FULL_SESSION`, `$XDG_CURRENT_DESKTOP` to pick Plasma / GNOME / Sway / Hyprland.
4. Instantiate the matching backend. If none match, log an error and run in "UI-only" mode (settings can still be edited, but nothing is managed).
5. Connect backend signals to the core reducer.
6. Create the tray icon.
7. Enter the Qt event loop.

### Shutdown

- Normal quit (tray → Quit, or SIGTERM): write config and runtime state, disconnect the backend cleanly, exit 0.
- Session end (logout): the session manager sends SIGTERM; same path.
- Crash: state on disk is always last-known-good because all writes are atomic (temp file + rename). See [02-state-format.md](02-state-format.md).

### Autostart

Perch installs a `perch.desktop` XDG autostart entry (`~/.config/autostart/perch.desktop` for user installs, or from Flatpak metadata). The UI has a "Start Perch at login" checkbox that toggles this. Autostart itself is not a backend concern.

## Threading model

**Default: everything on the Qt main thread.**

- Qt requires all UI object access on the main thread.
- `sdbus-python` is async-based (`asyncio`), binding explicitly to the running loop. Perch runs a `qasync`-integrated event loop so a single loop drives both Qt and asyncio.
- X11 event handling is blocking-socket-style; it runs on the main thread via a `QSocketNotifier` on the X11 connection fd.

**Exceptions (off the main thread):**

- Long-running file I/O for export/import: offloaded to a `QThread` worker so the UI doesn't freeze.
- Network operations (none in v1): reserved for future optional features (e.g. syncing rules).

Anything a backend does in its own thread must marshal events back to the main thread before they reach the core (signals/slots handle this automatically with `Qt::QueuedConnection`).

## Event flow example: "Firefox opens"

1. Compositor creates a new top-level window.
2. Backend sees the event (X11: `MapNotify`; KWin: `windowAdded` signal over D-Bus; Mutter: extension event).
3. Backend constructs a `WindowInfo` and emits `window_opened`.
4. Core reducer:
   a. Looks up the window's **identity** (`WM_CLASS=Firefox`, title pattern, etc.).
   b. Consults the rules engine — is there a rule whose match targets this identity under the current profile?
   c. If yes, computes the target geometry and calls `backend.set_geometry(window_id, target)`.
   d. If no rule matches, falls back to the last-seen remembered geometry for this identity (if persistence is enabled for it).
   e. If there is nothing remembered and no rule, does nothing.
5. Backend translates the set-geometry call into the compositor's native API.
6. Core records the applied geometry as the current best-known value.

The whole path is designed to complete well under 100 ms after the window appears, so the user does not see the window pop up in the wrong place.

## Failure modes the architecture must tolerate

| Failure | Behaviour |
|---|---|
| Backend crashes / connection dies | Core enters "degraded" state; tray icon shows a warning; UI remains usable. User can restart the backend from the menu. |
| Config file corrupted at startup | Load the previous good config (`config.toml.bak`); log a warning; surface a notification. Never overwrite a corrupted file until a known-good config is loaded. |
| Compositor refuses a geometry set | Log and move on. Do not retry in a tight loop — a loop here would spam the compositor and could pin windows the user is trying to drag. |
| Monitor topology changes mid-action | Abort the in-flight layout apply; re-evaluate profile match; re-apply under the new profile. |
| Window matches multiple rules | Resolved by rule priority (explicit order in config). See [07-rules-engine.md](07-rules-engine.md). |

## Dependencies, fixed

| Concern | Library | Pin | Why |
|---|---|---|---|
| Toolkit / tray / UI | PySide6 (Qt) | `>=6.8,<7` | Primary desktop is KDE; Qt renders natively there and acceptably elsewhere |
| Async glue | `qasync` | `>=0.28,<1` | Integrates Qt + asyncio on one thread; 0.28+ supports the `asyncio.run(..., loop_factory=QEventLoop)` pattern |
| D-Bus | `sdbus-python` | `>=0.14.2,<1` | Active upstream, C-backed (libsystemd), clean async, attaches to the running loop automatically |
| X11 | `python-xlib` + in-tree EWMH helper | `>=0.33` | `python-ewmh` is unmaintained since 2017 and missing from Fedora/openSUSE; a ~200-line helper against `python-xlib` covers what Perch needs |
| TOML (read) | stdlib `tomllib` | — | Stdlib since 3.11; fast, strict |
| TOML (write, comment-preserving) | `tomlkit` | `>=0.13,<1` | User-edited `config.toml` must preserve comments across Perch's own edits |
| Packaging | `hatchling` build backend | — | Standard, PEP 517 |

**Python floor: `>=3.12`.** Every distro shipping as default in April 2026 has 3.12+ (Debian 13 / Ubuntu 24.04 LTS / Fedora 43 / openSUSE Tumbleweed / Arch); 3.11's EOL is Oct 2027 but all 2026 default installs are already past it. 3.12 buys `PEP 695` generics (useful for the backend interface), better tracebacks, and lets us rely on stdlib `tomllib` without conditionals.

Everything else is in the Python stdlib.

**Explicitly NOT on the list:**

- **`QtAsyncio`** (PySide6 6.6+'s official asyncio integration) — still technical preview, lacks `asyncSlot`, incomplete. Perch stays on `qasync` for v1.
- **`xcffib`** — lower-latency XCB bindings, but ergonomically raw for an EWMH workload. Revisit only if `python-xlib` upstream breaks.
- **`dbus-next`**, **`python-ewmh`** — original Phase-1 picks, swapped in Phase 2; see `docs/11-roadmap.md`.

## Event loop bootstrap

**Canonical pattern (2026, verified against qasync 0.28 during M1):**

```python
# perch/__main__.py  (sketch)
import asyncio, sys
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

async def main() -> int:
    app = QApplication.instance()                # constructed by cli() below

    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)     # critical teardown handshake

    backend = await make_backend()               # async work happens in main()
    tray = PerchTray(backend); tray.show()
    await close_event.wait()

    await backend.stop()                         # release bus name, unload script
    return 0

def cli() -> int:
    # qasync >=0.28 requires QApplication to exist *before* QEventLoop is
    # instantiated: the factory asserts on QApplication.instance() inside
    # asyncio.run. Construct it here, in the sync CLI wrapper.
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app                                      # keep the C++ object alive
    return asyncio.run(main(), loop_factory=QEventLoop)

if __name__ == "__main__":
    sys.exit(cli())
```

Key constraints:

- `QApplication` is constructed **in the sync wrapper**, not inside `main()`. qasync 0.28's `QEventLoop.__init__` asserts `QApplication.instance() is not None` and runs *before* the coroutine does, so a `QApplication` constructed inside `main()` is too late. The `loop_factory=QEventLoop` form (3.11+) has replaced the older `with loop: loop.run_forever()` incantation.
- `app.aboutToQuit → asyncio.Event` is the handshake that keeps the qasync loop alive long enough for the last teardown coroutines to run. Without it, `loop.close()` happens while Perch is still awaiting bus-name release and spams teardown warnings.
- Sync Qt slots that need to call async backend methods use `@qasync.asyncSlot()` — *not* `asyncio.ensure_future`, which loses exception propagation.
- sdbus-python attaches to whatever loop is running at its first `await`; no explicit `set_event_loop` glue is needed. `sdbus.set_default_bus(await sdbus.sd_bus_open_user_async())` goes inside `main()`.

Teardown order (see `perch/core/shutdown.py`):

1. Flip the shutdown flag (UI stops dispatching intents).
2. Cancel named background tasks; `await asyncio.gather(..., return_exceptions=True)`.
3. `await backend.stop()` — unloads the KWin script and releases the D-Bus service name.
4. `QApplication.quit()` → triggers `aboutToQuit` → sets the close event → `main()` returns.

## Dependencies, deferred

These are *not* in v1 but the architecture is designed so they can be added without core changes:

- A CLI (`perch apply coding-layout`) — just another UI frontend talking to the same core.
- A D-Bus service interface (`org.milnet01.Perch`) — lets scripts and other desktop components trigger actions. Would live in the UI layer as a second frontend.
- A headless daemon mode — skip the tray icon, still run the core + backend. Useful for minimal tiling WMs.

## Things explicitly out of scope here

- The *content* of the config file lives in [02-state-format.md](02-state-format.md).
- The *shape* of the backend interface lives in [03-backend-interface.md](03-backend-interface.md).
- Specific UI widgets live in [08-ui.md](08-ui.md).

This doc is only about "what are the pieces, and how do they fit."
