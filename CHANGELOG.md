# Changelog

All notable changes to Perch are documented here.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Sections under each release are populated on a best-effort basis — empty sections are omitted at release time.

## [Unreleased]

### Added

- **`scripts/install-gnome-extension.py` installs the bundled GNOME Shell extension** (PERC-0062)
  The dev path docs/06 §Flatpak has described all along, and the only
  consumer of the `BUNDLED_EXTENSION_DIR` and `EXTENSION_UUID` constants,
  which had none. It copies the extension into `$XDG_DATA_HOME`, refuses to
  replace an existing install without `--force`, and leaves enabling and
  the session restart to you.

- **state.json has a migration registry, like config.toml** (PERC-0059)
  docs/02 §Versioning and migration covers both files and only config.toml
  had one. A state document older than the running Perch is migrated in
  memory and written back at the current version; one that cannot be
  migrated leaves the store empty and read-only, so the file survives a
  Perch that cannot read it.

- **Layout entries skipped for a missing monitor are now reported** (PERC-0068)
  docs/09 §Apply semantics has always required it and the reducer only
  wrote a log line. Activating a layout that names a disconnected output
  now raises one tray notification listing every entry it skipped.

### Changed

- **An empty string in a match or apply field is rejected** (PERC-0057)
  The two parsers had diverged on it. As a glob or a preset name an empty
  string matches nothing the user could have meant, so both now refuse it.

- **Inside a layout, the last matching entry wins** (PERC-0057)
  This is what docs/09 has always specified; the engine returned on the
  first match. Rules are unchanged and still first-match-wins — the
  asymmetry is deliberate and each document states its own half.

- **AppImage builds now verify the bundle is self-contained** (PERC-0056)
  The build extracts the finished AppImage on a bare ubuntu:22.04
  container and fails if any bundled library fails to resolve there. The
  previous check ran --version, which exits before Qt is touched and so
  proved nothing about the bundle.

- **The settings dialog now closes after a confirmed import**
  It held the pre-import document parsed when it opened, so the next Apply
  from any pane wrote that stale copy back over the imported file, silently
  undoing the import.

### Removed

- **`PERCH_LOG_TITLES` is gone from the documentation — it never existed in code** (PERC-0062)
  Five documents described it as a privacy opt-in for logging window
  titles, and no code has ever read it: `logging_privacy` redacts
  unconditionally and says so. A control a security standard names and
  nothing reads is worse than no control, because it invites a reader to
  believe the redaction is switchable and audited. The documents now say
  what the code does. Nothing about logging behaviour changed.

### Fixed

- **Module docstrings that described shipped code as still to come** (PERC-0062)
  The X11 and KWin backend docstrings said their commands and hotkey
  registration had not landed and would raise; both are v1 backends and
  complete. Same class in the core modules, the app entry point, the rules
  table model and the KWin hotkey path — all rewritten to describe what the
  code does.

- **Instructions that named retired tools and a retired drive** (PERC-0062)
  `audit_config.yaml` and `CLAUDE.md` drove the drift analyser from a path
  on the failed `/mnt/Storage` drive, with a flag the analyser does not
  accept, so nobody following them could run it. The docs also mandated
  four Claude Code skills that no longer exist, and two of them stated that
  `local_CI.sh` runs one interpreter, which stopped being true when it
  learned to read `ci.yml`'s matrix.

- **A failing config migration reports the problem instead of a traceback** (PERC-0059)
  A missing migration step escaped as a bare `KeyError`. It is now a
  `ConfigError` naming the file and the version gap, which is what docs/02
  §Schema reference promises.

- **A typo'd top-level section is reported instead of ignored** (PERC-0059)
  Unknown keys inside `[general]` and `[exclusions]` were rejected, but an
  unknown table at the top level was not — so `[[rule]]` for `[[rules]]`
  meant every rule in the file went unread with no error. `schema_version
  = true` was also accepted, because a bool is an int in Python.

- **A hand edit to config.toml is no longer discarded silently** (PERC-0059)
  The settings dialog parses config.toml when it opens and writes it whole
  on Apply, so anything edited on disk in between was lost. Perch offers
  hand-editing as a supported workflow, so Apply now compares the file
  against what it read and asks before replacing it.

- **Editing a profile in the dialog is validated the way adding one is** (PERC-0059)
  Renaming a profile to a name another already uses, or giving it a
  topology that is a duplicate or malformed, went through none of the
  checks `add_profile` applies. The dialog wrote it and the loader refused
  the file on the next start, with nothing said at the time.

- **X11: a window is moved to its target desktop before it is placed** (PERC-0068)
  The two v1 backends disagreed — KWin sent the desktop change first, X11
  sent it last. A window manager is free to re-place a window when its
  desktop changes, so the placement has to be the last word. Both messages
  still go out before a single flush.

- **Excluded and unidentifiable windows are no longer remembered** (PERC-0057)
  A window covered by an exclusion was written to `state.json` on any
  user-initiated move, so Perch would restore later exactly what the
  exclusion asked it to leave alone. A window reporting neither `app_id`
  nor `wm_class` was stored under one shared key, so unrelated windows
  overwrote each other's geometry.

- **The maximize fallback places the window on the resolved target monitor** (PERC-0057)
  Where a backend rejects native maximize, Perch substitutes the work-area
  rectangle. It resolved that against the window's own monitor, which is
  where the window sat before the same action moved it. The log line now
  names the rule, as docs/02 specifies.

- **`maximized = false` unmaximizes before a monitor or desktop move** (PERC-0057)
  The pre-move unmaximize only ran when the action also carried a
  geometry, so on a compositor that ignores writes to a maximized window
  the move was dropped — the backend the rule exists for.

- **Percent geometry is clamped to the target monitor's work area** (PERC-0057)
  Percentages are not range-checked when the config is parsed, so a
  negative or oversized one placed the window off-screen — against
  docs/07's promise that a rule cannot.

- **`monitor = "all"` is rejected when the config loads** (PERC-0057)
  It validated and then failed on every window it matched. Nothing fans a
  single action out across every output; the valid forms are an output
  name, `primary`, `current`, or an integer index.

- **A `match` block combining `catch_all` with other fields is rejected** (PERC-0057)
  `catch_all` short-circuits, so the other fields were never consulted and
  one stray checkbox matched every window. The settings dialog refuses the
  combination too, rather than writing a config it would then not load.

- **A profile's `default_layout` is applied when the profile activates** (PERC-0057)
  The field parsed, seeded the documented sample and was editable in the
  dialog, and nothing read it: docking activated the profile and applied
  no layout. The config loader now also rejects a `default_layout` that
  names no declared layout.

- **Release and CI gate scripts no longer swallow their own failures** (PERC-0056)
  The library harvest, the Flatpak manifest rewrite, the OBS upload and
  the CI/local lockstep check each had a path where a failure was
  discarded and the step reported success.

- **AppImage: a program launched from Perch no longer inherits the bundle's libraries** (PERC-0056)
  Opening a link or the config folder from the tray launched the host
  browser or file manager against the AppImage's bundled AlmaLinux 8
  libraries, which could crash it. The entry point now records the
  host's own library path and Perch restores it for anything it spawns.

- **Shutdown now cancels in-flight actions, and a failed state flush no longer strands the backend**
  Neither step matched `docs/01-architecture.md` §Teardown order: tasks ran
  on into teardown, and an `OSError` from the `state.json` flush skipped
  `backend.stop()` entirely, leaving the KWin script loaded.

- **Background actions now log their failures to `perch.log`**
  An intent task's exception was never retrieved, so asyncio reported it on
  the unconfigured root logger — it reached stderr and never the file a bug
  report attaches.

- **Hyprland queries now refuse when the backend is not connected**
  The guard existed but had an empty body, so a stopped backend still
  queried the compositor and repopulated the caches `stop()` had cleared.

- **Perch now reports it when the Hyprland event stream closes**
  A clean EOF left the backend marked healthy while it would never deliver
  another event.

- **A failed KWin start no longer leaves a script running inside the compositor**
  `stop()` returned early unless the connection had fully succeeded, so any
  earlier failure left the bus name held and the injected KWin script
  loaded with nothing owning it.

- **A backend that fails to start no longer exits Perch with a traceback**
  `start()` is a documented raiser on three backends — the ordinary trigger
  is a second copy failing to take the D-Bus name — and it ran unguarded
  after the tray was already visible. It now degrades to the UI-only mode
  `docs/01-architecture.md` §Startup has always described.

- **Restoring a window to a negative position on X11 no longer crashes**
  `_NET_MOVERESIZE_WINDOW` coordinates are signed, but the wire packing is
  unsigned, so any window remembered off the left or top edge raised
  `OverflowError` outside the backend error taxonomy.

- **Minimising a window on X11 no longer makes Perch forget it permanently**
  ICCCM has the window manager unmap a client to iconify it, and Perch read
  that as a close — emitting the terminal `window_closed` for a window still
  open, after which nothing could restore it.

- **A profile that cannot be deleted no longer corrupts the ones after it**
  The failure was suppressed while the index remap still assumed it had
  happened, so every later field write landed on the wrong profile.

- **Adding a layout and then renaming it no longer fails the save**
  The rename bookkeeping registered the new name as its own original, so
  the add step was skipped and a description was written to a table that
  was never created.

- **A failed save no longer silently discards the other panes' edits**
  The document was rolled back but each pane that had already committed had
  frozen its baseline, so it reported clean and was never committed again.
  Panes now stay dirty until the write to disk has landed.

- **Apply then OK no longer deletes a rule or exclusion you did not touch**
  The Rules and Exclusions panes never refreshed their baseline after a
  successful commit, so a second commit re-applied the first delete against
  the original index — which by then addressed a surviving entry.

- **A symlinked `config.toml` is followed instead of being replaced**
  `rename(2)` acts on the link, so the first save moved the symlink itself
  to `.bak` and dropped a regular file in its place — silently detaching a
  config symlinked into a dotfiles repo.

- **Fractional percent geometries survive an unrelated layout edit**
  They were rounded to whole percents on every re-serialisation, so `12.5%`
  silently became `12%` across the file.

- **Editing a layout no longer writes a `config.toml` Perch cannot read back**
  A window `type` was serialised as a TOML array; the reader accepts only a
  comma-separated string and refuses an array outright. Because a layout
  edit re-serialises every entry, one unrelated change was enough.

- **A `config.toml` with a non-UTF-8 byte now falls back to the backup**
  It raised `UnicodeDecodeError`, which was outside the caught set, so it
  skipped the fallback and surfaced as a traceback.

- **A `config.toml` from a newer Perch is refused rather than silently replaced by the backup**
  It was treated as corruption, so an older config loaded and the newer one
  was rotated away on the next save. It now exits non-zero with a pinpoint
  message, per `docs/02-state-format.md` §Schema reference.

- **A missing `config.toml` beside an intact backup now recovers instead of reseeding**
  The atomic write's own crash window leaves exactly that state. Perch
  seeded defaults over it, and the next save rotated the surviving backup
  away — losing every rule, layout and profile.

- **A window geometry saved during a `state.json` write is no longer dropped**
  The dirty flag was cleared after the write rather than with the snapshot,
  so a change landing mid-write was marked clean without being saved.

- **A malformed record in `state.json` no longer stops Perch starting**
  A missing field raised `KeyError` past the handler, so the documented
  `.bak` fallback never ran and the exception escaped startup.

- **A `state.json` from a newer Perch is no longer destroyed by an older one**
  Rolling back a version discarded the newer file, then rotated it into
  `.bak` and overwrote both within seconds of the first window event —
  losing every remembered geometry. The store now latches read-only, as
  `docs/02-state-format.md` §Versioning and migration always specified.

## [1.1.0] — 2026-08-28

### Added

- **First-run setup wizard, opening on the zero-config message** (PERC-0003)
  `src/perch/ui/onboarding.py` adds the three-page `QWizard` specified in
  `docs/08-ui.md`. Page 1 states the only thing that matters — you don't need
  to configure anything, just move your windows and Perch remembers (that page
  is PERC-0004). Page 2 checks the setup: tray visibility, start-at-login, and
  which compositor was detected. Page 3 offers an optional route into the
  config dialog. Badge logic for the two real checks lives in pure `check_*()`
  functions, so it is tested without a live desktop; start-at-login is a
  preference and renders on/off, never a warning.

  Gated on a new `[general] onboarding_completed`, which defaults false and is
  absent from the seeded config, so a fresh install and an upgrading config
  both see the wizard exactly once. It is written on every exit — Finish,
  Cancel and window-close — so it never reappears unprompted; Finish also
  persists and applies the autostart choice, while Cancel changes no system
  setting. Settings → General carries a **Run setup wizard again…** button,
  which saves the dialog first and re-seeds the page afterwards so the two
  cannot fight over `Start at login`.

  The GNOME-Wayland AppIndicator guidance is now shared between the wizard's
  tray row and the standalone hint in `perch.app`, so the two cannot drift.

- **Tray menu: a Donate submenu and a Report an issue entry** (PERC-0035)
  Donate opens as a submenu with one entry per destination in
  `.github/FUNDING.yml`; Report an issue opens the GitHub issue tracker. Both
  go through `QDesktopServices.openUrl`, which resolves to the OpenURI portal
  under Flatpak and needs no extra sandbox permission. The destinations are
  stated in `perch.ui.links` because `.github/` is not shipped in any package,
  and a test asserts they match `FUNDING.yml`.

- **README install section for the openSUSE and Fedora RPM repository** (PERC-0041)
  `home:milnet:perch` on OBS builds green for openSUSE Tumbleweed and Fedora
  and is now advertised, with copy-paste zypper and dnf commands. Both
  repositories were checked to be serving the RPM before the link went in.

- **`local_CI.sh --docs` — a documentation-only push no longer runs the full suite** (PERC-0034)
  New `tools/docs_check.py` verifies every relative link in the docs set
  resolves and that no retired or forbidden string has crept outside the
  documents that record it. It runs as a third `ci.yml` job and, via
  `--docs`, alone — the pre-push hook selects that for a documentation-only
  push, turning roughly half a minute of gate into well under a second.
  `docs/contributing-dev-setup.md` owns what counts as documentation.

- **Self-contained AppImage — a single-file, zero-dependency Linux download**
  Download → chmod +x → run; no Python, PySide6, or system packages for the user to install. Bundles the interpreter, Qt, and the xcb platform libraries (verified self-contained on a bare container). Recipe at packaging/appimage/; built and attached to releases by .github/workflows/release.yml.

### Changed

- **Dropped `--filesystem=xdg-config/perch:create` from the Flatpak manifest** (PERC-0036)
  It was justified as sharing one config file with a native install, which it
  never did: the sandbox redirects `XDG_CONFIG_HOME`, so Perch's config stays
  inside the sandbox and the host grant went unused. Flatpak Perch keeps its
  own config, which is the Flathub norm.

- **OBS submission targets the `home:milnet:perch` subproject and uploads a release tarball** (PERC-0041)
  The subproject matches the convention already used for this account's
  other projects, and gives Perch its own repository list (Tumbleweed and
  Fedora, both x86_64). `packaging/rpm/_service` is deleted: its `obs_scm`
  entry was `mode="manual"`, so OBS never ran it and the build died with
  `no .obsinfo file found` — and having any buildtime service pulled the
  `obs-service-*` packages into the build root, where Fedora could not
  resolve `wget`. Two targets failing for two unrelated reasons, from one
  mechanism nothing needed. `packaging/submit/obs.sh` now uploads the
  GitHub release tarball, which is all `Source0` ever wanted; it also
  looked for `~/.oscrc` when osc uses `~/.config/osc/oscrc`, so it refused
  to run on a correctly configured machine.

- **Live and planned work moved to ROADMAP.md at the repo root; docs/11-roadmap.md is now history**
  ROADMAP.md is a generated render of the roadmap store, and each item carries a
  PERC-NNNN id. docs/11-roadmap.md keeps its number and filename (the numbered
  sequence is the reading order and is stable, per docs/filename-standards.md)
  but is retitled "Roadmap history" and now says up front what it is: the record
  of how Perch reached v1.0.0 — the phased plan, each milestone's exit criteria
  and the evidence they were met, the ground rules, the known risks, and the
  Phase 2 / 2.5 research logs. It had still described itself as the source of
  truth for milestone ordering.

- **Tray "Pause restore" is now "Pause Perch" — a full panic switch**
  Paused now suppresses every automatic placement (rules, layouts, and
  last-seen restore), not just the last-seen auto-restore, so no window is
  moved while paused. Manual "Snap focused" still applies. Renamed the
  TogglePauseRestore intent to TogglePause. See docs/08-ui.md §Menu structure.

### Removed

- **Fedora COPR dropped as a distribution channel — OBS builds the Fedora RPM from the same spec** (PERC-0041)
  It would have been a second build service producing one artefact from one
  spec, with a second set of credentials and a second thing to keep current.
  Fedora users are unaffected: OBS builds Fedora targets, and the
  `%if 0%{?fedora}` guards in the spec stay, because package names differ
  between the distro families regardless of who builds them.
  `packaging/submit/copr.sh` is deleted. The spec also cited a
  `packaging/rpm/COPR.md` that never existed.

### Fixed

- **X11 backend: a display that goes away during `start()` no longer crashes Perch**
  An X server can accept the connection and then reset it mid-handshake — a
  session ending as Perch starts, or a freshly launched `Xvfb`. python-xlib
  wraps that in `Xlib.error.ConnectionClosedError`, which subclasses
  `Exception` alone and so escaped `start()`'s `OSError` / `ConnectionError`
  handler as a raw traceback. It is now named at all three points it can
  fire (the `Display()` constructor, the subscription handshake, the first
  cache-priming round-trips) and raises the documented `BackendUnavailable`,
  tearing the half-open display down first, so the core takes its UI-only
  fallback path instead. Caught by CI run 33145715623.

- **Flatpak autostart: read the portal's Response, not the Request path** (PERC-0037)
  `org.freedesktop.portal.Background.RequestBackground` returns the object
  path of an `org.freedesktop.portal.Request`; the outcome arrives later as
  that request's `Response` signal. `portal_set_autostart` read the returned
  path as the result dict, so every Flatpak autostart toggle raised
  `AttributeError: 'str' object has no attribute 'get'` in a task nobody
  retrieved — autostart silently never took effect and nothing was logged.
  It now correlates the Response the way `PortalGlobalShortcutsProvider`
  already did, returns whether autostart was granted, and logs a warning on
  a refusal, a non-zero response code or a timeout.

- **The tray-host probe no longer reports "no host" inside a Flatpak** (PERC-0040)
  It let sdbus pick the default bus, which fails outright in a sandbox where
  `DBUS_SESSION_BUS_ADDRESS` is `/run/flatpak/bus`; every failure is
  classified as "no host", so the wrong answer was silent. On GNOME Wayland
  that fired the "install the AppIndicator extension" dialog at users who
  did not need it.

- **Tray icons no longer come out null on an installed layout** (PERC-0039)
  The bundled-SVG fallback resolved a path relative to the source tree,
  which only exists in a dev checkout — under Flatpak it pointed at a
  directory that is not there, and the icon-theme lookup does not cover for
  it. The XDG data directories are now searched first, which name `/app`
  inside a Flatpak and `/usr` under an RPM; `sys.prefix` does not, because
  a Flatpak's interpreter comes from the runtime.

- **Flatpak tray icon now appears — granted the StatusNotifierWatcher talk-name** (PERC-0038)
  The sandbox answered `ServiceUnknown` for `org.kde.StatusNotifierWatcher`,
  so Perch could neither probe for a StatusNotifier host nor register its
  item. Perch has no window, so this left the Flatpak with no interface at
  all.

- **KWin script now installs to the host path under Flatpak** (PERC-0036)
  Inside a Flatpak, `XDG_DATA_HOME` is redirected into the sandbox, so the
  bundled KWin script was mirrored to a path KWin — which runs on the host —
  cannot read, leaving the KWin backend unable to drive anything. The target
  is now resolved from `$HOME` when sandboxed. `PERCH_KWIN_SCRIPT_TARGET`
  still overrides everything.

- **The RPM spec now builds on Fedora — five bugs no local check could catch** (PERC-0041)
  Publishing to OBS for the first time found them all. `rpmspec -P` passed
  throughout, because every one of them only fails inside a real build root:
  openSUSE-only `BuildRequires` names (`appstream-glib`, `libxml2-tools`)
  left Fedora unresolvable; a `%build` comment naming `%pyproject_wheel`
  unescaped made rpm *call* the macro with the sentence as arguments;
  `%{_metainfodir}` is Fedora-only and undefined on openSUSE; the build
  selected a python flavor the build root did not ship; and the icon
  directories were unowned. Fedora now produces
  `perch-1.0.0-7.1.noarch.rpm`.

- **The Flathub manifest now builds — it was based on the wrong Qt toolkit and could not be built by anyone** (PERC-0042)
  It based on `com.riverbankcomputing.PyQt.BaseApp`, the PyQt base app, for
  an application built on PySide6; it targeted a KDE runtime eight months
  stale; and its Python dependency includes were commented out and
  deliberately not committed, to be generated at submission time — so a
  fresh clone could not build it at all. It now uses
  `io.qt.PySide.BaseApp//6.11` on `org.kde.Platform//6.11`, with the
  dependency closure sha256-pinned and committed as `python3-deps.yaml`,
  which is what Flathub's network-free builders require. Verified by a real
  offline build of the submission manifest.

  New alongside it: `generate-pip-sources.sh` regenerates the closure from
  `pyproject.toml`, `flatpak-build.sh` reproduces Flathub's build locally
  and smoke-tests the result, and `flathub.json` restricts the buildbot to
  the arch the pinned wheels cover. `packaging/submit/flathub.sh` no longer
  does the work itself; it also no longer targets the wrong base branch —
  a new app is PR'd against `new-pr`, not `master`.

- **Docs no longer promise an "Include last-seen geometries" export checkbox that does not exist**
  docs/02-state-format.md described an export checkbox for shipping state.json
  alongside the config, contradicting its own Export bullet and docs/08-ui.md.
  Export copies config.toml verbatim and has never included state.json. The
  section now also states a round-trip criterion: what must survive an
  export/import, what need not, and what travels but stays inert until the
  target machine has matching monitors. (PERC-0031, PERC-0032)

- **"Reapply rules now" is no longer a silent no-op**
  The tray "Reapply rules now" action was wired to recompute_topology(),
  whose topology-key early-return meant no window was re-evaluated unless the
  monitor layout had changed. It now calls a dedicated Reducer.reapply() that
  re-evaluates every open window regardless of topology, matching the
  ReapplyRules intent's contract.

- **Tray snap-preset labels are now translatable**
  The built-in snap-preset labels (Left half, Right half, …) were marked
  for extraction with a context-less QT_TR_NOOP but translated at runtime
  under the perch.ui.tray context, so a translator's work never reached
  the tray menu. They now use QT_TRANSLATE_NOOP("perch.ui.tray", …) and
  translations/perch_en.ts was regenerated (also picking up strings added
  since M3 that had never been re-extracted).

## [1.0.0] — 2026-04-21

First stable release. Perch is a persistent, compositor-aware window geometry manager with full X11 and KWin (Plasma Wayland) backends, stub backends for Mutter / Sway / Hyprland, a PySide6 tray + config dialog, a rules engine, named layouts, per-monitor profiles, portal-first global hotkeys, and packaging recipes for Flathub / OBS / COPR / AUR / KDE Store.

### Added

- Phase 0 bootstrap: LICENSE (GPL-3.0-or-later), README, CONTRIBUTING, CODE_OF_CONDUCT, `.github/` templates, `pyproject.toml` scaffold.
- Phase 1 design docs: `docs/00-overview.md` through `docs/11-roadmap.md` — twelve docs covering architecture, backend interface, state format, per-backend designs (X11, KWin, stubs), rules engine, UI, layouts/profiles, packaging, and the phased roadmap.
- Phase 2 validation: stack swaps (`dbus-next` → `sdbus-python`, `python-ewmh` → `python-xlib`), GNOME floor raised to 48, pre-paint placement declared best-effort.
- Phase 2.5 implementation-readiness: concrete 2026 version pins, canonical qasync bootstrap pattern, KWin IPC long-poll design (replaces the original tight-polling sketch), concrete X11 patterns.
- Project tooling under `.claude/`: docs-drift Stop hook, Python post-edit ruff hook, `/perch-docs-check` skill, permission allowlist.
- `audit_config.yaml` wired to the /audit pipeline with Perch-specific drift detectors.
- Icon: `data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg` (stylised crested bird on a perch; symbolic-ready, scales cleanly).
- `CHANGELOG.md` (this file) and `packaging/flathub/` scaffolds for the eventual Flathub submission.
- **M1 — Skeleton + config:** `src/perch/` package with the canonical `asyncio.run(main(), loop_factory=QEventLoop)` entry point; config subsystem (`tomllib` read, `tomlkit` comment-preserving write, atomic-write recipe, schema validation, migration registry); `RotatingFileHandler` logging + Qt → Python bridge; XDG path helpers; `AppState`. `perch --version` / `perch` / `perch --debug` all work end-to-end.
- **M1 test suite:** pytest covering schema validation, loader fallback to `config.toml.bak`, atomic-write semantics, logging wiring, XDG path resolution, CLI exit codes, and the release-blocking tomlkit round-trip fixture.
- **M1 CI:** GitHub Actions matrix (Ubuntu 24.04 × Python 3.12 / 3.13 / 3.14) running `ruff`, `mypy --strict`, and `pytest`. PySide6 installed from PyPI to step over Ubuntu 24.04's 6.4 distro package.
- `docs/contributing-dev-setup.md` covering editable install, smoke-test, and the house rules.
- **`apply = { maximized = true | false }` rule vocabulary** (design, lands in code with the rules engine at M2). Toggles the compositor's native maximized state via `WindowBackend.set_state(wid, WindowState.MAXIMIZED)`, distinct from the existing `geometry = "maximize"` preset which writes a work-area-sized rectangle. Sway and Hyprland raise `BackendUnsupported` for the maximize state (their tiling models have no equivalent); the core substitutes work-area geometry and logs at DEBUG. Documented in `docs/02-state-format.md` §Apply actions, `docs/07-rules-engine.md` §Apply order + §Validation, `docs/06-backend-stubs.md` (Sway, Hyprland).
- **M2.a — Backend interface + MockBackend + compliance suite:** `src/perch/backend/` package — `types.py` (frozen dataclasses, `WindowType`/`WindowState` enums, `Capabilities`), `base.py` (error taxonomy + `WindowBackend` abstract base class extending `QObject` with the event signal surface), `mock.py` (`MockBackend` with a driver API — `_spawn_window`, `_move_window`, output lifecycle, `_fire_hotkey`, `_fail_state` for the MAXIMIZED fallback contract). Reusable compliance tests at `tests/backend/test_compliance.py` parameterised over `BACKEND_CLASSES` in `tests/backend/conftest.py` — covers lifecycle, shape validation, capability↔behaviour alignment, event ordering, and the error taxonomy (22 new tests; 66 total green).
- **M2.b — Profiles + topology:** `src/perch/core/profiles.py` — `Profile` / `ProfileOverride` dataclasses, `compute_topology_key(outputs)` (sorted, connected-only, refresh/scale/serial deliberately excluded per `docs/09`), `parse_profiles(raw)` (validates duplicate names, duplicate topologies, malformed segments, and unknown keys), and `select_profile(profiles, key)` (first-match-wins). `config/schema.py::validate` now delegates `[[profiles]]` to the typed parser; `Config.profiles` is `list[Profile]` instead of `list[dict]`. 28 new tests; 94 total green.
- **M2.c — Rules engine + layouts:** Seven focused core modules — `matching.py` (`MatchPattern`, glob/regex predicate, AND semantics), `actions.py` (`ApplyAction`, `GeometryExpr` ADT of `AbsoluteGeometry` / `PercentGeometry` / `PresetGeometry`, `BUILTIN_PRESETS`, full `apply = { ... }` validation including the `maximized`/`geometry` contradiction and monitor-in-two-places conflict), `snaps.py` (`SnapPreset` + parser), `exclusions.py` (`BUILTIN_EXCLUDED_TYPES = {DESKTOP, DOCK}` + user-exclusion parser), `rules.py` (`Rule`, `Context` with `matches()`, first-match-wins context gating), `layouts.py` (`Layout`, `LayoutEntry`, parser), and `engine.py` — the pure evaluator that implements the decision order from `docs/07`. `Config` is now end-to-end typed (no `dict[str, Any]` escapes the config boundary). 113 new tests; 207 total green.
- **M2.d — Event reducer + state.json persistence:** Four new core modules — `identity.py` (`compute_identity(window)` — base `app:<app_id>` form with `app:<wm_class>` fallback), `resolver.py` (`resolve_action(...) → ResolvedPlacement` turning percent/preset geometries into pixels, monitor keywords into output names, with `unmaximize_first` flag for the docs/07 §Apply order ordering), `state_store.py` (`StateStore` — load-with-`.bak`-fallback, atomic write using the docs/02 §Atomic writes recipe, debounced `mark_dirty` scheduling, `is_dirty()` probe), and `reducer.py` — the `Reducer` class wiring backend events → engine → resolver → backend commands → state persistence. Feedback-loop prevention follows docs/07: every `set_geometry` call records the expected echo and the matching `geometry_changed` is dropped. Topology changes (`output_added` / `output_removed` / `output_changed`) are debounced at 300 ms before the profile swap. Sway/Hyprland `MAXIMIZED` unsupported fallback substitutes work-area geometry per docs/06. `StateStore.dirty` is now a method (`is_dirty()`) rather than a property so mypy's strict narrowing doesn't flag legitimate assert chains as unreachable. 56 new tests; 263 total green.
- **M2.e — Profile overrides + reconciliation:** `Layout.with_overrides(overrides)` substitutes matching-signature base entries and appends unmatched ones per `docs/09-layouts-profiles.md` §Per-profile overrides for layouts. `match_signature(pattern)` in `perch.core.matching` canonicalises match patterns so two independently-parsed matches with the same source shape compare equal for override purposes. `ProfileOverride.windows` is now `tuple[LayoutEntry, ...]` (parsed at config load, not at apply time). Reducer maintains an `_effective_layout` that the engine consults — recomputed on layout activation and topology/profile change. `_percent_to_float` simplified to trust its pre-validated caller (removes dead defensive branches). Defensive-input coverage tests backfill every remaining parser error path, pushing **rules-engine line coverage to 100%** across `matching.py`, `actions.py`, `rules.py`, `layouts.py`, `exclusions.py`, `engine.py` (M2 exit criterion). docs/07 + docs/11 tense reconciled. 23 new tests; 286 total green.
- **M2.5 — KWin IPC spike:** `experiments/kwin_ipc_spike/` — a ~30-line KWin JS script (`script/contents/code/main.js`) packaged with `metadata.json`, a ~100-line sdbus-python host (`host.py`) that owns `io.github.milnet01.Perch.spike` at `/KWin` and implements long-poll `PollCommand` with a 5 s heartbeat ceiling, and a measurement harness (`harness.py`) driving `org.kde.KWin.Scripting.loadScript` / `unloadScript`. Three probes: 10 000 round-trip latency, reload-cycle recovery, and configurable-duration idle (RSS sampling for self + KWin). Results on the developer machine (Plasma 6.6.4) recorded in `SPIKE_RESULTS.md`: p50 = 138 µs, p99 = 452 µs, max = 1.27 ms — two orders of magnitude under the 5 ms exit-criterion target; reload recovery clean; no observable Python-side RSS growth on the 2-minute smoke. **Go** verdict on 6.6.4; Plasma 6.2 / 6.3 / `kdeneon:unstable` deferred to M5-prep.
- **M3.a — UI scaffold + tray skeleton:** `src/perch/ui/` package with `intents.py` (frozen-dataclass intent ADT the core consumes — `ActivateLayout`, `SnapFocused`, `TogglePauseRestore`, `ReapplyRules`, `OpenConfigDialog`, `OpenConfigFolder`, `ShowAbout`, `Quit`), `sni_probe.py` (synchronous `sni_host_available()` using `sdbus_block.dbus_daemon.FreedesktopDbus` + a property read on `/StatusNotifierWatcher`; the freedesktop rename never shipped so we check `org.kde.StatusNotifierWatcher` and `IsStatusNotifierHostRegistered == true` as an AND probe — watcher-without-host is treated as "no tray"), and `tray.py` (`TrayState` frozen dataclass, pure `build_tray_menu(state, controller) → QMenu`, `TrayController` with `intent = Signal(object)` and `state_changed`, `TrayIcon` shell that rebuilds the menu on `state_changed` and calls `setContextMenu(new_menu)` — `aboutToShow` is not used because QTBUG-55911 leaves it unemitted for tray-attached menus on Linux). `app.py` rewritten to wire the UI end-to-end with `MockBackend` + `Reducer` + `StateStore`; intents route through `_handle_intent` which schedules `asyncio.Task`s on a module-level set (RUF006 fix). First-run `_maybe_show_appindicator_hint` surfaced only when the SNI probe is negative AND `XDG_CURRENT_DESKTOP` contains `GNOME` AND `XDG_SESSION_TYPE == wayland`. `__main__.py` grew a `--check-config` smoke-exit flag for CI and packaging self-tests. 29 new tests (20 tray, 9 SNI); 315 total green; mypy --strict clean.
- **M3.d — i18n plumbing:** `src/perch/i18n.py` (module-level `QTranslator` instances — keeping them at module scope dodges the PySide6 GC footgun where Python reclaims the Python wrapper and translations silently revert; loader tries `$PERCH_TRANSLATIONS_DIR`, `/app/share/perch/translations`, `$sys.prefix/share/perch/translations`, dev-checkout fallback, in that order). `translations/perch_en.ts` (Qt Linguist XML; 19 strings extracted from the tray module via `pyside6-lupdate -extensions py src/perch`). User-visible tray strings wrapped via inline `QCoreApplication.translate("perch.ui.tray", "…")` calls (Qt Linguist's `lupdate` doesn't chase Python-level wrapper functions, so the verbose inline form is required) with `QT_TR_NOOP` marking the `BUILTIN_SNAP_MENU_ITEMS` tuple so labels survive extraction while still living in a constant. `scripts/i18n-update.sh` wraps the `lupdate` invocation for contributors. `.gitignore` excludes `translations/*.qm` (build product; `.ts` sources are versioned). `docs/08-ui.md` §Localization rewritten: translations live under `translations/` (not `po/` — that's a gettext signal and Qt's `.ts` format is not gettext-compatible).
- **M3.c — Reusable widgets: match, geometry, key-capture:** `src/perch/ui/widgets/` — three standalone-testable Qt widgets that round-trip through the core's typed dataclasses.
  - `MatchEditor` edits a `perch.core.matching.MatchPattern`: `app_id` / `wm_class` globs, `title` regex (inline-validated — compile failure surfaces on the field's tooltip and flips `validityChanged(False)`), `pid` integer filter, a check-grid of `WindowType` flags, and the `catch_all` escape hatch. Empty fields round-trip to `None` (not empty strings) so the emitted `MatchPattern` matches what `parse_match` produces from TOML.
  - `GeometryEditor` edits a `perch.core.actions.GeometryExpr`. A mode combo drives a `QStackedWidget` between Absolute (pixel `QSpinBox`es), Percent (`QDoubleSpinBox` 0-100 with `%` suffix), and Preset (combo of `BUILTIN_PRESETS`; `add_user_presets()` appends user snap names; unknown preset names injected via `set_value` are preserved so round-trips don't lose user data).
  - `HotkeyEdit` — `QKeySequenceEdit` subclass with `setMaximumSequenceLength(1)` + `setClearButtonEnabled(True)`. `keyPressEvent` filters bare `Key_Super_L`/`Super_R`/`Hyper_L`/`Hyper_R` so modifier-only presses never record on GNOME Wayland and wlroots-derived compositors (QTBUG-62102; KWin patches this at the compositor level, other Wayland stacks don't). Emits `accelChanged(str)` in `QKeySequence.PortableText` form (`"Meta+Left"`); rejects bare printable keys without a modifier but accepts unmodified F1-F35.
  - `portable_to_xdg()` / `xdg_to_portable()` translators at the `org.freedesktop.portal.GlobalShortcuts` boundary (`Meta ↔ LOGO`, `Ctrl ↔ CTRL`, etc.). Internal accelerator form stays Portable Text so the KGlobalAccel and X11 transports see the value as-is; portal callers translate at the boundary.
  - Dialog wiring: the Hotkeys section is now a live `HotkeysPage` showing `HotkeyEdit` next to each user snap preset, with a preview-only banner — persistence lands with the registration transports in M5. 35 new widget tests (10 match, 9 geometry, 16 key-capture) + 2 Hotkeys-page tests; 389 total green; mypy --strict clean.
- **M3.e — AppStream metainfo + desktop entry + screenshots:** `data/io.github.milnet01.Perch.metainfo.xml` (AppStream 1.0; `<developer>` with `id=` attr per the 2026-current schema; OARS 1.1 content rating with every attribute explicitly `none`; branding colours; inline `<releases>` with a `<url type="details">` pointing at the CHANGELOG anchor). `data/io.github.milnet01.Perch.desktop` (validator-clean). `scripts/render-screenshots.py` renders `docs/screenshots/tray-menu.png` and `docs/screenshots/rules-editor.png` under `QT_QPA_PLATFORM=offscreen` via `QWidget.grab()` so CI can regenerate them without a display. `docs/08-ui.md` §Screenshots links them with one-line captions. `pyproject.toml` sdist now includes `scripts/`, `translations/`, and the metainfo / desktop files via the existing `data` / repo-root patterns. `appstreamcli validate` and `desktop-file-validate` pass (the two remaining warnings are "screenshot URL not on `main` yet", self-resolving on push).
- **M3.b — Config dialog scaffold + edit flows:** `src/perch/ui/dialog.py` — a `QDialog` with an eight-row `QListWidget` sidebar driving a `QStackedWidget` of pages (General, Windows, Rules, Layouts, Profiles, Hotkeys, Exclusions, Import / Export), per `docs/08-ui.md` §Config dialog. General edits flip the four `[general]` toggles + theme combo via the new `perch.config.edit.apply_general`. Rules section is a `QTableView` over the new `perch.ui.rules_model.RulesModel` — a `QAbstractTableModel` that owns a working-copy of the rules list and implements `moveRows()` wired to `QAbstractItemView.InternalMove`, with `setDragDropOverwriteMode(False)` as the mandatory drag-reorder gotcha from the M3 research. Deep-copy-on-open / replace-on-OK so Cancel leaves the caller's list untouched. The Exclusions section mirrors the pattern via a simpler `QListWidget` with `InternalMove`. Placeholder pages (Windows / Layouts / Profiles / Hotkeys / Import-Export) carry "arrives in a later milestone" labels so the sidebar renders every documented row. Save path mutates the existing tomlkit document in place (not a rebuild from scratch — that dropped trailing trivia) via `perch.config.edit.{apply_general,reorder_rules,delete_rule,reorder_exclusions,delete_exclusion}`; atomic `write_document` handles the temp-file-and-rename write. `_on_ok` stages onto a deep-copy of the document so a save failure leaves the dialog's state pristine and surfaces a `QMessageBox.critical`. Tray's `OpenConfigDialog` intent now opens the dialog; `ShowAbout` still stubs. 37 new tests (11 config-edit, 18 RulesModel, 8 dialog); 352 total green; mypy --strict clean.
- **M7.f — Dark-theme pass:** `src/perch/ui/theming.py::apply_theme(app, theme)` called from `src/perch/app.py::main` at startup, right after `install_translators`. `"auto"` reads `QGuiApplication.styleHints().colorScheme()` (Qt 6.5+): `Unknown` is a no-op (leaves Breeze-Dark et al. untouched), `Light` / `Dark` apply Fusion + the matching hand-built palette. Explicit `"light"` / `"dark"` values force Fusion + the matching palette unconditionally — a GNOME-Adwaita-Dark user who wants a light Perch dialog gets it. Palettes are Breeze-inspired so the result looks native on Plasma users who override to `"dark"` specifically. 9 new tests in `tests/ui/test_theming.py`; docs/08-ui.md §Interaction rewritten present-tense. Runtime theme-change propagation without a restart is a follow-up.
- **M7.e — Privacy review of logs:** `src/perch/logging_privacy.py` adds `redact_payload(payload)` + `summarize_keys(payload)`. Window-title-bearing keys (`title`, `name`, `caption`, `class`, `initialTitle`, `initialClass`, `window_class`) get replaced with `<redacted>` before `%r` formatting; the rest of the structure is preserved for debuggability. Applied to the high-risk sites: KWin `on_window_added` (WARNING), `on_window_geometry_changed`, `on_window_properties_changed`, the `list_windows` skip-malformed path (all DEBUG); Hyprland `list_windows`, `list_outputs`, `event dispatch failed`, and `unhandled Hyprland event` (the last two redact to the event name only — the raw `socket2` line and `data` payload both carry the active window title verbatim on ≥ 0.40). 9 new tests in `tests/test_logging_privacy.py`; docs/08-ui.md gets a new §Logging and privacy subsection pinning the policy.
- **M7.d — Performance harness for the rules engine (500×500):** `tests/core/test_engine_performance.py` parametrises `perch.core.engine.evaluate` at (100 rules × 100 windows), (500 × 500), (1000 × 1000), placing the matching rule *last* so every window walks the full list. Measured on the reference dev box: 5 ms / 55 ms / 200 ms. Budgets are 0.5 s / 2 s / 10 s — the 10-20× headroom absorbs CI jitter while still catching quadratic regressions. A separate test confirms builtin-exclusion short-circuits O(1) on 500 dock windows. `docs/07-rules-engine.md` §Performance model updated with the measured table and a note pointing at compiled regex caches + app_id prefiltering as the obvious first cuts if a user materialises with a 500+-rule config.
- **M7.c — Error-surfacing audit:** `src/perch/ui/status.py` introduces `wire_backend_status(backend, controller, tray)` bridging the three `WindowBackend` status signals into the tray surface — `backend_connected` clears `backend_degraded`, `backend_disconnected` sets it (tray icon flips to warning variant + tooltip changes to "Perch — backend disconnected"), and `backend_error` surfaces a `QSystemTrayIcon.showMessage` balloon notification. `src/perch/app.py` wires the bridge between tray construction and `backend.start()` so a synchronous `backend_connected` from `start()` still updates the tray. Remaining untranslated user-visible strings wrapped in `QCoreApplication.translate(...)` / `self.tr(...)`: the `_maybe_show_appindicator_hint` dialog's title / body / informative text and the four `MatchEditor` `QLineEdit` placeholders. 8 new tests in `tests/ui/test_status_bridge.py` including the end-to-end `TrayIcon` tooltip round-trip.
- **M7.b — Dialog keyboard navigation audit:** `src/perch/ui/dialog.py` — `_DeleteKeyTableView` + `_DeleteKeyListWidget` subclasses let Delete / Backspace remove the selected row on the Rules table and Exclusions list (QShortcut + `WidgetWithChildrenShortcut` doesn't fire against `QTableView` — its built-in cell-editing delete handler swallows the key before the shortcut resolver sees it). Explicit `setTabOrder(sidebar → stack → buttons)` pins the Tab chain and the sidebar gets initial focus. Accessible-name / description strings on the sidebar ("Sections"), rules table ("Rules table"), and exclusions list ("Exclusion patterns") so orca + Qt's accessibility bridge announce them clearly. 7 new tests in `tests/ui/test_dialog_keyboard.py`; docs/08 §Accessibility rewritten present-tense.
- **M8.g — Release plumbing + docs close-out:** `.claude/bump.json` wired to `pyproject.toml`, `src/perch/__init__.py`, `packaging/rpm/perch.spec`, `packaging/aur/PKGBUILD`, and the Flatpak manifest's `tag:` line (the KWin `BUNDLED_SCRIPT_VERSION` is deliberately left independent per docs/05 §Version pinning). `docs/10-packaging.md` rewritten present-tense — every channel now points at the authored artefacts under `packaging/`. `docs/05-backend-kwin.md` §Hotkeys rewritten: portal path is preferred, KGlobalAccel is the explicit fallback. `KWinBackend.capabilities.notes` updated to match the new policy.
- **M9 — v1.0.0 release:** final docs pass — `README.md` and `CLAUDE.md` rewritten for a shipped project (status lines, Python floor, backend table, repo layout, installation instructions); `CONTRIBUTING.md` lint/test command made concrete; `docs/10-packaging.md` §Release mechanics points at `.claude/bump.json`; `docs/11-roadmap.md` phase map and M9 section marked done; Post-v1 ideas annotated with the docs that reference each deferred item. Version bumped to `1.0.0` across the five `.claude/bump.json` files; AppStream metainfo `<releases>` block replaced with a stable `1.0.0` entry and screenshot URLs pinned to the `v1.0.0` tag; `Development Status` classifier lifted to `5 - Production/Stable`.
- **M9.f — Config dialog gap closure:** smoke-testing v1.0.0 surfaced that four dialog panes still shipped the M3-era "arrives later" placeholder text and the Hotkeys page's edits were preview-only. Everything is now wired up:
  - **Windows pane** (`WindowsPage` + `src/perch/ui/windows_model.py`) — live `QTableView` over a `WindowsTableModel` seeded from `backend.list_windows()` and updated by the four lifecycle signals. Per-row **Save as last-seen** / **Forget last-seen** buttons mutate `StateStore`; commit flips `mark_dirty()` so the store flushes on the dialog's Apply / OK.
  - **Layouts pane** (`LayoutsPage`) — split layout list + entry table with Add / Rename / Delete at the layout level and Add / Edit / Delete / Move-up / Move-down at the entry level. Entry editing uses the new `EntryEditorDialog` which composes `MatchEditor`, `GeometryEditor`, a Snap-preset combo (built-ins + `[snaps]` names), and monitor / desktop / maximized fields with the same contradiction checks the TOML parser applies at load time. Commit replays through new `perch.config.edit.{add_layout, rename_layout, delete_layout, set_layout_description, add_layout_entry, update_layout_entry, delete_layout_entry, reorder_layout_entries}` mutators.
  - **Profiles pane** (`ProfilesPage`) — profile list + per-profile Name / Topology / Default-layout form + overrides table. Override editing wraps `EntryEditorDialog` in an `_OverrideEditorDialog` that also picks the override's target layout. Commit replays through new `perch.config.edit.{add_profile, delete_profile, rename_profile, set_profile_field, set_profile_overrides}` mutators.
  - **Import / Export pane** (`ImportExportPage`) — file-picker backed Export (`QFileDialog.getSaveFileName` → copy current `config.toml`) and Import (open-file → schema validate → `difflib.unified_diff` → Confirm / Cancel → atomic replace via `config.writer.atomic_write`).
  - **Hotkeys pane** — removed the "preview only" banner and stub `is_dirty/commit`. Edits now diff against the snapshot at open time and persist through `perch.config.edit.apply_snap_hotkey` on commit.
- **M9.f.7 — Runtime bugs surfaced by smoke-test:** fixed four shipped-but-broken pieces caught by running v1.0.0 live. `app.py` now calls `perch.backend.select()` (with `MockBackend` fallback + a startup log line) instead of hardcoding `MockBackend`, so the Windows pane shows real windows on KWin / X11. The config dialog's `saved` handler re-calls `apply_theme(app, fresh.general.theme)` so light ↔ dark toggles take effect on Apply without restart. `sni_host_available()` and `is_gnome_wayland()` moved from inside the async `main()` to `__main__.cli` before `asyncio.run(...)` — sdbus's sync API refuses to run with an active asyncio loop attached. The Quit intent now also calls `QApplication.quit()` (not just `close_event.set()`) and the loop installs a SIGINT / SIGTERM handler so Ctrl+C shuts down cleanly instead of tracebacking with `KeyboardInterrupt`.
- **M9.f.8 — Windows pane polish:** `WindowsTableModel` filters on a `USER_VISIBLE_TYPES` allowlist (`NORMAL` / `DIALOG` / `UNKNOWN`) at the model boundary, so hovering over UI chrome stops flashing phantom "ghost" rows (Qt tooltips reported as 201×22 `python3.13` windows on hover). The pane also grows a preset combo + **Apply preset** button that resolves `BUILTIN_PRESETS` + user `[snaps]` entries against the selected window's current monitor via `resolve_action` and calls `backend.set_geometry` — the direct "select window → pick preset → resize" flow that's the app's core use case.
- **M9.f.9 — Dialog close no longer kills the app + Profiles reject empty topology:** `QApplication.setQuitOnLastWindowClosed(False)` so clicking ✕ on the Preferences dialog only hides it (the tray icon and the asyncio loop are the authoritative lifetime owners; Quit intent / SIGINT / SIGTERM are the exit routes). `add_profile` / `set_profile_field` reject empty `name` / `topology` strings, and `ProfilesPage.commit` pre-validates the working copy and raises `ConfigEditError` with a user-facing explanation before any write hits disk.
- **M9.f.10 — Snap-focused tray intent wires through + size-preserving centre + clean shutdown:** `WindowBackend.get_active_window()` added (base raises `BackendUnsupported`; KWin implements via a new `queryActiveWindow` JS op). The `SnapFocused` tray intent now spawns `_snap_active_window` which queries active → `resolve_action` → `set_geometry`. Tray preset IDs (`top-left` / `top-right` / `bottom-left` / `bottom-right` / `center-60`) were missing from `BUILTIN_PRESETS` — added as aliases so the tray's "Snap focused window" submenu actually resolves. New `CenterKeepSize` `GeometryExpr` + `center-in-place` preset that centres the window without resizing (reads `window.geometry.{w, h}` at apply time). Tray menu now exposes it as "Centre (keep size)" alongside "Centre (60%)". Shutdown regression fixed: `app.quit()` moved from the Quit-intent / SIGINT handlers (which stopped qasync mid-finally with "Event loop stopped before Future completed") to the tail of `main()` after async cleanup.
- **M9.f.11 — Audit catches shipped-stub log strings:** four new `perch_drift` patterns in `audit_config.yaml` match the literal strings that characterise "handler ships as a log call" stubs (`routed in Mx`, `lands in Mx`, `not yet persisted/saved/wired/routed`, `lands in a (later|follow-up) milestone`, `placeholder` / `soon` prose markers). Running `/audit` against the v1.0.0 prep commit flagged two stubs: `ShowAbout` tray intent was a log-only stub — now shows a proper `QMessageBox.about` with version / license / project URL; `_PlaceholderPage` class in `dialog.py` was dead code after M9.f.1–4 replaced all placeholder panes — removed.
- **M9.f.12 — KWin JS: `Qt is not defined` + hardcoded script version:** `doSetFrameGeometry` used `Qt.rect(x, y, w, h)` — KWin's JS sandbox doesn't expose the `Qt` namespace, so every `set_geometry` call on live KWin silently failed with `{ok: false, error: "exception: Qt is not defined"}`. Swapped in a plain `{x, y, width, height}` object (Plasma 6 coerces via the QML property setter). The `ScriptReady` signal also hardcoded version `"1.0.0"` as a literal; lifted to a `const SCRIPT_VERSION` at the top of `main.js` pinned by `test_main_js_script_version_matches_python_constant`. Regression guard: `test_main_js_does_not_use_Qt_namespace` greps for any `Qt.X(` in the script and fails the build.
- **M9.f.13 — Intent dispatch audit tool + `TogglePauseRestore`:** new `tools/intent_dispatch_audit.py` that AST-walks `ui/intents.py` and `app.py::_handle_intent` to verify every variant of the `Intent` union has a handler body doing real work (not just a `log.*` call). Exit code is the finding count; wired into `.github/workflows/ci.yml` as a gate step after mypy. First run flagged one miss: `TogglePauseRestore` was still a log-only stub — now flips a real `Reducer.paused: bool` flag, and `handle_window_opened` skips `RestoreLastSeen` decisions when paused (rule / layout actions still apply, as they're explicit user intent).
- **M9.f.14 — KWin install uses content-digest, not just version:** `ensure_installed` short-circuited on `metadata.json` version match, so a `main.js` bugfix that didn't bump `BUNDLED_SCRIPT_VERSION` was invisible to the user forever — the M9.f.12 `Qt.rect` fix didn't reach any live session because install kept saying "already at v1.1.0" while the stale broken `main.js` kept loading. Install now also computes a SHA-256 of the bundled source tree and compares against the on-disk tree; any content divergence triggers a full mirror. Version bumped to 1.1.1 to force a fresh install on existing users.
- **M9.f.15 — Drop broken `preplace`; stops windows getting stuck on top:** `doSetFrameGeometry`'s `preplace` branch set `keepAbove=true` then tried to schedule a `QTimer` to clear it — but `QTimer.triggered.connect(...)` also isn't available in KWin's JS sandbox (the earlier "QTimer is reliably exposed" comment was wrong). Result: every successful `set_geometry` left the window pinned on top until the user manually cleared it. Removed the entire `preplace` block from `main.js`; `set_geometry` no longer sets `preplace=True`; `can_preplace_windows` capability flipped `True → False` to match reality. `BUNDLED_SCRIPT_VERSION` → `1.1.2`.
- **M9 validation sweep:** 796 tests pass, `ruff` + `mypy --strict` + `appstreamcli validate --no-net` + `desktop-file-validate` + `rpmspec -P` + `bash -n` PKGBUILDs + YAML/JSON parse all clean.
- **M8.f — KDE Store listing + CI validation job:** `packaging/kde-store/LISTING.md` with the store copy, tags, screenshot captions, and the GHNS install command pointing at the Flatpak — no parallel tarball upload, since maintaining a second binary channel duplicates what Flathub already handles. `.github/workflows/ci.yml` gains a `packaging` job running `appstreamcli validate` on the metainfo, `desktop-file-validate` on the desktop entry, `yamllint` on the Flatpak manifest, `rpmspec -P` on the RPM spec, `bash -n` on both PKGBUILDs, and well-formedness on the KWin script's `metadata.json` — every submission-blocking artefact is checked on every PR. Runs independent of the test matrix so packaging regressions surface without blocking on the Python grid.
- **M8.e — XDG Desktop Portal GlobalShortcuts hotkey path:** `PortalGlobalShortcutsProvider` in `src/perch/backend/kwin/hotkeys.py` — full `CreateSession` → `BindShortcuts` → `Activated` signal flow with per-Request `Response` correlation, portable-to-XDG accel translation (`Ctrl+Shift+Q` → `CTRL+SHIFT+Q`) inlined in the backend layer to keep the UI module out of the backend import graph. `choose_provider()` now probes portal availability (via a CreateSession dry-run) when `/.flatpak-info` is present or a portal factory is injected, falling back to KGlobalAccel cleanly on probe failure. `PERCH_HOTKEY_PROVIDER=mock|portal|kglobalaccel` env override short-circuits the probe for tests and unusual installs. Portal unbind is a local-map eviction because the spec doesn't expose `UnbindShortcuts` — session-close at `stop()` releases everything at once. 12 new tests in `tests/backend/kwin/test_hotkeys.py` using an in-memory fake portal.
- **M8.d — Autostart (XDG .desktop + Background portal):** `src/perch/autostart.py` wires both paths behind a single `sync(enabled)` façade. Non-Flatpak: atomic temp-and-rename write to `$XDG_CONFIG_HOME/autostart/io.github.milnet01.Perch.desktop` with `X-GNOME-Autostart-enabled=true`; honours freedesktop `Hidden=true` on the existence probe. Flatpak: async `org.freedesktop.portal.Background.RequestBackground` with `autostart=true` and `commandline=["perch"]`, routed as a background task when a qasync loop is running so the config dialog's OK button doesn't block on the portal's permission prompt. `is_flatpak()` probes `/.flatpak-info` as the canonical sandbox marker. `sync_from_config` is called at startup and from the config dialog's `saved` signal — the `Start Perch at login` checkbox now takes effect immediately without a restart. Portal failures are logged at WARNING and swallowed so a portal outage never blocks a config save. 16 new tests in `tests/test_autostart.py`.
- **M8.c — Flatpak manifest finalisation:** `packaging/flathub/io.github.milnet01.Perch.yml` cleaned up and tightened. Fixed the stale `src/perch/backends/kwin/` path (the package is singular `backend/` — a pre-M5 artefact). Dropped `--device=dri` (Perch is tray + QDialog, never touches a 3D surface). Replaced the blanket `--socket=session-bus`-plus-open-name posture with targeted `--talk-name` entries for `org.kde.KWin`, `org.kde.kglobalaccel`, `org.freedesktop.Notifications`, and `org.freedesktop.portal.Desktop`. Added the three symbolic status icons to the install commands. `python3-*.yml` include files are deliberately left out of the tree — `flatpak-pip-generator` regenerates them on each submission, and a committed copy would fight the `pyproject.toml` pins at every dep bump. `SUBMISSION.md` documents the regen recipe.
- **M8.b — AUR PKGBUILDs:** `packaging/aur/PKGBUILD` (stable, from tarball) + `packaging/aur/perch-git/PKGBUILD` (HEAD, with `pkgver()` derived from `git describe`). Both use the modern `python -m build --wheel` + `python -m installer` flow required by current Arch packaging guidelines. `provides=('perch')` / `conflicts=('perch')` on the `-git` side so users pick one channel. `python-i3ipc` is an `optdepends` (Sway backend is transport-gated — forcing it on every Arch install is wrong). `packaging/aur/README.md` covers the .SRCINFO + `git subtree push` maintenance flow.
- **M8.a — RPM spec for OBS + Fedora COPR:** `packaging/rpm/perch.spec` — one unified spec with `%if 0%{?suse_version}` guards for the PySide6 package-name divergence (openSUSE `python3-PySide6` vs. Fedora `python3-pyside6`). `%check` runs `appstream-util validate-relax --nonet` and `desktop-file-validate` inline so metadata regressions abort the build before package generation. `packaging/rpm/_service` drives OBS tagged rebuilds via `obs_scm` + `set_version`. `packaging/rpm/README.md` covers the OBS and COPR submission flows + the local smoke-build recipe. Translations (`*.qm`) are compiled at install time via `lrelease-qt6` or `pyside6-lrelease`, landing under `/usr/share/perch/translations/`.
- **M7.a — Tray status icons + HiDPI audit:** Three symbolic status variants land at `data/icons/hicolor/symbolic/status/perch-tray{,-warning,-error}-symbolic.svg`. `src/perch/ui/icons.py` loads the bundle via `QIcon.fromTheme("perch-tray-symbolic", bundled_fallback)` so packaged installs pick up the user's icon theme and dev checkouts still render. `src/perch/ui/tray.py` gains a `TrayIconState` enum + `TrayState.{icon_state,tooltip}` derivation + `TrayIcon._on_state_changed` that swaps `setIcon` on every state transition; new `TrayState` fields `awaiting_extension` and `compositor_missing` complete the docs/08 §Icon states matrix (warning on degraded-backend or missing-extension; error wins when no compositor is detected). `src/perch/app.py` reads the SNI-probe outcome into the initial `TrayState` instead of the previous log-then-forget. `pyproject.toml` adds `[tool.hatch.build.targets.wheel.shared-data]` mapping `data/icons → share/icons`, the desktop entry → `share/applications/`, and the AppStream metainfo → `share/metainfo/` so `pip install` deposits everything where `QIcon.fromTheme` + `xdg-open` + `appstreamcli` expect it. Qt's SVG renderer handles HiDPI at every scale factor natively — no raster variants shipped. 14 new tests (`tests/ui/test_tray_icon_states.py`); docs/08 §Tray icon rewritten present-tense; docs/11 §M7 gets an in-progress status line + per-subphase tracker.

### M2 exit criteria, verified

- Compliance suite passes against `MockBackend` (22 tests green).
- Rules engine has 100 % line coverage (verified via `coverage run -m pytest`).
- Scripted event sequences through `MockBackend` produce the expected `set_geometry` calls — `tests/core/test_reducer.py` is the table-driven pytest called out by the roadmap.

### Changed

- `pyproject.toml`: hatchling `src/`-layout wheel + sdist config wired; `tool.hatch.version` sources `__version__` from the package; `ruff.target-version` lifted from the stray `py311` to `py312` to match the locked Python floor; `mypy --strict` and `pytest-qt`/`asyncio_mode = "auto"` knobs added.
- **Backend lifecycle methods renamed `connect()` / `disconnect()` → `start()` / `stop()`** to avoid the collision with `QObject.connect` / `QObject.disconnect` (Qt's signal/slot staticmethods). Signal names (`backend_connected`, `backend_disconnected`) are unchanged. Docs updated across `01-architecture.md`, `03-backend-interface.md`, `05-backend-kwin.md`, `06-backend-stubs.md`, `11-roadmap.md`.

### Deprecated

### Removed

### Fixed

- **Orphan `PollCommand` awaiter after `unloadScript`** (surfaced by the M2.5 cycle probe before M5 ever has to debug it). When the KWin JS script is unloaded, any in-flight `PollCommand` coroutine on the Python side is still `await`ing the asyncio command queue; the next queued command would be consumed by the orphan and its reply routed to a KWin callback ID that no longer exists, so the new script instance never saw the command. Fixed in `experiments/kwin_ipc_spike/host.py` via `invalidate_polls()` — atomically swaps in a fresh `asyncio.Event`, signals the old one, so all orphan awaiters return `{"nop": true, "reason": "invalidated"}` and the queue is free for the new instance. `docs/05-backend-kwin.md` §Poll invalidation records the pattern so the real `KWinBackend` in M5 inherits the fix.

### Security

[Unreleased]: https://github.com/milnet01/perch/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/milnet01/perch/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/milnet01/perch/releases/tag/v1.0.0
