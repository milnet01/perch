<!-- ants-roadmap-format: 1 -->

# Perch — Roadmap

Live and planned work. The milestone history (phases 0–4, M1…M9), the
known-risks list and the Phase 2 / 2.5 research logs stay in
[`docs/11-roadmap.md`](docs/11-roadmap.md), which remains the source of truth
for milestone ordering and for the ground rules cited below.

None of the items here is a hard commitment — scope and ordering may change,
and community backends land whenever a contributor picks them up.

- **Status markers:** 📋 planned · 🚧 in progress · ✅ done · 💭 considered
- **Effort tags:** S small · M medium · L large · XL spans multiple releases

---

## v1.0.1 — Get it downloadable

Goal: anyone can install Perch without building from source.

- ✅ [PERC-0001] **AppImage — single-file download, zero dependencies for the user.**
  Download → mark executable → run; no system install, no root. The Python
  interpreter, PySide6/Qt and the Qt `xcb` platform libraries are all bundled,
  verified on a bare container with none of them pre-installed. Recipe at
  `packaging/appimage/`; build shape and glibc-2.28 floor in
  `docs/10-packaging.md` § AppImage. The primary channel for distros that do
  not carry Perch in their repos. [M]
  **Layman:** You download one file, double-click it, and Perch runs — nothing else to install
  Kind: package.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0002] **Publish the packaging recipes so they are actually installable.**
  Flathub (`packaging/flathub/`), AUR (`packaging/aur/`) and KDE Store
  (`packaging/kde-store/`). The manifests exist; this is the submission and
  review round-trip. [M]

  AUR is deferred (2026-07-18) pending the maintainer completing AUR account
  setup — the post-registration confirmation step (SSH-key / email code) fails
  to load on the AUR site. The `packaging/aur/` PKGBUILDs stay CI-validated and
  ready; only the `git push` to the AUR remote waits. Flathub and KDE Store are
  unaffected.
  **Layman:** Getting Perch listed in the places people normally install Linux software from
  Kind: package.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

---

- 📋 [PERC-0033] **test_export_writes_current_config_file never calls the export code.**
  tests/ui/test_import_export_pane.py::test_export_writes_current_config_file
  hand-copies config.toml to a target path and then asserts the copy equals the
  source. It never invokes ImportExportPage._on_export, so it cannot fail for any
  defect in the export path -- a truism dressed as coverage.

  _on_export takes its target from QFileDialog.getSaveFileName, so a test has to
  monkeypatch that (the sibling import tests already monkeypatch QMessageBox the
  same way) and then assert the written file matches the on-disk config.

  Until this lands, docs/02-state-format.md § Round-trip criterion states that the
  export half is manually verified only; fix that sentence in the same change.
  **Layman:** One of our tests claims to check the Export button but only copies a file itself, so the button could be broken and the test would still pass.
  Kind: test.
  Source: in-session-2026-08-27 while settling PERC-0032.

- 📋 [PERC-0034] **Give local_CI.sh a --docs mode so a docs-only push does not run the full suite.**
  The machine-wide pre-push hook detects a documentation-only push and says so:

    pre-push: documentation-only push, but ./local_CI.sh has no documentation
    mode - running all of it
      (give it one, then: git config ants.gate.docsMode --docs)

  So today every docs push pays the full gate (ruff, mypy, intent-dispatch
  audit, 806 pytest tests, and the whole packaging block) to validate prose.

  Two halves, and the second is the one that is easy to get wrong. Add a
  --docs flag to local_CI.sh running the documentation-touching checks only,
  then set the two git config keys the hook reads: ants.gate.docsMode --docs
  and ants.gate.docsGlob. The glob is not optional -- untold, the hook falls
  back to an extension list that ~/.claude/standards/commits.md 4.2 forbids,
  so a repo that sets only docsMode has not satisfied the rule.

  Decide what counts as documentation here before writing the glob. docs/**,
  README.md, CHANGELOG.md and ROADMAP.md are clear. data/ metainfo is NOT --
  appstreamcli validates it in the gate, so it is a code path wearing an XML
  extension.

  Not urgent: the full gate is ~4s of pytest plus the packaging checks, so
  this buys convenience rather than correctness.
  **Layman:** Pushing a documentation change currently runs every test, which is slow for no benefit.
  Kind: chore.
  Source: in-session-2026-08-27, prompted by the pre-push hook's own hint.

## v1.1 — Onboarding & robustness

Goal: fewer first-run support tickets; the config is safe.

- 📋 [PERC-0003] **First-run setup wizard.**
  Detect the compositor, verify the tray works (prompt to install the
  AppIndicator extension on GNOME Wayland, per the tray-visibility risk in
  `docs/11-roadmap.md`), confirm autostart. [M]
  **Layman:** A short guided setup the first time you run Perch, so it works before you touch any settings
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0004] **Zero-config first-run screen.**
  The wizard opens by stating the one thing that matters: just move your
  windows where you like them — Perch remembers, no rules or layouts required.
  Perch grew more capable than first envisioned (rules engine, layouts,
  per-monitor profiles, snap presets); this keeps that power opt-in rather than
  front-and-centre, so the complexity only surfaces for users who go looking
  for it. [S]
  **Layman:** The first thing Perch tells you is that you do not have to configure anything
  Kind: ux.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0005] **Guided "create your first rule / layout" flows.**
  Promote the existing point-of-need affordances ("Add rule from this window…",
  "Save current as new layout…" in `docs/08-ui.md` § Menu structure) into
  optional one-time walkthroughs, offered from the first-run wizard and
  re-discoverable from the config dialog. Teaches the complex features by
  doing, at the moment the user wants them, instead of a manual nobody reads.
  Pairs with PERC-0010 as the "see why it did that" half of the same onboarding
  story. [M]
  **Layman:** Optional walkthroughs that teach the advanced features at the moment you reach for them
  Kind: ux.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0006] **Config backup / restore points.**
  Snapshot the config on each write and offer "revert to a previous version" in
  the dialog; guards the window-memory data against a bad edit or a crash
  mid-write. [M]
  **Layman:** If a settings change goes wrong, you can roll back to how it was
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0007] **Monitor hotplug re-apply.**
  On output add/remove (dock / undock), re-resolve and re-place managed windows
  automatically. [M]
  **Layman:** Plug in or unplug a monitor and your windows rearrange themselves without you asking
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0008] **Self-update for the AppImage and the Windows installer.**
  Perch checks for a newer release, downloads it in the background, then
  closes, swaps itself in place and relaunches (AppImage: zsync delta via the
  AppImageUpdate mechanism; Windows: download plus installer handoff). For
  store-managed installs (Flatpak / RPM / AUR) Perch does not self-update — it
  detects the managed channel and only notifies, so it never fights the system
  package manager. [L]
  **Layman:** Perch can update itself, except where your system's software manager already owns that job
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0009] **Runtime theme-change propagation.**
  Global re-apply without a restart. Referenced from `docs/08-ui.md`
  § Interaction. [S]
  **Layman:** Switch your desktop theme and Perch follows immediately instead of after a restart
  Kind: enhancement.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0010] **Explain last placement.**
  Surface a plain-language "why did this window land here?" answer in the UI
  (right-click a managed window → Explain placement): the matched rule, the
  active profile, the resolved monitor/desktop, and the last-seen fallback when
  no rule matched. The GUI companion to PERC-0016 and to the observability
  hooks in `docs/07-rules-engine.md` § Debugging and observability; turns a
  "why did it do that?" support ticket into a self-serve answer. [M]
  **Layman:** Right-click a window and Perch tells you, in plain words, why it put it there
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- ✅ [PERC-0011] **Pause Perch — full panic toggle replacing the narrow "Pause restore".**
  Done 2026-07-18. Broadened the existing narrow toggle (which suppressed only
  the last-seen auto-restore and let rules and layouts keep moving windows)
  into a full off-switch: while paused the reducer's `_execute` drops every
  placement decision — rules, layouts and last-seen restore — so no window is
  moved automatically. Manual "Snap focused" still applies (it bypasses the
  reducer); unpausing does not retroactively rearrange. Renamed the
  `TogglePauseRestore` intent → `TogglePause` and `toggle_pause_restore()` →
  `toggle_pause()`. Contract in `docs/08-ui.md` § Menu structure; locked by
  `tests/core/test_reducer.py` and `tests/ui/test_tray.py`. [S]
  **Layman:** One switch that stops Perch moving anything at all, for when you want it out of the way
  Kind: feature.
  Source: in-session 2026-07-18.

- ✅ [PERC-0012] **Fix tray snap-preset translations.**
  Done 2026-07-18. The tray snap labels in `src/perch/ui/tray.py` were marked
  with bare `QT_TR_NOOP` (empty context) but looked up under context
  `perch.ui.tray`, so their translations never resolved. Migrated to
  `QT_TRANSLATE_NOOP("perch.ui.tray", …)` and regenerated
  `translations/perch_en.ts`, which was stale project-wide — the re-extraction
  also picked up the M3…M9 strings that had never been re-scanned. Locked by
  `tests/test_translations.py`. See `docs/accessibility-i18n-standards.md`
  § Marking strings. [S]
  **Layman:** The tray menu's snap options now show up in your own language instead of always in English
  Kind: fix.
  Source: in-session 2026-07-18.

---

- ✅ [PERC-0031] **State what "your config survives a reinstall or a new machine" actually means.**
  Found by an adopt-project cold read, 2026-08-26. Export / import is one of
  the nine v1 goals in docs/00-overview.md and is repeated in README.md, and it
  is the only one of them with no written sign of success anywhere in the docs.
  What exists (docs/02-state-format.md, docs/08-ui.md) describes the buttons and
  the file operations, which is a specification of the mechanism, not a criterion
  for the outcome.

  What is needed is a round-trip condition: a config exported on machine A and
  imported on machine B yields the same placements for the same windows -- or a
  named class of thing that must come across and a named class that need not.

  This is the single reason the project reads as workflow.md state 1 rather than
  state 2, despite v1.0.0 having shipped. Every other stated goal has a bar
  somewhere, several of them in docs/testing/*.md.
  Resolved (2026-08-27): docs/02-state-format.md § Export / import gains a Round-trip criterion naming three classes -- what must come across (all of config.toml), what need not (state.json: last-seen geometries, active profile/layout), and what comes across but stays inert until the hardware matches (monitor names in rules/layouts, profile topology strings). Coverage is stated honestly: the import half has tests, the export half has none that call _on_export (filed as PERC-0033).
  **Layman:** Perch promises your settings survive moving to a new computer, but nowhere says what counts as having survived.
  Kind: doc.
  Source: adopt-project cold read 2026-08-26.

- ✅ [PERC-0032] **docs/02-state-format.md and docs/08-ui.md disagree about what Export actually exports.**
  Found by an adopt-project cold read, 2026-08-26. The two documents describe
  the same button differently, and the difference is the substantive one.

  docs/02-state-format.md, Export / import: "A separate 'Include last-seen
  geometries' checkbox lets power users export state too, if they want to
  pre-seed a new machine."

  docs/08-ui.md, Sections item 8: the Export button "copies the current on-disk
  config.toml to the chosen path" -- no checkbox mentioned.

  So it cannot be settled from the docs whether last-seen geometries, which are
  literally where your windows were, travel with an export at all. Settle it
  against the shipped code and fix whichever document is wrong. Blocks the
  criterion in the sibling item, since that criterion has to say whether
  geometries are in scope.
  Resolved (2026-08-27): settled against src/perch/ui/dialog.py ImportExportPage._on_export, which reads config.toml and writes it verbatim to the chosen path -- no checkbox, no state.json. docs/08-ui.md was correct; docs/02-state-format.md was wrong and internally contradictory (its Export bullet already said state.json is excluded). Removed the checkbox sentence.
  **Layman:** Two of our own documents describe the Export button differently, and neither can be trusted until we check the code.
  Kind: doc-fix.
  Source: adopt-project cold read 2026-08-26.

## v1.2 — Smarts

Goal: Perch learns instead of only obeying.

- 📋 [PERC-0013] **Learn mode.**
  Observe where windows actually land over time and offer to promote a
  recurring pattern into a rule. Builds on the topology-scoped last-seen idea
  ("remember this arrangement per topology automatically") tracked in
  `docs/09-layouts-profiles.md`. [L]
  **Layman:** Perch notices habits and offers to make them permanent, instead of waiting for you to write a rule
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0014] **CLI frontend for scripting.**
  `perch apply coding`, `perch snap left-half`. Referenced from
  `docs/06-backend-stubs.md` § Sway / Hotkeys and `docs/08-ui.md` § Hotkeys as
  the self-grabbed-hotkey fallback for compositors that do not expose a hotkey
  API. [M]
  **Layman:** Drive Perch from a terminal or a script, not only from the tray menu
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0015] **Activity-scoped rules.**
  Rules that apply only within a given KDE Activity. [M]
  **Layman:** Different window rules for different KDE Activities
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0016] **`perch --test-rules <config.toml>` replay tool.**
  Replays a saved event stream against a config for rules-engine regression
  testing. Referenced from `docs/07-rules-engine.md` § Debugging and
  observability. [S]
  **Layman:** A way to check a rules file behaves as intended without moving any real windows
  Kind: test.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0017] **Shareable layouts.**
  Export a single named layout to a portable `.perch-layout` file and import
  someone else's — distinct from the whole-config Export / Import pane
  (`docs/08-ui.md` § Import / Export), which ships the entire `config.toml`.
  Lets users pass one layout around ("here's my ultrawide coding setup")
  without exposing the rest of their config — rules, hotkeys, profiles. Builds
  on named layouts in `docs/09-layouts-profiles.md`. [M]
  **Layman:** Send one window arrangement to a friend without handing over all your other settings
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

---

## v2.0 — Wayland-native

Goal: one backend for the wlroots family instead of four hand-written stubs.

- 📋 [PERC-0018] **Backend built on the standard Wayland protocols.**
  `ext-foreign-toplevel-list` for enumeration plus the maturing placement
  protocols, working across wlroots compositors — promoting the Sway and
  Hyprland stubs, and where the protocol reaches the Mutter/GNOME stub, from
  stub to real support. [XL]
  **Layman:** One properly supported backend for several Wayland desktops, instead of four partial ones
  Kind: implement.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0019] **Publish the GNOME Shell extension to extensions.gnome.org.**
  For the parts that still need an extension. [L]
  **Layman:** GNOME users can install the piece Perch needs from the normal GNOME extensions site
  Kind: package.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 📋 [PERC-0020] **`docs/contributing-backend-mutter.md`.**
  GJS conventions, per-GNOME-branch policy and the release-to-EGO checklist.
  Owned by the first community contributor to take the Mutter stub to a full
  backend. Referenced from `docs/06-backend-stubs.md` § Contributor path. [M]
  **Layman:** Written instructions for whoever takes on full GNOME support
  Kind: doc.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

---

## Windows edition — separate track

Perch does not run on Windows today: the backends depend on `sdbus` (Linux
system bus) and `python-xlib` (X11), and there is no Win32 backend. But the
core (tray, rules, memory, UI) is OS-agnostic and Qt already runs on Windows,
so a port is a self-contained new backend, not a rewrite. It roughly doubles
the platform surface to maintain forever — a cost the maintainer has explicitly
accepted: a Windows edition is a committed goal (maintainer request,
2026-07-18), scheduled after the Linux v1.x line stabilises. Its published
installer is bound by ground rule 6 in `docs/11-roadmap.md` — fully
self-contained, zero dependencies for the user, the same bar as the Linux
AppImage.

- 📋 [PERC-0021] **`WindowBackend` implementation over the Win32 API.**
  Enumerate / move / resize / virtual desktop. [XL]
  **Layman:** The piece that lets Perch actually control windows on Windows
  Kind: implement.
  Source: maintainer request 2026-07-18.

- 📋 [PERC-0022] **Windows hotkeys, signed installer and Windows CI runners.**
  Global hotkeys via `RegisterHotKey`, a signed `.msi` / `.exe` installer, and
  Windows CI. The installer must be fully self-contained — the same
  zero-dependency bar as the Linux AppImage: the user installs one thing and
  runs it, with the Python runtime and Qt bundled, never a separate
  Python/PySide6 install. [L]
  **Layman:** A normal Windows installer that brings everything with it
  Kind: package.
  Source: maintainer request 2026-07-18.

- 📋 [PERC-0023] **Windows self-update via the installer handoff.**
  The Windows half of PERC-0008. [M]
  **Layman:** Perch updates itself on Windows too
  Kind: feature.
  Source: maintainer request 2026-07-18.

---

## Someday / unscheduled

- 💭 [PERC-0024] **D-Bus service interface for external triggers.**
  **Layman:** Let other programs tell Perch to do things
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0025] **Headless daemon mode for minimal window managers.**
  **Layman:** Run Perch with no tray icon, for desktops that have no tray
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0026] **Enforcement mode per rule — pin a window, fight user drags.**
  **Layman:** An option to keep a window pinned even if it gets dragged away
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0027] **Full Plasma 5 support.**
  Out of v1 scope; the KWin backend refuses Plasma below 6 today, per
  `docs/05-backend-kwin.md`.
  **Layman:** Support for the older KDE Plasma 5 desktop
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0028] **Config sync across machines.**
  **Layman:** Your Perch settings follow you to another computer
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0029] **Accessibility pass on the config dialog.**
  **Layman:** Make the settings window work well with screen readers and keyboard-only use
  Kind: accessibility.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- 💭 [PERC-0030] **Docs / marketing site for discoverability.**
  **Layman:** A website so people can find Perch in the first place
  Kind: marketing.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).
