# 11 — Roadmap

Phased plan, from "repo bootstrap" to "v1.0.0 shipped." This is the **source of truth** for milestone ordering; everything else references it.

## Ground rules

1. **Docs-first, always.** Any behaviour change lands in `docs/` before or in the same PR as the code. No exceptions, not even for one-liners.
2. **No documentation debt.** Every PR that changes behaviour updates `docs/`. Stale docs are a bug, not a paperwork issue — fixing them has the same priority as fixing a functional bug. `CONTRIBUTING.md` encodes this as a review checklist item.
3. **Milestones are discrete.** A milestone is "done" only when its exit criteria pass in CI. No partial rollovers.
4. **Stubs are real.** A backend marked "stub" still implements `WindowBackend` faithfully and passes the compliance suite. It just declares narrower capabilities.
5. **No workarounds without documentation.** Any `# WORKAROUND:` comment must cite the underlying issue (a bug URL, a compositor quirk, a protocol gap). Silent workarounds are tech debt.

## Phase map

| Phase | Name | Status | Contents |
|---|---|---|---|
| 0 | Repo bootstrap | **done** | LICENSE, README, CoC, CONTRIBUTING, `.github/`, `pyproject.toml` |
| 1 | Design docs | **done** (2026-04-20) | `docs/00` … `docs/11` (this file is the last one) |
| 2 | Review + research | **done** (2026-04-20) | Validated design against current state of KWin scripting, GNOME extensions, Wayland protocols, Python toolchain. See Phase 2 log at the bottom of this file. |
| 2.5 | Implementation-readiness research | **done** (2026-04-20) | Concrete 2026 toolchain picks; qasync/sdbus bootstrap pattern; KWin IPC long-poll pattern; X11 pragmatics. Log at the bottom of this file. |
| 3 | Docs revision | **done** (2026-04-20) | Applied Phase 2 + 2.5 findings to all affected docs. Design is frozen pending M1 start. |
| 4 | Implementation | in progress (M1 underway from 2026-04-20) | Milestones M1…M9 below, with an injected M2.5 spike |

---

## M1 — Skeleton + config

**Status:** **in progress** (started 2026-04-20). See `src/perch/` and `tests/`.

**Goal:** a runnable Perch binary that parses config, logs what it sees, and quits cleanly. No backend yet.

**In scope:**

- `perch/` package with `__main__.py` entrypoint using the canonical `asyncio.run(main(), loop_factory=QEventLoop)` pattern (see [01-architecture.md](01-architecture.md) §Event loop bootstrap).
- `perch/config/` — TOML load via stdlib `tomllib`, save via `tomlkit`, schema validation, atomic writes, migration registry (empty but wired).
- `perch/core/state.py` — in-memory state (no persistence yet).
- Logging wired to `$XDG_STATE_HOME/perch/perch.log` with `RotatingFileHandler` (1 MB × 3 files) and a Qt→Python bridge via `qInstallMessageHandler`.
- `pyproject.toml` dependencies pinned (`PySide6>=6.8,<7`, `qasync>=0.28,<1`, `sdbus>=0.14.2,<1`, `python-xlib>=0.33`, `tomlkit>=0.13,<1`) and `pip install -e ".[dev]"` works.
- Test harness: `pytest` + `pytest-qt` + `pytest-xvfb` + `pytest-asyncio` (imported; tomlkit round-trip fixture live from day one).
- CI: GitHub Actions matrix Ubuntu 24.04 × Python 3.12/3.13/3.14, install PySide6 from PyPI, run `ruff`, `mypy`, `pytest`.

**Exit criteria:**

- `perch --version` prints the version.
- `perch` with no config creates default `~/.config/perch/config.toml` and exits cleanly.
- `perch` with a malformed config refuses to start, logs the specific problem, exits non-zero.
- `pytest` passes in CI with ≥ 80% coverage of `perch/config/`.

**Docs updates at M1:**

- `02-state-format.md` cross-references the actual schema module — **done**.
- A new `docs/contributing-dev-setup.md` describing the dev workflow — **done**.

---

## M2 — Mock backend + rules engine + core

**Goal:** all the compositor-agnostic logic works against an in-memory backend.

**In scope:**

- `perch/backend/base.py` — the interface from [03-backend-interface.md](03-backend-interface.md).
- `perch/backend/mock.py` — `MockBackend` with a test-driver API.
- `perch/backend/tests/compliance.py` — the compliance suite.
- `perch/core/rules.py` — rules engine per [07-rules-engine.md](07-rules-engine.md).
- `perch/core/layouts.py` — layout apply logic.
- `perch/core/profiles.py` — topology-key computation and profile activation.
- `perch/core/reducer.py` — the event reducer that glues backend events + rules + state together.
- `state.json` persistence (atomic, debounced).

**Exit criteria:**

- Compliance suite passes against `MockBackend`.
- Rules engine has 100% line coverage.
- Feeding a scripted event sequence into `MockBackend` produces the expected `set_geometry` calls — verified by a table-driven pytest.

**Docs updates:**

- `07-rules-engine.md` adds any semantics discovered during implementation.
- `09-layouts-profiles.md` adds the override-merge rules' exact behaviour as implemented.

---

## M2.5 — Spike: KWin IPC validation

**Goal:** de-risk the KWin backend's long-poll IPC pattern (see [05-backend-kwin.md](05-backend-kwin.md)) **before** M5 commits to it.

Phase 2.5 research established that the originally-planned 50 ms polling is wasteful and that kdotool's long-poll-via-callback-chaining pattern is demonstrably better. But no public precedent exists for a *tray app* + *bundled persistent KWin script* using this pattern, so we need empirical confirmation that it holds across Plasma 6.x versions before designing a whole backend around it.

**In scope:**

- `perch/experiments/kwin_ipc_spike/` containing:
  - A 30-ish-line JS script that registers a `workspace.windowAdded` handler, fires `WindowAdded` via `callDBus`, and maintains a `PollCommand` long-poll loop.
  - A 60-ish-line Python host using `sdbus` that owns `io.github.milnet01.Perch.spike`, counts round-trips, and cycles the script through `Scripting.unloadScript` / `loadScript`.
  - A measurement harness: 10,000 round-trips; latency distribution; behaviour when the Python side disconnects mid-call; memory growth of the callback chain over an hour.
- Run the harness on Plasma 6.2, 6.3, and whatever `kdeneon:unstable` is at the time.
- A `SPIKE_RESULTS.md` recording latency numbers, failure modes observed, and a go/no-go decision.

**Exit criteria:**

- Long-poll round-trip median latency < 5 ms on all three Plasma versions.
- No memory growth after 1 hour of idle-script operation.
- Clean recovery across `unloadScript`/`loadScript`.
- `SPIKE_RESULTS.md` committed; [05-backend-kwin.md](05-backend-kwin.md) updated to either confirm or replace the long-poll design.

**Fallback if any criterion fails:** document the observed failure mode in [05-backend-kwin.md](05-backend-kwin.md) and revert to the 50 ms polling design (known to work but ugly). Better to know in M2.5 than in M5.

**Why here in the schedule:** M2 finishes the core + MockBackend, so the spike has a realistic harness to piggy-back on. M3 (UI) and M4 (X11 backend) do not depend on the spike outcome — they can run in parallel after M2.5 is kicked off. Only M5 blocks on the spike's go/no-go.

## M3 — UI: tray + minimal config dialog

**Goal:** Perch has a face. Tray icon, menu, basic config dialog that wires to the core.

**In scope:**

- `perch/ui/tray.py` — `QSystemTrayIcon`, menu per [08-ui.md](08-ui.md).
- `perch/ui/dialog.py` — config dialog scaffold with Windows / Rules / Layouts / Profiles sections.
- `perch/ui/widgets/` — match editor, geometry editor, key-capture widget.
- `qasync` integration so one event loop drives Qt + asyncio.
- i18n plumbing (tr()-wrapped strings, `po/` directory, build step for `.qm`).

**Exit criteria:**

- Tray icon appears on Plasma X11, Plasma Wayland, and GNOME.
- Menu actions produce the right intents on the core (verified against `MockBackend`).
- Config dialog opens, edits rules, and saves without loss.
- `pytest-qt` covers the major dialog flows.

**Docs updates:**

- Screenshots added to `docs/screenshots/` and linked from `08-ui.md`.
- AppStream metainfo gets its first screenshot references.

---

## M4 — X11 backend

**Goal:** usable on every X11 desktop.

**In scope:**

- `perch/backends/x11/` implementing `WindowBackend`.
- XRandR output tracking.
- Hotkey registration via `XGrabKey`.
- Integration tests via `Xvfb` + `openbox` in CI.

**Exit criteria:**

- Compliance suite passes.
- Manual smoke test on Plasma X11, Xfce, and i3 (documented in `docs/testing/x11-checklist.md`).
- Geometry restore for a representative app (Firefox, Konsole) works end to end.

**Docs updates:**

- `04-backend-x11.md` marks its "open questions" resolved or moved to follow-up issues.

---

## M5 — KWin backend (Wayland primary)

**Goal:** Perch is good on Plasma Wayland.

**In scope:**

- `perch/backends/kwin/` — Python half.
- `perch/backends/kwin/script/` — bundled KWin JS script.
- Script versioning and load/unload lifecycle.
- KGlobalAccel integration for hotkeys.
- Integration test: headless KWin in CI (`kwin_wayland --virtual`).

**Exit criteria:**

- Compliance suite passes.
- Pre-paint placement works for a representative app (no visible flash on restore).
- Manual smoke test on Plasma Wayland 6 documented in `docs/testing/kwin-checklist.md`.

**Docs updates:**

- `05-backend-kwin.md` confirms the script's final D-Bus surface matches the doc.

---

## M6 — Backend stubs

**Goal:** Mutter, Sway, Hyprland have real-but-limited backends.

**In scope:**

- `perch/backends/mutter/` — Python backend + GNOME Shell extension scaffolding.
- `perch/backends/sway/` — Python backend using `swaymsg`.
- `perch/backends/hyprland/` — Python backend using `hyprctl` + socket2.
- `STATUS.md` per stub.

**Exit criteria:**

- All three stubs pass the compliance suite with their declared capabilities.
- `CONTRIBUTING.md` has a "contributing a backend" section finalised.

**Docs updates:**

- `06-backend-stubs.md` stops being speculative where implementation has answered questions.

---

## M7 — Polish

**Goal:** things that aren't features but decide whether Perch feels good.

**In scope:**

- Icon set refinement, HiDPI audit.
- Keyboard navigation audit of the dialog.
- Error-surfacing audit (every expected failure has a user-visible message).
- Performance: rule evaluation under load (500 windows × 500 rules sanity check).
- Privacy review of logs.
- Dark-theme pass.

**Exit criteria:**

- No known accessibility regressions.
- No `TODO` / `FIXME` in shipped code that lacks a linked issue.

---

## M8 — Packaging

**Goal:** installable from every channel in [10-packaging.md](10-packaging.md).

**In scope:**

- Flatpak manifest submitted to Flathub.
- OBS package building for Tumbleweed.
- COPR configured for Fedora.
- AUR `PKGBUILD` published.
- KDE Store listing prepared.

**Exit criteria:**

- Perch installable from at least Flathub, OBS, and AUR.
- `appstream-util validate-relax` passes.
- `desktop-file-validate` passes.

**Docs updates:**

- `10-packaging.md` moves from "planned" tense to "current" tense for each channel that is live.

---

## M9 — v1.0.0

**Goal:** release.

**In scope:**

- Final docs pass — every "planned" / "will" rewritten as "does."
- CHANGELOG finalised.
- Tag + release.

**Exit criteria:**

- All M1–M8 exit criteria still green.
- Release tag `v1.0.0` exists with signed-off release notes.

---

## Post-v1 ideas (not a commitment)

- CLI frontend for scripting (`perch apply coding`, `perch snap left-half`).
- D-Bus service interface for external triggers.
- Headless daemon mode for minimal WMs.
- "Enforcement mode" per rule — pin a window, fight user drags.
- Topology-scoped last-seen ("remember this arrangement per topology automatically").
- GNOME Shell extension published to extensions.gnome.org.
- Full Plasma 5 support.
- Activity-scoped rules.

## Known risks (post Phase 2)

- **KWin scripting API stability** across Plasma point releases. *Confirmed risk*: 5→6 renamed `client*` → `window*` across the scripting API; minor 6.x releases occasionally add or rename signals without deprecation. Mitigation: pin the script and expected KWin version at each Perch release; smoke-test against each new Plasma point release.
- **Mutter extension API instability**: every GNOME major release breaks something (ESM in 45, removals in 48, etc.). Mitigation: ~3 parallel per-GNOME source branches of the extension; the stub status in [06-backend-stubs.md](06-backend-stubs.md) documents this cost honestly.
- **Hyprland IPC informal stability**: socket2 event format has broken backwards across minor Hyprland versions. Mitigation: defensive parsing (unknown events logged + skipped), minimum-version check at `connect()`.
- **Ubuntu 24.04 LTS PySide6 too old**: 6.4 vs. required 6.7. Mitigation: Flathub or pipx; DEB package built only for 24.10+ / Debian 13+ ([10-packaging.md](10-packaging.md)).
- **GNOME Wayland tray visibility** requires AppIndicator extension. Mitigation: detect SNI host absence at startup; surface an install prompt (see [08-ui.md](08-ui.md)).
- **Two-Firefox identity collision** — same `app_id`, same `title` patterns. Users have to add explicit title regexes, which is awkward. Worth a UX pass.

---

## Phase 2 research log

**Date:** 2026-04-20. Conducted in a single session, four parallel research topics.

### What was validated

1. **KWin `.kwinscript` loading via D-Bus** — still current on Plasma 6. Method name and KPackage format confirmed. `metadata.json` preferred over `metadata.desktop`.
2. **`workspace.sendClientToScreen`** — still current in Plasma 6 despite the broader `Client` → `Window` rename.
3. **`workspace.screens`** — still works; `org.kde.KWin.Management.screens` D-Bus also exists.
4. **`Meta.Window.move_resize_frame`** — present and stable in GNOME 48/49/50. No deprecation planned.
5. **GNOME extensions can register D-Bus services** — well-established pattern; precedents on EGO.
6. **i3ipc-python async variant** — stable on Python 3.11/3.12; no bitrot.
7. **Openbox for CI** — upstream dormant (last release 3.6.1, 2015) but universally packaged and still the de-facto EWMH reference WM. Keep using it.

### What broke, and what we changed

| Assumption | Broke how | Doc change |
|---|---|---|
| KWin JS script registers a D-Bus service `org.milnet01.Perch.KWin` | KWin's JS sandbox only exposes `callDBus` (outbound); no `QDBusConnection.registerService` reachable from JS | Inverted design in [05-backend-kwin.md](05-backend-kwin.md): Python owns `io.github.milnet01.Perch`, JS uses `callDBus` outbound |
| `workspace.clientAdded` / `clientList` | Renamed to `workspace.windowAdded` / `windowList` in Plasma 6 | Replaced every occurrence in [05-backend-kwin.md](05-backend-kwin.md) |
| Flatpak ships KWin script at `/app/share/perch/kwin/` and calls `loadScript` on it | KWin runs on the host and cannot see `/app/`; loading fails | [10-packaging.md](10-packaging.md): copy script to `$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/` on first run, load from there. Added `--filesystem=xdg-data/kwin/scripts:create` to manifest |
| Pre-paint placement is a solid KWin promise | Best-effort; flicker is uncommon but not absent | Added `can_preplace_windows` capability bit in [03-backend-interface.md](03-backend-interface.md); KWin sets true-with-caveat, others false |
| Pre-paint placement on Mutter | `window-created` on Mutter fires after Wayland has the initial buffer; `move_resize_frame` shortly after creation is racy regardless. Visible snap is the norm | [06-backend-stubs.md](06-backend-stubs.md): `can_preplace_windows = False`; documented as explicit capability gap |
| `dbus-next` is the async D-Bus pick | Upstream dormant since 2022; known asyncio-teardown bugs | Switched stack to `sdbus-python` ([CLAUDE.md](../CLAUDE.md), [01-architecture.md](01-architecture.md), [10-packaging.md](10-packaging.md)) |
| `python-ewmh` for X11 | Unmaintained since 2017; not packaged on Fedora/openSUSE | Switched to `python-xlib` direct + in-tree EWMH helper ([04-backend-x11.md](04-backend-x11.md)) |
| GNOME 45 is the minimum target | Current distros ship 48–50; 45 is effectively retired | Floor raised to **GNOME 48** in [06-backend-stubs.md](06-backend-stubs.md) |
| Flatpak installs the GNOME Shell extension | No portal exists for that | Documented two-step install in [06-backend-stubs.md](06-backend-stubs.md) and [10-packaging.md](10-packaging.md) |
| "Works across GNOME releases with one source branch" | Every GNOME major breaks something; Dash-to-Dock/Pop Shell maintain per-version branches | Extended the risks list; stub status reflects multi-branch cost |
| `QSystemTrayIcon` works everywhere | GNOME Wayland has no tray host without the AppIndicator extension | Added tray-host detection + install-prompt in [08-ui.md](08-ui.md) |
| Global hotkeys via direct KGlobalAccel | Works non-Flatpak on Plasma, but the supported path for sandboxed apps is the GlobalShortcuts portal | [05-backend-kwin.md](05-backend-kwin.md): portal-first, KGlobalAccel as fallback; `setShortcut` deprecated → `setShortcutKeys` |
| `_NET_MOVERESIZE_WINDOW` + StaticGravity is universally consistent | i3 ignores gravity for tiled windows; Openbox has a map-race without `_NET_FRAME_EXTENTS`; Plasma-X11 applies GTK shadow margins | Added "WM quirks" subsection in [04-backend-x11.md](04-backend-x11.md) |
| XRandR under XWayland reports real output names | Names are synthetic (`XWAYLAND0`, `XWAYLAND1`, …); fractional scale invisible | Documented in [04-backend-x11.md](04-backend-x11.md) |
| Hyprland IPC is as stable as Sway's | `.socket2.sock` event format has broken backwards across minor releases | [06-backend-stubs.md](06-backend-stubs.md): `hyprctl -j` + defensive event parsing + minimum-version pin |
| Ubuntu 24.04 LTS ships a usable PySide6 | Ships 6.4 (too old) | Documented Flathub/pipx workaround in [10-packaging.md](10-packaging.md); DEB built only for 24.10+ |

### What Phase 2 did *not* resolve

- **SELinux behaviour** when Flatpak writes into `$XDG_DATA_HOME/kwin/scripts/`. Low expected risk (user-owned dir, KWin reads as user), but unverified. Tracked as an M8 smoke-test on Fedora.
- **KWin 6.x minor-release API drift** cadence. No formal deprecation policy exists; we budget a "port tax" but can't predict its size. Mitigation is testing at each release, not upfront analysis.
- **Headless Plasma-6 in CI**: Phase 2.5 established the `dbus-run-session -- kwin_wayland --virtual` recipe works but is fragile on GHA runners. Resolved by scheduling KWin integration as a **nightly job**, not a per-PR gate.

---

## Phase 2.5 research log

**Date:** 2026-04-20 (same session as Phase 2; separated because it focused on implementation-readiness details needed before writing M1 code, versus the high-level design validation of Phase 2).

### What was established

**Python floor** → raised to `>=3.12`. Every April 2026 default distro install already has 3.12+ (Debian 13, Ubuntu 24.04 LTS, Fedora 43, openSUSE Tumbleweed, Arch). 3.11 EOLs Oct 2027 but no default install ships 3.11 anymore.

**Concrete pin table:**

| Dep | Pin | Source |
|---|---|---|
| PySide6 | `>=6.8,<7` | current LTS Qt 6.8 shipped Oct 2025 |
| qasync | `>=0.28,<1` | supports `asyncio.run(..., loop_factory=QEventLoop)` cleanly |
| sdbus (python-sdbus) | `>=0.14.2,<1` | Dec 2025 release, known-good with asyncio |
| python-xlib | `>=0.33` | low-activity but stable; no compelling 2026 replacement |
| tomlkit | `>=0.13,<1` | monthly 30M downloads, maintained; 1.0 will reshape API |
| ruff | `>=0.15,<0.16` | pre-1.0, pin minor |
| mypy | `>=1.20,<2` | |
| pytest | `>=8.4,<10` | 9 just landed; let range cover both |
| pytest-qt | `>=4.5,<5` | |
| pytest-asyncio | `>=1.3,<2` | |
| pytest-xvfb | `>=3` | preferred over `xvfb-run` wrappers |

**Bootstrap pattern (canonical 2026):** `asyncio.run(main(), loop_factory=QEventLoop)` — the older `with loop: loop.run_forever()` still works but is on the deprecation track. `aboutToQuit → asyncio.Event` is the critical teardown handshake (without it, `loop.close()` spams warnings). See [01-architecture.md](01-architecture.md) §Event loop bootstrap.

**sdbus + qasync**: attaches cleanly to whatever loop is running at first `await`. No explicit glue needed. `sdbus.set_default_bus(await sdbus.sd_bus_open_user_async())` is called once inside `main()`.

**`@qasync.asyncSlot()`** is the right decorator for sync-Qt→async bridges. `asyncio.ensure_future()` from a slot loses exception propagation.

**DO NOT use `QtAsyncio`** (PySide6 6.6+'s official asyncio integration). Still technical preview, no `asyncSlot`, incomplete. Stay on qasync.

### KWin IPC pattern — significant design revision

The Phase 1 design used **50 ms polling** from the JS script to `PollCommand()`. Phase 2.5 research found that's a footgun:

- Wastes wakeups (60 × 50 ms = 1,200 KWin JS invocations per minute, for zero benefit).
- Latency is always at least the polling interval.

The correct pattern, used in production by `kdotool` (jinliu/kdotool) and validated against Plasma 6.0–6.4, is **long-poll via callback chaining**:

1. Script calls `callDBus(..., "PollCommand", callback)`.
2. Python holds the reply until a command is queued, or up to a ~5 s heartbeat ceiling.
3. Callback fires, script executes the command, re-arms the long-poll.

Round-trip latency collapses to a single D-Bus round-trip (sub-millisecond). Wakeups go to zero when idle. Documented in the revised [05-backend-kwin.md](05-backend-kwin.md).

**New milestone: M2.5 (spike)** de-risks this pattern before M5 commits to it. See above.

### `callDBus` quirks confirmed

- Always async; never blocks.
- Reply arrives via the optional trailing callback argument.
- **Numeric-signature footgun (KWin bug 486024):** variadic args go through Qt's best-guess type coercion; JS numbers default to `double`, breaking `i`/`u` D-Bus signatures. Mitigation: all Perch ↔ script arguments are **JSON strings**, decoded on the Python side.

### Pre-paint placement

No hard guarantee on any platform. On KWin, writing `window.frameGeometry` synchronously inside `windowAdded` *usually* lands before the first frame, but XWayland clients and apps that call `xdg_surface.set_window_geometry` after mapping can still flicker. **De-facto mitigation**: temporarily set `window.keepAbove = true` during placement, then clear. Reduces perceived jump, doesn't eliminate it. Documented in [05-backend-kwin.md](05-backend-kwin.md). `can_preplace_windows = True` on KWin, `False` everywhere else.

### Headless KWin in CI

Command: `dbus-run-session -- kwin_wayland --virtual --width 1920 --height 1080 --exit-with-session <test-runner>`. Packages: `kwin-wayland` on Fedora/openSUSE, `kwin-wayland + kwin-wayland-backend-virtual` on Debian. Fragile on GHA (seat/seatd requirements, XDG_RUNTIME_DIR, upstream-vs-distro skew) → **nightly job, not per-PR gate**.

### X11 backend concrete patterns

- Drain loop: `while d.pending_events(): handle(d.next_event())` — one readable wakeup can cover multiple queued events.
- `d.flush()` after sending requests outside the drain loop; never `d.sync()` on the main thread.
- Subscribe `SubstructureNotifyMask | PropertyChangeMask` on root; per-window `PropertyChangeMask` on everything in `_NET_CLIENT_LIST`, always guarded with `BadWindow`/`BadMatch` handlers.
- `XGrabKey` lock-mask fan-out covering all combinations of LockMask and Mod2 (NumLock). Resolve Mod2 dynamically via `get_modifier_mapping()`. Surface `BadAccess` to the user as "hotkey unavailable."
- Electron/Chromium `WM_CLASS` late-set: still present in 2026. Retry on `PropertyNotify`, cap at 5 retries over ~2 s.
- `override_redirect=True` filter is unconditionally correct; OR doesn't flip mid-life.

### TOML library

- Read with stdlib `tomllib`.
- Write with `tomlkit>=0.13,<1`.
- **Known footgun**: deep inline-table rewrites can drop mid-table comments. M1 requires a round-trip fixture test; dropping user comments is an unacceptable trust violation.

### What Phase 2.5 did *not* resolve

- Whether Flatpak's `qasync + sdbus` combo works cleanly under the `org.kde.Platform` runtime (needs a smoke build on Flathub infra). Tracked as M8 work.
- Python 3.14 ABI stability for any C-extension deps (sdbus bundles libsystemd) on Fedora COPR / openSUSE OBS build roots. Tracked as M8 work.
- Whether `tomlkit` preserves comments in all Perch `config.toml` shapes — needs a concrete round-trip fixture in M1 to prove it empirically for our schema.
- Whether `kwin_wayland --virtual` in a Fedora container on a GHA runner boots reliably enough for nightly CI. Tracked under M5 preparation work.
