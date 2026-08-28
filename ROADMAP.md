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
  Progress (2026-08-27): Flathub is now submission-ready and nothing has
  been submitted. The manifest could not be built by anyone before this --
  it based on the PyQt base app for a PySide6 application, pinned a KDE
  runtime eight months stale, and shipped its dependency includes commented
  out and uncommitted. Now io.qt.PySide.BaseApp//6.11 on
  org.kde.Platform//6.11, with the closure sha256-pinned and committed;
  verified by a real offline build of the submission manifest (commit
  e1de021). flatpak-builder-lint: 6 finish-args errors down to 3, and the
  3 survivors are load-bearing (KWin talk-name, the two filesystem paths)
  and carry written justifications in the PR body.

  REMAINING before the Flathub PR: (1) the manual live-Plasma checks a
  headless build cannot make -- tray icon, KWin script mirroring to
  ~/.local/share/kwin/scripts/ at first run, geometry restore, config
  dialog; (2) open the flathub/flathub PR against the new-pr branch, an
  outward-facing action awaiting user go-ahead.

  Scope decision (user, 2026-08-27): Fedora COPR is DROPPED -- OBS builds
  Fedora RPMs from the same spec, so COPR was a second pipeline for one
  artefact.

  Other channels unchanged: OBS is ready and the osc account is
  authenticated but nothing has been pushed; AUR stays blocked on the
  maintainer's account confirmation; KDE Store is a manual web listing that
  wants the Flathub build to be public first.
  Progress (2026-08-27, later): OBS is LIVE at home:milnet:perch (subproject,
  matching the ants-terminal / finbreak convention -- the docs' old
  "home:milnet01/perch" was wrong on both the account name and the shape).
  Repositories: openSUSE_Tumbleweed and Fedora_44, x86_64.

  Fedora_44 BUILDS GREEN: perch-1.0.0-7.1.noarch.rpm. openSUSE_Tumbleweed
  was still failing 50-check-filelist as of revision 7; revision 8 adds
  BuildRequires: hicolor-icon-theme (the check runs against the build root,
  so a runtime Requires does not satisfy it) and its result was NOT seen.
  CHECK IT FIRST next session: osc results home:milnet:perch perch

  Six real spec/tooling bugs were found and fixed by doing this, none of
  which any local check could have caught -- rpmspec -P passed throughout:
    1. obs.sh looked for ~/.oscrc; osc uses ~/.config/osc/oscrc, so the
       script refused to run at all.
    2. obs.sh targeted home:<user>/perch, not the subproject.
    3. _service was unusable: obs_scm mode="manual" never ran server-side
       ("no .obsinfo file found"), and ANY buildtime service pulls
       obs-service-* into the build root, where Fedora could not resolve
       wget. Deleted; obs.sh now uploads the release tarball instead.
    4. BuildRequires: appstream-glib / libxml2-tools were unguarded
       openSUSE names. Now %if-guarded (libappstream-glib on Fedora);
       libxml2-tools dropped as unused. Requesting it by path was tried and
       REVERTED -- OBS does not index /usr/bin file provides, and it broke
       both targets.
    5. %build carried a comment naming %pyproject_wheel unescaped. rpm
       expands macros in scriptlet comments, so the comment CALLED the
       macro with the sentence as arguments.
    6. %{_metainfodir} is Fedora-only and undefined on openSUSE.

  The Flathub PR is NOT open and must not be opened -- blocked by PERC-0036,
  found by running the built Flatpak on this live KDE Wayland session.
  Resolved for OBS (2026-08-27): BOTH targets build green at revision 8 --
  perch-1.0.0-8.1.noarch.rpm on openSUSE_Tumbleweed AND Fedora_44. The
  BuildRequires: hicolor-icon-theme was the last fix; the note above saying
  Tumbleweed's result was unseen is superseded.

  Not yet done for OBS: publishing the repository (the project builds but
  has not been announced), and a README install section pointing at
  https://software.opensuse.org//download.html?project=home%3Amilnet%3Aperch&package=perch
  once the user is happy to advertise it.

  Channels remaining on this item: Flathub (blocked, PERC-0036), AUR
  (blocked on the maintainer's account), KDE Store (manual web listing,
  wants Flathub live first).
  Progress (2026-08-27, OBS advertised): user decision -- announce the OBS
  repo now rather than waiting for Flathub. README's "Download & run" now
  carries an "openSUSE and Fedora: install the RPM" section with real
  zypper / dnf commands.

  Verified before advertising, so the README does not point at a dead
  link: both repositories return HTTP 200 and serve
  perch-1.0.0-8.1.noarch.rpm with repodata, and both .repo files fetch
  clean. NOT used: the software.opensuse.org one-click download page --
  it returns HTTP 403 even with a browser User-Agent, so the README links
  the download.opensuse.org .repo files directly, which is what the
  one-click page would have handed over anyway. Worth a look if that page
  is meant to work for this project.

  Also corrected in docs/10-packaging.md: the OBS project was recorded as
  "home:milnet01/perch" in two places, wrong on both the account name and
  the subproject shape. It is home:milnet:perch.

  Flathub status: PERC-0036, PERC-0038, PERC-0039 and PERC-0040 are all
  fixed and verified on a live Plasma Wayland session, so the tray icon,
  its menu and the KWin script all work in the sandbox now. Of the manual
  checks this item lists, two remain and both need a human at the screen:
  geometry remembered across a close/reopen, and the config dialog opening
  and saving. The PR is still not open.
  Progress (2026-08-27, build refreshed): the installed local Flatpak was
  rebuilt from HEAD after the PERC-0037 fix landed, so the manual checks
  below now run against code that includes it. Verified by finding
  _await_portal_response in the installed
  files/lib/python3.13/site-packages/perch/autostart.py; build + smoke
  green (perch --version, --check-config, sandbox imports).

  The manual list is unchanged and still needs a human at the screen:
  geometry remembered across a close/reopen, and the config dialog opening
  and saving. Worth a third glance while there, though it gates nothing:
  ticking "start Perch at login" now reaches the Background portal
  correctly, and the portal shows a one-time permission prompt.

  The Flathub PR is still not open and must not be opened before those
  checks.
  Progress (2026-08-27, build refreshed again): rebuilt from HEAD after the
  PERC-0003 / PERC-0004 wizard landed, so the installed local Flatpak carries
  both that and the PERC-0037 autostart fix. Verified by finding
  ui/onboarding.py in the installed site-packages; build + smoke green.

  The manual pass is now THREE checks, not two, and one run covers all of
  them. The setup wizard fires on the next Flatpak launch by itself: the
  sandbox config has no onboarding_completed key, and an absent key parses as
  false. So:
    1. the wizard opens, its three rows read sensibly, and Finish does not
       bring it back on the launch after;
    2. a window's geometry is remembered across a close/reopen;
    3. the config dialog opens and saves.
  Ticking "start Perch at login" in the wizard is worth a fourth glance -- it
  should now reach the Background portal and show a one-time permission
  prompt -- but it gates nothing.

  The Flathub PR is still not open and must not be opened before those
  checks.
  Progress (2026-08-28, 1.1.0 release cut): two pieces of shipped work were
  split out of this item so the 1.1.0 CHANGELOG could cite closed ids
  rather than claiming this one had shipped. PERC-0041 takes the OBS /
  RPM channel (live and advertised for openSUSE Tumbleweed and Fedora);
  PERC-0042 takes the Flathub manifest (builds offline, submission-ready).

  This item stays PLANNED and is now scoped to the SUBMISSIONS alone:
  the Flathub PR (still blocked on the three manual live-Plasma checks),
  AUR (blocked on the maintainer's account confirmation) and the KDE
  Store (manual web listing, wants Flathub live first).

  The three manual checks are unchanged and still need a human at the
  screen: the setup wizard opens and does not reappear after Finish, a
  window's geometry survives a close/reopen, and the config dialog opens
  and saves.
  **Layman:** Getting Perch listed in the places people normally install Linux software from
  Kind: package.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

---

- ✅ [PERC-0033] **test_export_writes_current_config_file never calls the export code.**
  tests/ui/test_import_export_pane.py::test_export_writes_current_config_file
  hand-copies config.toml to a target path and then asserts the copy equals the
  source. It never invokes ImportExportPage._on_export, so it cannot fail for any
  defect in the export path -- a truism dressed as coverage.

  _on_export takes its target from QFileDialog.getSaveFileName, so a test has to
  monkeypatch that (the sibling import tests already monkeypatch QMessageBox the
  same way) and then assert the written file matches the on-disk config.

  Until this lands, docs/02-state-format.md § Round-trip criterion states that the
  export half is manually verified only; fix that sentence in the same change.
  Resolved (2026-08-27): the test stubs QFileDialog.getSaveFileName and
  QMessageBox.information, calls _on_export, and asserts the written file
  is byte-identical to the on-disk config -- a marker comment proves the
  copy is verbatim rather than re-serialised. Confirmed falsifiable by
  mutating the write in _on_export. docs/02-state-format.md
  § Round-trip criterion's Coverage sentence updated in the same commit
  (3612e1e).
  **Layman:** One of our tests claims to check the Export button but only copies a file itself, so the button could be broken and the test would still pass.
  Kind: test.
  Source: in-session-2026-08-27 while settling PERC-0032.

- ✅ [PERC-0034] **Give local_CI.sh a --docs mode so a docs-only push does not run the full suite.**
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
  Resolved (2026-08-27): local_CI.sh gained --docs, ci.yml gained a third
  "docs" job, and both git config keys are set (docsMode --docs, docsGlob
  'docs/*.md|*.md|LICENSE'). A docs push now costs ~0.07s against ~25s.

  The item's premise needed correcting: nothing in the gate read a docs
  path, so "the documentation-touching checks only" was an empty set. The
  new tools/docs_check.py supplies the content -- relative links and
  #anchors resolve, and retired or forbidden strings stay inside the
  documents that record them. Both checks confirmed falsifiable by seeding
  a broken link, a bad anchor and a retired symbol.

  Two of /perch-docs-check's greps were deliberately not ported: the
  future-tense scan needs the roadmap's milestone state, and the
  swapped-library grep matches eight files here, all of them correct
  rationale -- allow-listing them would leave a check that cannot fail.
  Both stay in the skill, which the gate now names as its wider half.

  Commit 419b660.
  **Layman:** Pushing a documentation change currently runs every test, which is slow for no benefit.
  Kind: chore.
  Source: in-session-2026-08-27, prompted by the pre-push hook's own hint.

- ✅ [PERC-0036] **Flatpak writes the KWin script inside the sandbox, so KWin never sees it.**
  BLOCKS the Flathub submission (PERC-0002). Do not open that PR until this
  is fixed.

  Observed 2026-08-27 by running the built Flatpak on a live KDE Wayland
  session. The script landed at
  ~/.var/app/io.github.milnet01.Perch/data/kwin/scripts/org.milnet01.perch
  and the host path ~/.local/share/kwin/scripts/org.milnet01.perch was
  untouched (still dated 2026-04-21, from the native install).

  Cause: inside a Flatpak, XDG_DATA_HOME is redirected to
  ~/.var/app/<id>/data. KWinBackend derives the mirror target from
  XDG_DATA_HOME, so it writes to the sandbox. KWin runs on the HOST and
  cannot read that path -- which is the exact failure
  docs/10-packaging.md § "KWin script delivery from Flatpak" says the
  mirroring exists to avoid. The manifest's
  --filesystem=xdg-data/kwin/scripts:create makes the HOST directory
  writable, and the code never uses the host path, so the grant is
  correct and unused.

  Likely fix: detect Flatpak (/.flatpak-info exists) and resolve the
  mirror target to Path.home()/".local/share/kwin/scripts" rather than
  XDG_DATA_HOME. Needs a test that fails when the path resolves inside
  the sandbox, and a re-run on a live Plasma session -- a headless build
  cannot see this.

  Related, same run, smaller: config also goes to the sandbox
  (~/.var/app/.../config/perch), NOT ~/.config/perch. So
  --filesystem=xdg-config/perch:create does not do what the manifest
  comment claims (sharing one config with a native install) and should be
  dropped -- flatpak-builder-lint already flags it as unnecessary, and
  this run shows why it is right.
  Progress (2026-08-27): fix written and unit-tested, live re-verify still
  owed. target_dir() now resolves from $HOME when /.flatpak-info is
  present, so the mirror lands on the host where KWin can read it; the
  probe moved to perch.paths.is_flatpak() and autostart delegates to it.
  Two tests in tests/backend/kwin/test_install.py cover it, the first
  confirmed failing against the old resolution before the fix landed.
  Docs updated in the same change (05-backend-kwin.md, 10-packaging.md,
  02-state-format.md, the manifest, SUBMISSION.md, submit/flathub.sh).
  The config half is done too: --filesystem=xdg-config/perch:create is
  dropped, and every place that claimed it shared a config with a native
  install now says the Flatpak keeps its own.
  Outstanding, and the reason this is not shipped: rebuild the Flatpak
  and confirm on a live Plasma Wayland session that the script appears at
  ~/.local/share/kwin/scripts/org.milnet01.perch and that KWin loads it.
  A headless run cannot see this. The Flathub PR stays shut until then.
  Resolved (2026-08-27). Verified on a live Plasma Wayland session with a
  LOCAL flatpak-build.sh build of commit c76db7e. Both paths were emptied
  first so the mirror had to prove itself:
    installing KWin script v1.1.2 to
      /home/ants/.local/share/kwin/scripts/org.milnet01.perch
    loaded KWin script org.milnet01.perch as id=0
    KWin script ready (version='1.1.2')
  KWin on the host loaded it, which is the end-to-end proof a headless
  build cannot give. ~/.var/app/io.github.milnet01.Perch/data/kwin was
  never recreated.
  The config half shipped too: --filesystem=xdg-config/perch:create is
  gone from the manifest, and SUBMISSION.md, submit/flathub.sh and
  docs/02-state-format.md no longer claim the Flatpak shares a config
  with a native install.
  The same run surfaced an unrelated defect, filed as PERC-0037:
  portal_set_autostart() treats RequestBackground's return as the result
  dict when it is the Request object path, so Flatpak autostart raises.
  It does not block the Flathub submission -- autostart simply does not
  take effect.
  **Layman:** Installed as a Flatpak, Perch cannot control windows on KDE — the helper it gives KDE is saved somewhere KDE cannot read
  Kind: fix.
  Source: in-session-2026-08-27, live Plasma Wayland run of the built Flatpak.

- ✅ [PERC-0037] **Flatpak autostart raises: RequestBackground's return is read as the result.**
  Observed 2026-08-27 running the Flatpak on a live session:

    Task exception was never retrieved
    File ".../perch/autostart.py", line 170, in portal_set_autostart
      granted = bool(result.get("autostart", False))
    AttributeError: 'str' object has no attribute 'get'

  org.freedesktop.portal.Background.RequestBackground returns the object
  path of a Request handle, not the result. The result arrives later on
  that Request's Response signal, as (uint32 response, a{sv} results).
  portal_set_autostart treats the return value as the result dict, so
  every Flatpak autostart call raises before it can read `autostart`.

  The same file's hotkey sibling already does this correctly --
  PortalGlobalShortcutsProvider correlates per-Request Response signals
  (see the M8.e CHANGELOG entry) -- so the pattern to follow is in-tree.

  Effect: autostart silently never takes effect under Flatpak, and the
  task dies unretrieved rather than logging a warning. Does NOT block the
  Flathub submission.

  Needs a test that fails when the return value is treated as a mapping,
  and a live re-run: the portal shows a permission prompt on first call.
  Resolved (2026-08-27). portal_set_autostart now takes the object path
  RequestBackground returns, subscribes to that Request's Response signal
  and reads `autostart` from the results dict, unwrapping the a{sv}
  variants. It returns whether autostart was granted, and logs a warning
  on a refusal, a non-zero response code or a timeout (300 s, generous
  because the response only arrives once the user has answered the
  permission dialog). The proxy's result signature was "a{sv}" and is now
  "o", which is what the interface actually declares.

  Pattern copied from PortalGlobalShortcutsProvider as planned; the
  Response correlation and a four-line variant unwrapper are duplicated
  rather than shared, because this module keeps its sdbus import lazy so
  `sync` imports on a box with no sdbus build.

  Verified: against the pre-fix source the same call raises
  AttributeError: 'str' object has no attribute 'get' -- the traceback
  this item recorded -- and 8 of the autostart tests fail; after the fix
  all 20 pass and local_CI.sh is green (803 passed, 16 skipped). Four new
  tests lock the behaviour: the Response is awaited on the path the portal
  handed back, a denied grant, a non-zero response code, and a timeout.

  Not done: the live re-run in the Flatpak. It needs a human to answer the
  portal's permission prompt, so it is grouped with the two eyeball checks
  PERC-0002 still lists.
  **Layman:** Ticking "start Perch at login" does nothing in the Flatpak build
  Kind: fix.
  Source: in-session-2026-08-27, live Plasma Wayland run of the PERC-0036 Flatpak build.

- ✅ [PERC-0038] **Flatpak has no talk-name for StatusNotifierWatcher, so the tray never registers.**
  BLOCKS the Flathub submission (PERC-0002).

  Observed 2026-08-27, Flatpak on a live Plasma session:
    WARNING perch.app: no StatusNotifierHost detected; tray icon may be
      invisible
    WARNING perch.qt: KDE platform plugin is loaded but SNI unavailable

  Proved from inside the sandbox -- a QDBusInterface call to
  org.kde.StatusNotifierWatcher returns
  org.freedesktop.DBus.Error.ServiceUnknown, while `busctl --user list`
  on the host shows kded6 owning that exact name. The manifest grants
  talk-names for org.kde.KWin, org.kde.kglobalaccel and
  org.freedesktop.Notifications only, so xdg-dbus-proxy filters the
  watcher out. Perch can neither probe for a host nor register its item.

  A native run of the same code on the same session logs none of these
  warnings, which rules out the session.

  Fix: add --talk-name=org.kde.StatusNotifierWatcher to finish-args and
  justify it in SUBMISSION.md -- for a tray-only application the tray is
  the entire interface, so this is load-bearing rather than a preference.
  Re-run flatpak-builder-lint afterwards.

  Separate second cause of the same symptom: PERC-0039.
  Resolved (2026-08-27). --talk-name=org.kde.StatusNotifierWatcher added
  and justified in SUBMISSION.md and the PR body. Verified on a live
  Plasma Wayland session with a LOCAL build: the watcher's
  RegisteredStatusNotifierItems gained an entry while Perch ran, and that
  item answers Id="perch", Status="Active", with its menu at /MenuBar
  listing the real entries (Layouts, Snap focused window, Pause Perch,
  Reapply rules now). Both startup warnings are gone.
  **Layman:** Installed as a Flatpak, Perch's tray icon never appears — and the tray is the whole interface
  Kind: fix.
  Source: in-session-2026-08-27, live Plasma Wayland run of the Flatpak.

- ✅ [PERC-0039] **Tray icons resolve to a dev-checkout path, so installed layouts get a null icon.**
  BLOCKS the Flathub submission (PERC-0002), and is NOT Flatpak-specific.

  Observed 2026-08-27, Flatpak on a live Plasma session:
    WARNING perch.qt: QSystemTrayIcon::setVisible: No Icon set

  perch.ui.icons.load_tray_icons tries QIcon.fromTheme first and falls
  back to _bundled_icon_dir(), which is
  Path(__file__).resolve().parents[3] / "data/icons/hicolor/symbolic/status".
  That arithmetic is correct for a dev checkout (src/perch/ui -> repo
  root) and wrong for every installed layout: from
  /app/lib/python3.13/site-packages/perch/ui it yields
  /app/lib/python3.13/data/..., which does not exist.

  Measured on this machine, both lookups fail in the Flatpak even though
  the three SVGs ARE installed at
  /app/share/icons/hicolor/symbolic/status/, so the theme lookup is not
  covering for the broken fallback. QIcon.hasThemeIcon returns False for
  all three names on a real Plasma session with breeze-dark, so
  load_tray_icons()'s docstring claim that the theme lookup succeeds on
  packaged installs is unverified at best.

  Suggested fix: also try sys.prefix/share/icons/hicolor/symbolic/status,
  which resolves under Flatpak (/app), an RPM (/usr) and a venv install,
  keeping the existing dev-checkout path. Needs a test that fails when
  the package is imported from a site-packages-shaped layout.

  Check the AppImage and the RPM for the same symptom before closing --
  the dev checkout is the only layout the current code gets right.
  Resolved (2026-08-27), on the second attempt. The first fix used
  sys.prefix and did NOT work: inside a Flatpak the interpreter comes from
  the runtime, so sys.prefix is /usr while Perch's data is under /app --
  measured in the sandbox, /usr/share/icons/hicolor/symbolic/status absent
  and /app/share/... present. The lookup now walks XDG_DATA_DIRS plus
  XDG_DATA_HOME, with the dev checkout last.
  Verified in the sandbox: load_tray_icons() returns three non-null icons
  resolved from /app/share/icons/hicolor/symbolic/status, and the
  "QSystemTrayIcon::setVisible: No Icon set" warning is gone from a live
  run. Regression test simulates the installed layout and was confirmed
  failing without the fix.
  Still worth checking, and NOT done here: whether the AppImage and the
  RPM had the same symptom. The dev checkout was the only layout the old
  code got right, so both are suspect.
  **Layman:** The tray icon file is looked for in a folder that only exists when running from the source code
  Kind: fix.
  Source: in-session-2026-08-27, live Plasma Wayland run of the Flatpak.

- ✅ [PERC-0040] **The SNI host probe opens the wrong bus, so it always fails under Flatpak.**
  Found 2026-08-27 while fixing PERC-0038, by running perch.ui.sni_probe
  inside the sandbox:

    SdBusLibraryError: sd_bus_open(...) returned error number: 2

  _sdbus_probe let sdbus pick the default bus. Inside a Flatpak
  DBUS_SESSION_BUS_ADDRESS is unix:path=/run/flatpak/bus and the default
  open returns ENOENT. sni_host_available catches every exception and
  classifies it as "no host", so the failure is silent by design and
  Perch reports no StatusNotifierHost on a session that has one --
  IsStatusNotifierHostRegistered reads true on the host bus, and
  sd_bus_open_user() inside the same sandbox reaches it fine.

  Consequences, in order of severity: on GNOME Wayland the wrong branch
  fires the "install the AppIndicator extension" first-run dialog at users
  who need no such thing; everywhere else it is a spurious startup
  warning, because app.py creates the tray regardless of a negative probe.

  Fix: sd_bus_open_user() explicitly and pass the bus to both the
  FreedesktopDbus helper and the watcher proxy.

  Note the broad except in sni_host_available is what hid this. It is
  correct to fail closed, but a transport failure and a genuine "no host"
  are not the same answer and only one of them should be quiet.
  Resolved (2026-08-27). _sdbus_probe now calls sd_bus_open_user()
  explicitly and passes that bus to the FreedesktopDbus helper and the
  watcher proxy. Verified inside the sandbox: the old path raised
  SdBusLibraryError (sd_bus_open -> ENOENT) while the explicit open
  returns name_has_owner(org.kde.StatusNotifierWatcher)=True, and the
  "no StatusNotifierHost detected" warning is gone from a live run.
  **Layman:** Perch wrongly decides the desktop has no system tray when it is installed as a Flatpak
  Kind: fix.
  Source: in-session-2026-08-27, live Plasma Wayland run of the Flatpak.

- ✅ [PERC-0041] **OBS repository live for openSUSE Tumbleweed and Fedora, and advertised.**
  Split out of PERC-0002 so the channel that actually shipped carries a
  closed record while its parent stays open for Flathub, AUR and the KDE
  Store. The CHANGELOG for 1.1.0 cites this id rather than PERC-0002,
  which is still planned.

  Shipped: home:milnet:perch on OBS builds green at revision 8 for both
  openSUSE_Tumbleweed and Fedora_44 (perch-1.0.0-8.1.noarch.rpm), and
  README's "Download &amp; run" carries an "openSUSE and Fedora: install the
  RPM" section with real zypper / dnf commands. Both repositories were
  verified serving the RPM with repodata, and both .repo files fetched
  clean, before the link went in.

  Not used: the software.opensuse.org one-click download page, which
  returns HTTP 403 even with a browser User-Agent; the README links the
  download.opensuse.org .repo files directly instead.
  **Layman:** openSUSE and Fedora users can install Perch with a normal package command
  Kind: package.
  Source: split from PERC-0002 at the 1.1.0 release cut (in-session-2026-08-28).

- ✅ [PERC-0042] **The Flathub manifest builds offline and is submission-ready.**
  Split out of PERC-0002 alongside PERC-0041, on the same grounds: the
  manifest work shipped and is verifiable, while the Flathub PR it enables
  has not been opened. PERC-0002 stays open for that submission, for AUR
  and for the KDE Store.

  Shipped: the manifest was based on com.riverbankcomputing.PyQt.BaseApp
  for a PySide6 application, targeted a KDE runtime eight months stale, and
  shipped its dependency includes commented out and uncommitted, so a fresh
  clone could not build it at all. It is now io.qt.PySide.BaseApp//6.11 on
  org.kde.Platform//6.11 with the closure sha256-pinned and committed as
  python3-deps.yaml. Verified by a real offline build (commit e1de021).

  Alongside it: generate-pip-sources.sh regenerates the closure from
  pyproject.toml, flatpak-build.sh reproduces Flathub's build locally and
  smoke-tests the result, flathub.json restricts the buildbot to the arch
  the pinned wheels cover, and packaging/submit/flathub.sh targets the
  new-pr branch rather than master.

  flatpak-builder-lint is down from 6 finish-args errors to 3, and the 3
  survivors are load-bearing (the KWin talk-name and the two filesystem
  paths) with written justifications ready for the PR body.

  NOT shipped, and tracked by PERC-0002: the three manual live-Plasma
  checks and the flathub/flathub PR itself.
  **Layman:** The Flatpak recipe now actually builds, which it never did before
  Kind: package.
  Source: split from PERC-0002 at the 1.1.0 release cut (in-session-2026-08-28).

## v1.1 — Onboarding & robustness

Goal: fewer first-run support tickets; the config is safe.

- ✅ [PERC-0003] **First-run setup wizard.**
  Detect the compositor, verify the tray works (prompt to install the
  AppIndicator extension on GNOME Wayland, per the tray-visibility risk in
  `docs/11-roadmap.md`), confirm autostart. [M]
  Started 2026-08-27. The design already exists and needed none written: docs/08-ui.md § First-run setup wizard specifies the three pages, the one-time `[general] onboarding_completed` flag, the five schema touch-points, the startup control flow and the re-run button. Its code claims were verified against the tree before starting -- `_select_backend` does run after `_maybe_show_appindicator_hint` (the documented reorder is needed), `apply_general` takes four keyword-only args with one production caller in `GeneralPage.commit` plus four test call-sites, `_GENERAL_BOOL_KEYS` is unused, and `sni_probe.is_gnome_wayland` exists. Scope confirmed with the user: PERC-0003 and PERC-0004 only; PERC-0005 stays a hook point.
  Resolved (2026-08-27). Implemented exactly as docs/08-ui.md specified:
  src/perch/ui/onboarding.py holds the three-page QWizard, the pure check_*()
  badge functions and run_setup_wizard; the `[general] onboarding_completed`
  key is carried at the five documented points; app.py selects the backend
  ahead of tray bring-up and gates the wizard on the flag; Settings > General
  gained a "Run setup wizard again..." button.

  Two things the doc did not settle, decided here and written back into it.
  The UI layer may not import perch.backend at runtime (see the package
  docstring), so the compositor map keys on type(backend).__name__ and
  BACKEND_LABELS is public, which lets a test assert one label per real
  backend rather than reaching into a private. And the re-run button re-seeds
  the General page after the wizard writes: that page owns the same "Start at
  login" checkbox, and a stale one would be committed back on the next OK and
  silently revert what the wizard saved.

  Verified: 18 new tests, 821 passing (was 803), local_CI.sh green. Each new
  assertion was proved non-vacuous by mutating one part of the behaviour at a
  time -- writing the flag as false, letting Cancel keep the checkbox, dropping
  a backend label, removing the key from the schema read loop, and clobbering
  the flag on a General save. Each reddened exactly its own test and no other.
  The AppIndicator extension URL was checked live (HTTP 200) before shipping.

  Not covered by a test: the app.py startup gate itself. No test in this repo
  imports perch.app, so covering it means building a harness for main() --
  reported rather than absorbed. It is exercised by the first-run eyeball
  check instead.
  **Layman:** A short guided setup the first time you run Perch, so it works before you touch any settings
  Kind: feature.
  Source: docs/11-roadmap.md Post-v1 ideas (migrated 2026-08-26).

- ✅ [PERC-0004] **Zero-config first-run screen.**
  The wizard opens by stating the one thing that matters: just move your
  windows where you like them — Perch remembers, no rules or layouts required.
  Perch grew more capable than first envisioned (rules engine, layouts,
  per-monitor profiles, snap presets); this keeps that power opt-in rather than
  front-and-centre, so the complexity only surfaces for users who go looking
  for it. [S]
  Started 2026-08-27. Delivered as page 1 of the PERC-0003 wizard -- docs/08-ui.md § First-run setup wizard makes the Welcome page the zero-config statement, with no controls beyond Next. Not a separate surface.
  Resolved (2026-08-27). Shipped as page 1 of the PERC-0003 wizard, which is
  what docs/08-ui.md specifies -- the Welcome page states "You don't need to
  configure anything. Just move your windows where you like them -- Perch
  remembers", and carries no controls beyond Next. The rules engine, layouts
  and profiles stay opt-in and are reachable only via page 3's optional "Show
  me what else Perch can do" tick-box, so the complexity surfaces for users
  who go looking for it.
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

- ✅ [PERC-0035] **Tray menu: a Donate item and a Report an issue item.**
  Two entries near the existing About action in src/perch/ui/tray.py
  (build_menu, around the About/Quit block).

  "Report an issue" opens https://github.com/milnet01/perch/issues.

  "Donate" offers the same destinations as .github/FUNDING.yml, which
  today lists three: GitHub Sponsors (milnet01), Patreon
  (AntsProjectsHub), and https://paybru.co.za/tip/ants-projects-hub.
  Three destinations do not fit one menu item, so this needs a decision:
  a submenu with one entry each, or a single item opening a chooser.
  Prefer the submenu -- it is one click fewer and needs no new dialog.

  FUNDING.yml is the source of truth for the list. Read it at build time
  rather than hardcoding the three URLs, so adding a funding source stays
  a one-file change; if that proves awkward, hardcode but add a test
  asserting the menu matches FUNDING.yml, because a donate link that
  404s is worse than no donate link.

  Both open in the user's browser. Under Flatpak that must go through the
  portal rather than a direct xdg-open, and the manifest currently grants
  no network or browser access -- check what QDesktopServices.openUrl
  needs inside the sandbox before assuming it works.
  Resolved (2026-08-27). Shape decided by the user: a Donate SUBMENU with
  one entry per destination, as this item recommended.

  The two open questions in this item are both settled by measurement
  rather than assumption. Reading FUNDING.yml at runtime is impossible:
  `.github/` is not shipped in the wheel, the RPM or the Flatpak
  (pyproject packages = ["src/perch"]), so there is nothing to read once
  Perch is installed. Taking this item's own fallback, the destinations
  are stated in the new src/perch/ui/links.py and tests/ui/test_links.py
  asserts they match FUNDING.yml, expanding the github / patreon / custom
  shorthands; a platform with no URL mapping fails loudly rather than
  being skipped.

  And QDesktopServices.openUrl needs NO new sandbox permission: the
  org.freedesktop.portal.OpenURI interface is reachable from the running
  Flatpak with the manifest as it stands, verified by introspecting the
  portal inside the sandbox. The manifest is unchanged.

  Both entries emit a new OpenUrl intent, handled in app.py beside
  OpenConfigFolder. Four tests: the documented menu order (updated in
  docs/08-ui.md in the same change), the FUNDING.yml parity check, the
  submenu's labels, and one asserting each entry carries its OWN url --
  that last one confirmed failing against a deliberately reintroduced
  lambda late-binding bug, which is the defect that would otherwise send
  every donor to the same page.

  Not verified by a click: no headless way to press a tray menu item. The
  menu is confirmed to EXPORT correctly over D-Bus.
  **Layman:** Two new entries in the tray menu — one to support the project, one to report a problem
  Kind: feature.
  Source: user-request-2026-08-27.

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
