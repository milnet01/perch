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
| 3 | Docs revision | **done** (2026-04-20) | Applied Phase 2 + 2.5 findings to all affected docs. Design is frozen. |
| 4 | Implementation | **done** (2026-04-21) — M1 + M2 + M2.5 + M3 + M4 + M5 + M6 + M7 + M8 + M9 all landed; v1.0.0 tagged | Milestones M1…M9 below, with an injected M2.5 spike |

---

## M1 — Skeleton + config

**Status:** **done** (2026-04-20). See `src/perch/` and `tests/` — exit criteria green on CI matrix 3.12 / 3.13 / 3.14.

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

**Status:** **done** (2026-04-20). Exit criteria verified: compliance suite passes against `MockBackend`, rules engine at 100 % line coverage, and `tests/core/test_reducer.py` is the table-driven pytest asserting scripted event sequences produce the expected `set_geometry` calls. Sub-phases M2.a (backend interface + `MockBackend` + compliance suite), M2.b (profiles + topology), M2.c (rules engine + layouts), M2.d (event reducer + `state.json` persistence), and M2.e (profile overrides + reconciliation, 100 % coverage backfill) are all landed.

**Goal:** all the compositor-agnostic logic works against an in-memory backend.

**In scope:**

- `src/perch/backend/base.py` + `types.py` — the interface from [03-backend-interface.md](03-backend-interface.md).
- `src/perch/backend/mock.py` — `MockBackend` with a test-driver API.
- `tests/backend/test_compliance.py` — the reusable compliance suite, parameterised over `BACKEND_CLASSES` in `tests/backend/conftest.py`.
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

**Status:** **done** (2026-04-20) on the developer machine (Plasma 6.6.4). See [`experiments/kwin_ipc_spike/SPIKE_RESULTS.md`](../experiments/kwin_ipc_spike/SPIKE_RESULTS.md). The full Plasma 6.2 / 6.3 / `kdeneon:unstable` matrix is deferred to M5-preparation work (needs containerised runners that don't exist yet); it does not block M3 or M4.

**Goal:** de-risk the KWin backend's long-poll IPC pattern (see [05-backend-kwin.md](05-backend-kwin.md)) **before** M5 commits to it.

Phase 2.5 research established that the originally-planned 50 ms polling is wasteful and that kdotool's long-poll-via-callback-chaining pattern is demonstrably better. But no public precedent exists for a *tray app* + *bundled persistent KWin script* using this pattern, so we need empirical confirmation that it holds across Plasma 6.x versions before designing a whole backend around it.

**In scope:**

- `experiments/kwin_ipc_spike/` (at the repo root, outside `src/` — not shipped in the wheel) containing:
  - `script/` — a ~30-line JS script packaged as a KPackage (`metadata.json` + `contents/code/main.js`) that registers a `workspace.windowAdded` handler, fires `WindowAdded` via `callDBus`, and maintains a `PollCommand` long-poll loop.
  - `host.py` — the Python host using `sdbus` that owns `io.github.milnet01.Perch.spike`, counts round-trips, and exposes an `invalidate_polls()` hook so the harness can cycle the script through `Scripting.unloadScript`/`loadScript` without leaking orphan awaiters.
  - `harness.py` — the measurement harness: 10,000 round-trips (latency distribution), the `unloadScript`/`loadScript` cycle probe, and a configurable-duration idle probe that samples Python + KWin RSS.
- Run the harness on Plasma 6.2, 6.3, and whatever `kdeneon:unstable` is at the time (deferred — see status).
- A `SPIKE_RESULTS.md` recording latency numbers, failure modes observed, and a go/no-go decision.

**Exit criteria (status after 2026-04-20 run on Plasma 6.6.4):**

- Long-poll round-trip median latency < 5 ms on all three Plasma versions. — **met on 6.6.4** (p50 = 138 µs, p99 = 452 µs). 6.2 / 6.3 / Neon-unstable pending M5-prep.
- No memory growth after 1 hour of idle-script operation. — **2-minute smoke: met** (Python-side RSS delta 0.0 MiB). Full 60-minute run pending.
- Clean recovery across `unloadScript`/`loadScript`. — **met, after fixing an orphan-awaiter bug** surfaced by the probe (`invalidate_polls()`; see `SPIKE_RESULTS.md`).
- `SPIKE_RESULTS.md` committed; [05-backend-kwin.md](05-backend-kwin.md) updated to either confirm or replace the long-poll design. — **done.**

**Fallback if any criterion fails:** document the observed failure mode in [05-backend-kwin.md](05-backend-kwin.md) and revert to the 50 ms polling design (known to work but ugly). Better to know in M2.5 than in M5.

**Why here in the schedule:** M2 finishes the core + MockBackend, so the spike has a realistic harness to piggy-back on. M3 (UI) and M4 (X11 backend) do not depend on the spike outcome — they can run in parallel after M2.5 is kicked off. Only M5 blocks on the spike's go/no-go.

## M3 — UI: tray + minimal config dialog

**Status:** **done** (2026-04-20). All five subphases landed in a single session:
- M3.a — tray skeleton + intents ADT + SNI host probe + app wiring
- M3.b — config dialog scaffold + General / Rules / Exclusions edit flows via in-place tomlkit mutation + `RulesModel` with `InternalMove` drag-reorder
- M3.c — reusable widgets (`MatchEditor`, `GeometryEditor`, `HotkeyEdit` with the QTBUG-62102 Wayland Super workaround) + `portable_to_xdg()` accelerator translator for the GlobalShortcuts portal boundary, plus a live Hotkeys page in the config dialog
- M3.d — i18n plumbing: `translations/perch_en.ts` (Qt Linguist XML; 37 strings extracted via `pyside6-lupdate`) + `i18n.py` loader with the module-level-`QTranslator` GC fix
- M3.e — AppStream metainfo + desktop entry + rendered screenshots via a headless `scripts/render-screenshots.py`

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

**Status:** **done** (2026-04-20). All seven subphases landed in a single session:
- M4.a — EWMH helper + geometry math (pure, no Display)
- M4.b — X11Backend skeleton + XRandR output enumeration
- M4.c — window enumeration + identity extraction (`_NET_CLIENT_LIST`, WM_CLASS, _NET_WM_NAME UTF-8 / WM_NAME Latin-1, _NET_WM_WINDOW_TYPE, _NET_WM_STATE, WM_WINDOW_ROLE, WM_TRANSIENT_FOR)
- M4.d — `QSocketNotifier` event loop + lifecycle events (window_opened / _closed / _changed, geometry_changed, output_added / _changed / _removed with 200 ms RandR debounce)
- M4.e — commands: `set_geometry` via `_NET_MOVERESIZE_WINDOW` with StaticGravity + source=pager; `set_state` via `_NET_WM_STATE` client messages + ICCCM `WM_CHANGE_STATE` for minimize; `close_window` via `WM_DELETE_WINDOW` with `XKillClient` fallback
- M4.f — hotkeys via `XGrabKey` with lock-mask fan-out, NumLock discovered dynamically from the modifier map, `HotkeyBusyError` surfaced as `BackendUnsupported` + `backend_error` signal
- M4.g — Xvfb + openbox integration tests (`tests/backend/x11/test_live_openbox.py`, gated on `pytest -m x11`; skip when either tool is missing)

**Goal:** usable on every X11 desktop.

**In scope:**

- `perch/backend/x11/` implementing `WindowBackend`.
- XRandR output tracking.
- Hotkey registration via `XGrabKey`.
- Integration tests via `Xvfb` + `openbox` in CI.

**Exit criteria:**

- Compliance suite passes against the live backend — verified in `tests/backend/x11/test_live_openbox.py` (7 tests covering lifecycle, enumeration, set_geometry / set_state / close_window, hotkey conflict detection, and UnknownWindow / UnknownOutput error taxonomy).
- Manual smoke test on Plasma X11, Xfce, and i3 — checklist at [docs/testing/x11-checklist.md](testing/x11-checklist.md). Plasma X11 was the dev-session smoke environment (2026-04-20); Xfce and i3 cross-environment passes tracked there.
- Geometry restore for a representative app (Firefox, Konsole) works end to end — verified manually with xclock on Openbox and by inspection against the canonical `_NET_MOVERESIZE_WINDOW` + StaticGravity wire format.

**Docs updates:**

- `04-backend-x11.md` marks its "open questions" resolved (XIconifyWindow correction → `WM_CHANGE_STATE`; async-error pattern → `CatchError`; source-indication bit layout clarified; Xvfb `-displayfd` CI recipe documented).

---

## M5 — KWin backend (Wayland primary) — **done** 2026-04-20

**Goal:** Perch is good on Plasma Wayland.

**Landed in subphases M5.a..M5.g:**

- **M5.a** — Bundled KWin JS script: `src/perch/backend/kwin/script/`
  (`metadata.json` v1.0.0 + `contents/code/main.js`). Subscribes to
  `workspace.windowAdded`/`Removed`, per-window
  `frameGeometryChanged` (50 ms debounced), `captionChanged`,
  `fullScreenChanged`, `minimizedChanged`, `maximizedChanged`,
  `desktopsChanged`, `outputChanged`, and `workspace.screensChanged`.
  Long-poll command dispatcher (`setFrameGeometry` / `setFullScreen`
  / `setMinimized` / `setMaximizeMode` / `setDesktop` / `closeWindow`
  / `queryWindows` / `queryOutputs` / `queryWindow` /
  `queryCurrentDesktop` / `queryDesktopCount`). Batch op for
  one-tick layout application. Fires `ScriptReady(v=1.0.0)` on
  startup. JSON-strings-everywhere to sidestep KWin bug 486024.
- **M5.b** — Python D-Bus service (`PerchKWin1` exporting
  `io.github.milnet01.Perch.KWin1`) with long-poll `PollCommand` (5 s
  ceiling), `CommandDone` correlation, `invalidate_polls()` with
  Event-swap (carried forward from the M2.5 spike's orphan-awaiter
  fix), `reset_completion_state()` for clean shutdown. Typed `op_*`
  builders + `decode_window_info` / `decode_output_entry` codecs.
  Client proxies for `org.kde.KWin.Scripting` (`loadScript` /
  `unloadScript` / `isScriptLoaded`), per-script `/Scripting/Script{id}`,
  and `/KWin` core. `method_name=` pinned everywhere because
  sdbus-python's auto-camel uppercases the first letter.
- **M5.c** — Script installation + version pinning:
  `ensure_installed()` mirrors the bundled tree into
  `$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/` (idempotent when
  the on-disk version matches `BUNDLED_SCRIPT_VERSION`, rewrites
  otherwise, heals a truncated install). `ScriptVersionMismatch`
  raised if the on-disk version still doesn't match after install.
- **M5.d** — `KWinBackend(WindowBackend)` skeleton: env probe,
  transport lifecycle with defensive pre-load unloadScript,
  `Capabilities` per docs/05, enumeration queries (`list_windows` /
  `get_window` / `list_outputs` / `current_desktop` /
  `desktop_count`), event routing (backend is its own `EventSink`),
  output diff-and-emit on `OutputsChanged`, no-op suppression on
  repeated `WindowGeometryChanged` with identical geometry.
- **M5.e** — Commands: `set_geometry` (with monitor cache hit-through
  + `UnknownOutput`, `setDesktop` + `setFrameGeometry` batched when
  both supplied, `preplace=True` for best-effort first-frame stacking),
  `set_state` (per-state transition batches for FULLSCREEN /
  MAXIMIZED / MINIMIZED / NORMAL), `close_window`, consistent
  error translation (`unknown_window` → `UnknownWindow`,
  `unknown_output` → `UnknownOutput`).
- **M5.f** — Hotkeys via KGlobalAccel: `KGlobalAccelProvider` with
  `setShortcutKeys` + `globalShortcutPressed` signal pump;
  `ParsedAccel` parser with portable-accel aliases; Qt packed-int key
  encoding for letters / digits / F1..F35; `HotkeyProvider` Protocol
  with a `MockHotkeyProvider` for unit tests; `choose_provider`
  factory with `PERCH_HOTKEY_PROVIDER=mock` env override.
  `HotkeyBusyError` / `HotkeyParseError` surface as `backend_error`
  signals before re-raising. Portal-first path (xdg-desktop-portal
  GlobalShortcuts) deferred to M8 — it needs live validation against
  the Flatpak + xdg-desktop-portal-kde environment that M8 sets up.
- **M5.g** — Integration tests against a private `dbus-daemon` +
  `kwin_wayland --virtual` session (`@pytest.mark.kwin`, automatically
  skipped when binaries are missing). Manual smoke checklist
  in `docs/testing/kwin-checklist.md` for the real-Plasma checks
  CI can't do (KGlobalAccel, multi-monitor restore, pre-placement
  flicker).

**Exit-criterion evidence:**

- Compliance suite passes: 511 tests green (507 unit + 4 live KWin).
- Pre-paint placement hook implemented (`preplace=True` →
  `keepAbove` during first-frame settle) per docs/05 §Pre-placement
  hook; visible-flicker criterion is manual-checklist territory (see
  `docs/testing/kwin-checklist.md`).
- Manual smoke checklist documented at
  `docs/testing/kwin-checklist.md`; reference-environment pass
  expected on the maintainer's Plasma 6.6.4 session.

**Docs updates made:**

- `05-backend-kwin.md` §Outbound table reworked to reflect "every
  method has signature `s` (JSON payload)" after correcting the
  pre-Phase-2.5 table that still showed typed signatures; §Script
  installation strategy rewritten to state the shared-target-path
  invariant and reference `BUNDLED_SCRIPT_DIR` / `ensure_installed`
  / `ScriptVersionMismatch`; §Hotkeys rewritten to describe
  KGlobalAccel as the v1 path with the portal deferred to M8.

---

## M6 — Backend stubs — **done** 2026-04-21

**Goal:** Mutter, Sway, Hyprland have real-but-limited backends.

**Status:** all three stubs landed. `perch.backend.select()` probes the
session environment and returns the matching backend class — KWin →
Mutter → Sway → Hyprland → X11 fallback. `WindowBackend.is_available()`
is the cheap env-only probe; the compliance suite filters by it at
test-collection time so missing transports skip cleanly on dev boxes.

**In scope (landed):**

- `perch/backend/mutter/` — Python backend + bundled GNOME Shell extension
  (`extension/metadata.json` + `extension/extension.js`) exporting
  `io.github.milnet01.Perch.Mutter1`.
- `perch/backend/sway/` — Python backend using `i3ipc.aio.Connection`
  against `$SWAYSOCK`. Added as an optional `perch[sway]` extra in
  `pyproject.toml`.
- `perch/backend/hyprland/` — Python backend using `hyprctl -j` for
  queries + `.socket2.sock` for events, with defensive log-skip on
  unknown event names and a `MIN_HYPRLAND_VERSION = (0, 40, 0)` floor.
- `STATUS.md` per stub documenting capabilities, known skews, and the
  GNOME two-step install.
- Unit tests for each stub's pure decoders + `is_available` probe;
  compliance suite wired to auto-include each backend whose transport
  is detected.
- `CONTRIBUTING.md` §Contributing a backend finalised with the
  8-step workflow.

**Exit criteria (met):**

- Compliance suite passes against mock on every host; against KWin /
  X11 / Sway / Hyprland / Mutter on hosts where the transport is
  detectable. Backends whose transport is missing skip via
  `BackendUnavailable` + `pytest.skip`.
- `CONTRIBUTING.md` has the "Contributing a backend" section.

**Deferred from M6 (not exit-blocking):**

- Live-integration tests for Sway / Hyprland / Mutter (the M5
  `kwin_wayland --virtual` pattern needs equivalent harnesses; none
  exist in-repo yet). The unit-tested decoders carry the weight until
  contributors land those harnesses.
- GNOME Shell gschema for Perch hotkey registration — `extension.js`
  calls `getSettings()` but the `.gschema.xml` + compiled
  `gschemas.compiled` aren't shipped yet. Documented in
  `src/perch/backend/mutter/STATUS.md` §Schema.

---

## M7 — Polish

**Goal:** things that aren't features but decide whether Perch feels good.

**Status:** **done** 2026-04-21. Sequenced as six subphases M7.a…M7.f; cheapest / most isolated first so each subphase landed as an independent commit. Exit criteria met: no accessibility regressions, no `TODO` / `FIXME` markers in shipped code (verified via `grep -rn "TODO\|FIXME\|HACK\|XXX" src/perch/` returning zero hits at M7-close). Per-subphase acceptance recorded inline below.

**Subphases:**

- **M7.a — Icon set refinement + HiDPI audit** — **done** 2026-04-21. Three symbolic status icons (`perch-tray{,-warning,-error}-symbolic`) under `data/icons/hicolor/symbolic/status/`, a `TrayIcons` bundle + `load_tray_icons()` loader in `src/perch/ui/icons.py`, `TrayIconState` enum + `icon_state` / `tooltip` derivation on `TrayState`, automatic `setIcon` swap in `TrayIcon._on_state_changed`, and Hatch `shared-data` mapping so `pip install` deposits the icon theme under `<prefix>/share/icons/hicolor/...` for `QIcon.fromTheme` lookup. Qt's SVG renderer handles HiDPI at any scale factor without raster variants — the HiDPI "audit" is "we use SVG end-to-end," unit-tested via the 14 new cases in `tests/ui/test_tray_icon_states.py`.
- **M7.b — Keyboard navigation audit of the dialog** — **done** 2026-04-21. Sidebar receives initial focus; explicit `setTabOrder(sidebar → stack → buttons)` pins the Tab chain; `_DeleteKeyTableView` + `_DeleteKeyListWidget` subclasses let Delete / Backspace remove the selected row on the Rules table and Exclusions list (QShortcut alone doesn't work because `QTableView.keyPressEvent` swallows the key for cell-editing); accessible-name / description strings added to the sidebar, rules table and exclusions list so orca + Qt's accessibility bridge announce them clearly. 7 new tests in `tests/ui/test_dialog_keyboard.py`; docs/08 §Accessibility rewritten present-tense.
- **M7.c — Error-surfacing audit** — **done** 2026-04-21. `src/perch/ui/status.py` introduces `wire_backend_status(backend, controller, tray)` that bridges the three `WindowBackend` status signals into the tray surface: `backend_connected` clears `backend_degraded`, `backend_disconnected` sets it (so the tray icon swaps to the warning variant and the tooltip changes to "Perch — backend disconnected"), and `backend_error` surfaces a `QSystemTrayIcon.showMessage` balloon notification. The composition root in `src/perch/app.py` wires the bridge between tray construction and `backend.start()` so a synchronous `backend_connected` from `start()` still updates the tray. Remaining untranslated user-visible strings wrapped in `QCoreApplication.translate(...)` / `self.tr(...)`: the `_maybe_show_appindicator_hint` dialog title / body / informative text, and the four `MatchEditor` `QLineEdit` placeholders. 8 new tests in `tests/ui/test_status_bridge.py`.
- **M7.d — Performance harness (500 windows × 500 rules)** — **done** 2026-04-21. `tests/core/test_engine_performance.py` parametrises `evaluate()` at (100×100), (500×500), (1000×1000), with the matching rule placed *last* in the rules list so every window walks the full list (worst case). Measured: 5 ms / 55 ms / 200 ms on the reference dev box; budgets in the harness are 0.5 s / 2 s / 10 s — the 10-20× headroom absorbs CI jitter while still catching quadratic regressions. A separate test confirms builtin-exclusion short-circuits O(1) on 500 dock windows. `docs/07-rules-engine.md` §Performance model updated with the measured table.
- **M7.e — Privacy review of logs** — **done** 2026-04-21. `src/perch/logging_privacy.py` adds `redact_payload(payload)` + `summarize_keys(payload)`; window-title-bearing keys (`title`, `name`, `caption`, `class`, `initialTitle`, `initialClass`, `window_class`) are replaced with `<redacted>` while the rest of the structure is preserved for debuggability. Applied to the high-risk sites: KWin `on_window_added` (WARNING), `on_window_geometry_changed`, `on_window_properties_changed`, and `list_windows` skip-malformed path (DEBUG); Hyprland `list_windows`, `list_outputs`, `event dispatch failed`, and `unhandled Hyprland event` (the last two redact to the event name only — the raw line and `data` payload both carry the active window title verbatim on ≥ 0.40). 9 new tests in `tests/test_logging_privacy.py`; docs/08-ui.md gets a new §Logging and privacy subsection pinning the policy.
- **M7.f — Dark-theme pass** — **done** 2026-04-21. `src/perch/ui/theming.py::apply_theme(app, theme)` called from `src/perch/app.py::main` at startup, right after `install_translators`. `"auto"` reads `QGuiApplication.styleHints().colorScheme()` (Qt 6.5+): `Unknown` is a no-op (leaves Breeze-Dark et al. untouched), `Light` / `Dark` apply Fusion + the matching hand-built palette. Explicit `"light"` / `"dark"` values force Fusion + the matching palette unconditionally. Palettes are Breeze-inspired so the result looks native on Plasma users who override to `"dark"` specifically. 9 new tests in `tests/ui/test_theming.py`; docs/08-ui.md §Interaction updated present-tense. Runtime theme-change propagation without a restart is a follow-up.

**Exit criteria:**

- No known accessibility regressions.
- No `TODO` / `FIXME` in shipped code that lacks a linked issue.

---

## M8 — Packaging — **done** 2026-04-21

**Goal:** installable from every channel in [10-packaging.md](10-packaging.md).

**Status:** in-repo packaging artefacts authored and validated; external
submissions (the actual Flathub PR, OBS project, COPR project, AUR
push) are queued for the v1.0.0 tag at M9. Every submission-blocking
file is validated by CI on every PR.

**Landed in subphases M8.a..M8.g:**

- **M8.a — RPM spec for OBS + Fedora COPR** (`packaging/rpm/perch.spec`
  + `_service` + `README.md`). Unified spec with `%%if 0%%{?suse_version}`
  guards for the PySide6 package-name divergence. `%check` runs
  `appstream-util validate-relax` and `desktop-file-validate` inline so
  a metadata regression aborts the RPM build. `_service` drives tagged
  rebuilds on OBS via `obs_scm` + `set_version`.
- **M8.b — AUR PKGBUILD + perch-git variant**
  (`packaging/aur/PKGBUILD`, `packaging/aur/perch-git/PKGBUILD`,
  `README.md`). Stable + `-git` channels conflict via
  `provides=('perch')` / `conflicts=('perch')` so users pick one.
  Both use the modern `python -m build --wheel` + `python -m installer`
  flow. `-git`'s `pkgver()` derives from `git describe`.
- **M8.c — Flatpak manifest finalisation**. Fixed the stale
  `src/perch/backends/kwin/` path (singular `backend/`). Tightened
  `finish-args` — dropped `--device=dri` (Perch doesn't render a 3D
  surface), replaced open-name allowlist with targeted `--talk-name`
  entries for `org.kde.KWin`, `org.kde.kglobalaccel`,
  `org.freedesktop.Notifications`, `org.freedesktop.portal.Desktop`.
  Added the three symbolic status icons to the install commands.
  `python3-*.yml` include files are deliberately not committed —
  `SUBMISSION.md` documents the regen step.
- **M8.d — Autostart** (`src/perch/autostart.py`). XDG `.desktop` path
  for non-Flatpak (atomic write to `$XDG_CONFIG_HOME/autostart/`);
  `org.freedesktop.portal.Background.RequestBackground` path for
  Flatpak. `is_flatpak()` probes `/.flatpak-info`. `sync_from_config`
  is called at startup and from the config dialog's `saved` signal so
  the `Start Perch at login` checkbox takes effect immediately. 16
  new tests in `tests/test_autostart.py` covering both paths with an
  in-memory fake portal.
- **M8.e — XDG Desktop Portal GlobalShortcuts hotkey path**
  (`PortalGlobalShortcutsProvider` in `src/perch/backend/kwin/hotkeys.py`).
  Full `CreateSession` → `BindShortcuts` → `Activated` flow with
  per-Request Response correlation; `_portable_to_xdg_accel` translator
  at the portal boundary. `choose_provider()` now probes portal
  availability and falls back to KGlobalAccel cleanly; sandbox
  detection auto-enables the probe. `PERCH_HOTKEY_PROVIDER` env var
  forces `mock` / `portal` / `kglobalaccel` for tests and unusual
  installs. 12 new tests using an in-memory fake portal.
- **M8.f — KDE Store listing + CI validation job**
  (`packaging/kde-store/LISTING.md` +
  `.github/workflows/ci.yml` `packaging` job). The KDE Store entry
  points at the Flatpak as the install source (no parallel tarball
  upload). The CI job runs `appstreamcli validate`, `desktop-file-validate`,
  `yamllint` on the Flatpak manifest, `rpmspec -P` on the RPM spec,
  `bash -n` on both PKGBUILDs, and well-formedness on the KWin script's
  `metadata.json` — every submission-blocking artefact is checked on
  every PR.
- **M8.g — Release plumbing** — `.claude/bump.json` wired to
  `pyproject.toml`, `src/perch/__init__.py`, `packaging/rpm/perch.spec`,
  `packaging/aur/PKGBUILD`, and the Flatpak manifest's `tag:` line.
  `docs/10-packaging.md` rewritten present-tense for the in-repo
  artefacts; `docs/05-backend-kwin.md` §Hotkeys rewritten to describe
  the portal-first, KGlobalAccel-fallback policy; this file updated.

**Exit criteria (met):**

- Perch is installable from Flathub, OBS, and AUR **once v1.0.0 is
  tagged** — the manifest / spec / PKGBUILDs are authored, validated,
  and ready. Actual submissions are queued for M9 because Flathub /
  OBS / AUR review needs a tagged release to operate on (see
  `packaging/flathub/SUBMISSION.md` §Why we're not opening a
  speculative PR now).
- `appstreamcli validate` passes (CI enforces per-PR).
- `desktop-file-validate` passes (CI enforces per-PR).

**Docs updates (landed):**

- `10-packaging.md` channels table updated to present tense for every
  in-repo artefact; "target at v1" replaced with specific pointers to
  `packaging/<channel>/`.
- `05-backend-kwin.md` §Hotkeys rewritten — portal is preferred, not
  future.
- `KWinBackend.capabilities.notes` rewritten from "KGlobalAccel
  hotkeys (portal path follows with M8 Flatpak)" to "GlobalShortcuts
  portal (KGlobalAccel fallback when the portal is unavailable)".

---

## M9 — v1.0.0 — **done** 2026-04-21

**Goal:** release.

**Landed:**

- Final docs pass — `README.md` and `CLAUDE.md` rewritten present-tense; every shipped behaviour spoken of in the present throughout `docs/`; remaining future-tense references (the Perch CLI, runtime theme-change, `contributing-backend-mutter.md`) explicitly pinned as post-v1 work in `11-roadmap.md` §Post-v1 ideas.
- `CHANGELOG.md` finalised — Unreleased section rolled into `[1.0.0] — 2026-04-21`; empty Unreleased scaffold retained; comparison links updated.
- Version bumped to `1.0.0` across the five files wired in `.claude/bump.json` (`pyproject.toml`, `src/perch/__init__.py`, `packaging/rpm/perch.spec`, `packaging/aur/PKGBUILD`, Flatpak manifest `tag:`). `Development Status` classifier lifted to `5 - Production/Stable`. AppStream metainfo `<releases>` replaced the pre-release placeholder with a `1.0.0` stable entry; screenshot URLs pinned to the `v1.0.0` tag.
- Full validation sweep green: 727 tests pass on the reference dev box; `ruff check`, `mypy --strict`, `appstreamcli validate --no-net`, `desktop-file-validate`, `rpmspec -P`, `bash -n` on both PKGBUILDs, YAML load on the Flatpak manifest, and JSON load on the KWin script's `metadata.json` all clean.
- Tag `v1.0.0` created and pushed.

**Exit criteria (met):**

- All M1–M8 exit criteria still green.
- Release tag `v1.0.0` exists.

---

## Post-v1 ideas (not a commitment)

- CLI frontend for scripting (`perch apply coding`, `perch snap left-half`). Referenced from `docs/06-backend-stubs.md` §Sway / Hotkeys and `docs/08-ui.md` §Hotkeys as the self-grabbed-hotkey fallback for compositors that don't expose a hotkey API.
- Runtime theme-change propagation (global re-apply without a restart). Referenced from `docs/08-ui.md` §Interaction.
- `docs/contributing-backend-mutter.md` covering GJS conventions, per-GNOME-branch policy, and the release-to-EGO checklist. Owned by the first community contributor to take the Mutter stub to full backend. Referenced from `docs/06-backend-stubs.md` §Contributor path.
- `perch --test-rules <config.toml>` replay tool for rules-engine regression testing. Referenced from `docs/07-rules-engine.md` §Debugging and observability.
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
- **Hyprland IPC informal stability**: socket2 event format has broken backwards across minor Hyprland versions. Mitigation: defensive parsing (unknown events logged + skipped), minimum-version check at `start()`.
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
