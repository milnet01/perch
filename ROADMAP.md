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

- 📋 [PERC-0043] **Build the four documented features the audit found missing.**
  Each is promised by a document and has no implementation behind it:
  `perch --settings` (docs/08-ui.md:47, and the only recovery route offered
  to a user whose tray icon is invisible); the tray's Windows submenu
  (docs/08-ui.md §Menu structure); the tray error state for a missing
  compositor (TrayIconState.ERROR and its icon ship, and nothing ever sets
  compositor_missing); and the Rules dry-run toggle and trace panel, which
  docs/07-rules-engine.md:116 makes the gate for a documented engine mode.
  Note (2026-09-01): the full per-lane findings from the 2026-08-31 sweep,
  including the ~130 LOW/INFO items these bullets only summarise, are at
  `.audit/review-code-2026-08-31-findings.md` (905 lines). That path is
  GITIGNORED, so it survives on this machine only — if it matters elsewhere,
  track it or fold the tail into these bodies before it is lost. Line numbers
  there are as at e336950, before the tranche-1 fixes.

  Sequencing: run `verify-delivery` AFTER this item, not before. It works by
  running a feature against the promise made for it, and the four features here
  are documented-but-absent — so a run today would spend a full pass
  rediscovering exactly this bullet.
  **Layman:** Four things the manual says Perch can do that it currently cannot do at all.
  Kind: implement.
  Source: review-code 2026-08-31 (lanes app-shell, ui-shell, ui-dialog).

- 📋 [PERC-0044] **Make the Sway and Mutter backends' declared capabilities honest.**
  Both declare can_observe_geometry and can_observe_outputs true and emit
  no observation signal at all; neither polls either, despite Mutter's
  STATUS.md saying it does. docs/03-backend-interface.md:230 gates
  restore-on-open on that bit, so the product's headline feature is dead on
  both. Mutter also declares can_register_hotkeys against a gschema its own
  STATUS.md says is not shipped, which denies GNOME users the fallback
  grabber. Set the bits to what is true, then implement the event paths.
  **Layman:** On GNOME and Sway, Perch never notices a window opening — silently, with no error.
  Kind: fix.
  Source: review-code 2026-08-31 (lane backend-iface-stubs).

- 📋 [PERC-0045] **Target the requested window in the Hyprland dispatchers.**
  moveactive, resizeactive, movewindow and fullscreen all act on the active
  window and take no selector; the window-targeted forms are
  movewindowpixel, resizewindowpixel and movetoworkspacesilent. The
  dispatch helper only checks the reply is "ok", so acting on the wrong
  window reports success.
  **Layman:** On Hyprland, Perch moves whichever window has focus instead of the one it meant.
  Kind: fix.
  Source: review-code 2026-08-31 (lane backend-iface-stubs).

- 📋 [PERC-0046] **Give the compositor JavaScript a static-analysis gate, and fix what it finds.**
  The repo has no package.json, so check-code's detection table never
  selected eslint or tsc and 750 lines of shipped JavaScript have had no
  static analysis. What one pass would have caught: setInterval used in
  main.js where QJSEngine has no such builtin, which kills the whole
  windowAdded handler; an unused binding in extension.js; a deprecated
  global log(). Beyond a linter's reach and also open: main.js asserts both
  that QTimer.triggered.connect works and that it does not, the Plasma 5
  name sendClientToScreen with a silent read-only-property fallback, and
  the GNOME extension discarding the accel argument it is passed.
  **Layman:** The code Perch runs inside your desktop has never been checked by any tool.
  Kind: fix.
  Source: review-code 2026-08-31 (lane compositor-scripts); check-code 2026-08-31 tool gap.

- 📋 [PERC-0047] **Close the remaining X11 EWMH and ICCCM defects.**
  Eight survive the 2026-09-01 fix pass, which took the unmap-as-close and
  the negative-coordinate OverflowError. ScrollLock is missing from the
  modifier-mask permutations, so a hotkey silently dies with ScrollLock on;
  a server without RandR raises AttributeError out of start() rather than
  degrading, and the except BadAccess written for it cannot execute; every
  KeyPress refires the hotkey with no repeat filter; and the disjoint
  branch of outputs._intersect returns a zero-size rect that becomes an
  output's work area. close_window calls d.kill_client, which closes the
  client's whole connection and every window it owns with no save prompt,
  where docs/03:190 documents only WM_DELETE_WINDOW. There is no de-iconify
  path at all -- _NET_ACTIVE_WINDOW is interned and never used -- so
  can_set_state=True over-claims. None of the seven files imports logging
  or defines a module logger, against coding-standards.md:74, so a Perch
  that has stopped seeing windows produces no evidence at all. And the
  accelerator parser splits on "+", making the legal PortableText "Ctrl++"
  unregisterable. Two doc-side items belong with these and are carried by
  the documentation item instead: docs/04 Reading geometry describes a
  _NET_FRAME_EXTENTS subtraction the code correctly does not do, and
  docs/04:32 bans d.sync() absolutely while docs/04:117 requires catching
  an asynchronous BadAccess, which needs it.
  **Layman:** Several X11 corner cases where a hotkey stops working or Perch fails to start.
  Kind: fix.
  Source: review-code 2026-08-31 (lane backend-x11).

- 📋 [PERC-0048] **Fix the KWin portal Request/Response ordering and its uncaught fallback.**
  _await_response installs the signal match after issuing the call that
  triggers it, which for CreateSession completes immediately; the module's
  own comment states the required order. The documented fallback to
  KGlobalAccel then does not happen: no except clause for
  BackendDisconnectedProvider exists anywhere in src/, so the failure
  aborts startup instead of degrading. Derive the request path from
  handle_token and subscribe before the call.
  **Layman:** On Flatpak, the preferred way of registering shortcuts times out instead of working.
  Kind: fix.
  Source: review-code 2026-08-31 (lane backend-kwin).

- 📋 [PERC-0049] **Decide the single-instance question and implement the answer.**
  Four independent lanes looked for a guard and found none: no QLockFile,
  no flock, no pidfile anywhere in src/. docs/01-architecture.md:37 simply
  asserts "There is one process". Consequences already identified: two
  reducers writing one state.json through a fixed temp filename, and a
  suppressed SdBusRequestNameExistsError that lets the second instance
  believe it owns the bus name so every command times out. The 2026-09-01
  pass made the startup failure survivable; it did not answer whether the
  second instance should refuse or degrade.
  **Layman:** Nothing stops two copies of Perch running and fighting over the same saved file.
  Kind: implement.
  Source: review-code 2026-08-31 (lanes app-shell, core-state, config, backend-kwin).

- 📋 [PERC-0050] **Close the audit's security findings.**
  All calibrate low against docs/security-standards.md, which puts a
  same-UID attacker out of scope — filed because each is cheap and one is
  arguably not that case. The KWin D-Bus service resolves any caller's
  CommandDone payload into the state store with no sender check; the GNOME
  extension exports close_window and set_geometry to any session-bus caller
  with no validation, reachable by a Flatpak holding --socket=session-bus;
  the Hyprland backend falls back to a world-writable /tmp/hypr socket path
  built from an unvalidated instance signature; the config temp file is
  opened without O_NOFOLLOW; and XDG directories are created 0755 where the
  spec requires 0700, which does expose to other users on a shared machine.
  Two more calibrated UP rather than down and belong here. A user-authored
  `title` regex is compiled and run with re.search against window titles --
  attacker-controlled by any application the user runs -- with no length
  cap and no timeout, on the single thread driving both Qt and asyncio, so
  a catastrophic-backtracking pattern freezes the whole tray; it is
  reachable through config import, which the UI offers as a feature. And
  the import path reads the picked file twice and writes the bytes from the
  FIRST read, so a file changing between the two is written unvalidated,
  against the security standard's claim that every loaded document is
  validated.
  **Layman:** Tightening a few places where Perch trusts input it should check first.
  Kind: security.
  Source: review-code 2026-08-31 (lanes backend-kwin, compositor-scripts, backend-iface-stubs, config).

- 📋 [PERC-0051] **Reconcile the documentation the audit found contradicting the code.**
  Roughly thirty places where a lane named the DOCUMENT as the wrong side,
  left unfixed because each needs a contract decision rather than an edit.
  The largest: docs/05-backend-kwin.md §Pre-placement hook and
  docs/03-backend-interface.md both describe a can_preplace_windows feature
  and a QueryPlacement method that CHANGELOG.md:269 records as deliberately
  removed; docs/04-backend-x11.md §Reading geometry describes a
  _NET_FRAME_EXTENTS subtraction the code correctly does not do;
  docs/08-ui.md promises mutators with no callers; and the KWin command
  vocabulary is documented only in docs/11-roadmap.md, a milestone log,
  rather than in the design doc that calls itself authoritative. Route
  through review-contract rather than editing piecemeal.
  **Layman:** The manual describes things the code does not do, and vice versa.
  Kind: doc-fix.
  Source: review-code 2026-08-31 (all ten lanes).

- ✅ [PERC-0052] **Audit tranche 1a: the config and state persistence data-loss defects.**
  Thirteen findings, each verified against source before it was touched.
  state.json: a file from a newer Perch was discarded then rotated into
  .bak and overwritten (CRITICAL); a malformed record raised KeyError past
  the handler so the .bak fallback never ran; the dirty flag was cleared
  after the write rather than with the snapshot, dropping a geometry saved
  mid-flush. config.toml: a missing primary beside an intact backup seeded
  defaults over it; a too-new schema was treated as corruption and answered
  by loading the older backup; UnicodeDecodeError and OSError skipped the
  fallback entirely; the first-run seed bypassed the atomic recipe;
  os.replace rotated a symlinked config, detaching a dotfiles link; a
  failed write left a stray .tmp. Layout writer: `type` was serialised as a
  TOML array its own reader refuses (CRITICAL), and fractional percents
  were rounded away on every re-serialise. Also fixed, found by the suite
  rather than by review: load_or_create paired an explicit config_path with
  a backup defaulted to the real user's ~/.config/perch/config.toml.bak.
  Six regression tests added; the state-store one proved red by reverting
  the latch.
  **Layman:** Nine ways Perch could lose your saved windows or your settings file, all closed.
  Kind: fix.
  Source: review-code 2026-08-31 (lanes core-state, config); closed 2026-09-01 in 810c1c4.

- ✅ [PERC-0053] **Audit tranche 1b: the settings dialog's commit path.**
  Six findings. The Rules and Exclusions panes never refreshed their
  baseline after a successful commit, so a second commit re-applied the
  first delete against the original index -- which by then addressed a
  surviving entry. A failed save rolled back the document but not the
  panes' dirty state, so panes that had already committed reported clean
  and were never committed again, losing their edits silently. Adding a
  layout then renaming it registered the new name as its own original, so
  the add step was skipped and a description was written to a table that
  was never created. A suppressed profile delete left the index remap
  assuming it had happened, sending every later field write to the wrong
  profile. And a confirmed import left the dialog holding the pre-import
  document, so the next Apply from any pane undid the import. commit() and
  mark_committed() are now separate, with the freeze happening only after
  the write to disk lands.
  **Layman:** Clicking Apply then OK could delete a rule you never touched. Fixed.
  Kind: fix.
  Source: review-code 2026-08-31 (lane ui-dialog); closed 2026-09-01 in 810c1c4.

- ✅ [PERC-0054] **Audit tranche 1c: startup, teardown and backend lifecycle.**
  Nine findings. `await backend.start()` ran unguarded after the tray was
  already visible -- found independently by four review lanes, the highest
  agreement in the sweep -- and now degrades to the UI-only mode docs/01
  has always described; state_store.load() beside it was equally
  unguarded. KWin's stop() was gated on a flag set on start()'s last line,
  so any earlier failure left the bus name held and the injected script
  running inside the compositor with nothing owning it; start() now unwinds
  through stop(), which is idempotent. X11 read an ICCCM iconify unmap as a
  close, emitting the terminal window_closed for a live window that nothing
  could then restore (CRITICAL), and negative coordinates raised
  OverflowError outside the error taxonomy because the wire packing is
  unsigned (CRITICAL). Hyprland's event reader returned silently on EOF
  leaving the backend marked healthy, and its connection guard had an empty
  body. Teardown now cancels in-flight intent tasks and guards each stop
  independently, per docs/01 Teardown order; intent-task exceptions are
  retrieved so they reach perch.log.
  **Layman:** Perch no longer dies with a traceback when a backend cannot start.
  Kind: fix.
  Source: review-code 2026-08-31 (lanes app-shell, backend-x11, backend-kwin, backend-iface-stubs); closed 2026-09-01 in 810c1c4.

- ✅ [PERC-0055] **Audit tranche 1d: the documentation corrected alongside those fixes.**
  Fixed in the same commit as the code, per the project's
  no-documentation-debt rule. docs/01-architecture.md Teardown order cited
  `perch/core/shutdown.py`, a file that does not exist -- found by two
  independent lanes -- and its step list omitted the reducer stop entirely;
  both corrected, with the independent guarding of steps 3 and 4 stated.
  docs/08-ui.md now records that a confirmed import closes the dialog and
  why that is load-bearing rather than a convenience, and carries a new
  section documenting the commit/mark_committed protocol every page
  implements. CLAUDE.md rule 14 was applied to both: each records what was
  just built rather than changing direction for work still to come, which
  is the amendment instance that does not re-arm the cold-read gate.
  **Layman:** Three places where the manual described something that was not true.
  Kind: doc-fix.
  Source: review-code 2026-08-31 (lanes app-shell, core-state, ui-dialog); closed 2026-09-01 in 810c1c4.

- ✅ [PERC-0056] **Repair the project's own gates and packaging scripts.**
  Nine findings, none covered elsewhere. docs/10-packaging.md claims the
  AppImage is validated by extracting it in a bare ubuntu:22.04 container;
  that check exists nowhere, and the only real one runs `--version`, which
  __main__.py states exits before touching Qt -- so the bundle's whole
  reason for existing is unverified and release.yml ships it. harvest-libs.sh
  swallows three `dnf install` failures with `|| true` and nothing asserts
  the harvested count is non-zero, which is how that unverified bundle
  becomes a published AppImage that cannot load the xcb plugin. The
  docs-drift hook offers "open a tracking TODO" as a resolution, which the
  no-documentation-debt rule forbids by name, and it diffs the working tree
  against HEAD so it is silent once the turn is committed -- wrong in both
  directions. ci_lockstep_check.py drops any `run:` step with no `name:`, so
  an unnamed check in ci.yml leaves local_CI.sh printing "safe to push".
  intent_dispatch_audit.py classifies only top-level statements, so a stub
  wrapped in an `if` counts as real work. entrypoint.sh exports
  LD_LIBRARY_PATH to every child, so opening a link launches the host
  browser against AlmaLinux 8 libraries. generate-pip-sources.sh fetches and
  executes an unpinned `master` generator with no `curl -f`. flatpak-build.sh
  does not assert its manifest rewrite matched anything. obs.sh discards and
  silences an `osc add` failure, then commits without the tarball.
  Resolved (2026-09-02): all nine closed, each checked against
  current source first. The AppImage now proves itself -- build.sh's last
  step extracts it on a bare ubuntu:22.04 and resolves the xcb plugin's and
  Qt Core/Gui/Widgets/DBus's library closure against the host-provided
  soname list harvest-libs.sh writes out, so the harvest and the check
  cannot drift; harvest-libs.sh no longer tolerates a dnf failure and
  asserts a non-zero harvest. The docs-drift hook dropped its
  tracking-TODO resolution and now looks at unpushed commits as well as the
  working tree, so it survives the commit. generate-pip-sources.sh pins the
  generator to a commit and fetches with curl -f; flatpak-build.sh fails
  unless its rewrite matched exactly one module; obs.sh aborts on any osc
  add failure but "already tracked"; ci_lockstep_check.py reports an
  unnamed run: step instead of dropping it; intent_dispatch_audit.py
  descends into compound bodies while counting an effectful guard condition
  as real work; entrypoint.sh records the host library path and
  src/perch/hostenv.py restores it at every spawn site.

  Verified rather than assumed: a full AppImage build ran the new check,
  which passed and, with one soname removed from the allowed set, failed
  naming it. tests/test_hostenv.py is six tests, three of which fail
  without the fix. local_CI.sh: "All CI checks passed -- safe to push",
  830 passed on each of 3.12/3.13/3.14.

  The first version of the bare-container check was wrong -- it scanned
  every bundled .so with an incomplete search path and reported Qt's unused
  database/GTK/speech/Wayland plugins as missing libraries. Running it is
  what caught that.

  The lane's LOW/INFO tail and its three open questions are PERC-0065.
  **Layman:** The checks that decide whether Perch is safe to release have holes in them.
  Kind: fix.
  Source: review-code 2026-08-31 (lane tooling).

- ✅ [PERC-0057] **Close the rules-engine and state semantics the docs specify and the code does not implement.**
  Eleven findings. profiles.default_layout is parsed, seeded in the sample
  config and editable in the dialog, and nothing reads it -- docking
  activates the profile and applies no layout. The most-recently-focused
  rule is stated three times (docs/09:50, :163, layouts.py:6) and the
  reducer has no focus tracking at all, so activating a layout stacks every
  matching window on one rectangle. identity.py returns a shared
  "app:unknown" for any window with neither app_id nor wm_class, so
  unrelated windows overwrite each other's geometry, while its docstring
  claims a skip the reducer does not perform. catch_all short-circuits
  before every other field and parse_match accepts the combination, so one
  typo matches every window. monitor='all' validates and then fails on
  every apply. Percent geometry is never clamped, so docs/07:81's "a rule
  cannot push a window off-screen" does not hold. The remembered-window
  store has no quota, LRU or age eviction and records windows the exclusion
  layer says must never be remembered. _opt_str exists twice and has diverged on whether an empty string is
  valid. Three more sit in the apply path: the BackendUnsupported maximize
  fallback resolves the work area of the window's cached pre-move monitor
  rather than the resolved target, which docs/02:152 and docs/07:94 both
  specify; resolver's unmaximize_first requires a geometry, while
  docs/07:89 makes it unconditional on an explicit maximized=false --
  precisely so a following move lands on Mutter -- so that move is dropped
  on the backend the rule exists for; and the layout loop returns on the
  FIRST matching entry where docs/09:31 says last one wins, which may be
  the document's error rather than the code's and needs deciding.
  Resolved (2026-09-02): nine of the eleven fixed. default_layout is
  applied on profile activation and the loader now rejects one naming no
  declared layout; identity.UNKNOWN_IDENTITY and excluded windows are
  refused by a single Reducer._remember guard covering both write paths;
  catch_all combined with any other match field is rejected at parse time
  and in the settings dialog, which builds the dataclass directly;
  monitor='all' is rejected when the config loads rather than on every
  apply; percent geometry is clamped like the absolute branch;
  unmaximize_first is unconditional on an explicit maximized=false, so a
  monitor or desktop move is no longer dropped on Mutter; the maximize
  fallback resolves the target monitor's work area and names the rule; the
  two _opt_str copies are one shared matching.opt_str that rejects an
  empty string; and the layout loop takes the LAST matching entry, which
  is what docs/09 specifies -- rules keep first-match-wins and each
  document states its own half. Fourteen tests lock the changed
  contracts; all fourteen fail against the pre-fix tree.

  Two were split out rather than fixed, both needing a decision and not an
  edit. Most-recently-focused layout disambiguation is PERC-0066: no
  backend reports a focus order, and docs/09 §Apply semantics and
  §Implementation pointers describe different algorithms. Store retention
  is PERC-0067: no doc states a rule, and the growth is milder than the
  finding reads -- identities key on the application, not the window
  instance. docs/02, /07 and /09 record both.
  **Layman:** Several rule and layout behaviours the manual describes that do not actually happen.
  Kind: fix.
  Source: review-code 2026-08-31 (lane core-state).

- 📋 [PERC-0058] **Close the UI correctness and accessibility findings.**
  The red-outline validation docs/08-ui.md promises twice sets a Qt dynamic
  property with no stylesheet consumer anywhere in src/ -- setStyleSheet has
  zero hits -- so the only signal is a mouse-only tooltip Orca never
  announces. theming.py's default `auto` returns "system" only when
  colorScheme() is Unknown, which Plasma 6 and GNOME under Qt 6.8 never
  report, so it installs Fusion plus a hardcoded palette over Breeze and
  over any high-contrast scheme the user chose, with no config value that
  leaves the palette alone. The documented backend-disconnect notification
  never fires. rules_model._summarise_geometry and
  entry_editor.summarise_apply have diverged: one handles all four
  GeometryExpr members and the other three, and they render identical
  values differently, so two tables disagree on screen. icons.py returns a
  null QIcon with no log line, making Perch's only surface invisible
  silently. status.py connects plain closures Qt cannot auto-disconnect, so
  the backend outliving the tray raises on a deleted C++ object.
  portable_to_xdg is a zombie -- the live portal boundary uses a private
  copy. Plus untranslated user-facing strings across four lanes and two
  missing setAccessibleName calls.
  **Layman:** Validation that shows nothing, a theme override that ignores your desktop, and keyboard gaps.
  Kind: fix.
  Source: review-code 2026-08-31 (lanes ui-shell, ui-dialog).

- ✅ [PERC-0059] **Close the remaining config robustness findings.**
  Four findings left after the 2026-09-01 pass. There is no stale-document
  or concurrent-writer guard: the dialog parses the document at open time
  and writes it whole on Apply, and atomic_write compares no mtime, so a
  hand edit made meanwhile is discarded silently on a file the docs call
  hand-editable. schema.validate accepts `schema_version = true`, since
  bool is an int in Python. validate() rejects unknown keys inside
  [general] and [exclusions] but ignores unknown top-level tables, so a
  typo'd [[rule]] is silently dropped -- against docs/07:157's "Perch does
  not silently drop bad rules". rename_layout deletes and re-appends every
  key in [layouts], and tomlkit standalone comments are not in the map, so
  comments detach from the tables they annotate; docs/02:46 calls that
  footgun release-blocking and it needs a fixture to confirm. Separately,
  state.json has no migration registry at all, while docs/02 describes one
  for both files.
  Resolved (2026-09-02): five of the six fixed, one dismissed on evidence.

  set_profile_field now applies add_profile's rules -- duplicate name,
  duplicate topology, and the topology-key shape, the last through
  profiles.validate_topology_key rather than a second copy of the rule
  (add_profile was not checking the shape either). The stale-document hole
  is closed by writer.document_digest: the dialog fingerprints the file it
  parsed and asks before replacing it, and re-fingerprints after its own
  write and after the wizard's, so the ordinary path stays silent.
  schema.validate rejects a bool schema_version and any unknown top-level
  table, so a typo'd [[rule]] is reported rather than dropped -- docs/07
  §Validation. A missing config migration raises MigrationError, which the
  loader turns into the ConfigError docs/02 §Schema reference promises,
  rather than a bare KeyError. And state.json has the registry docs/02
  describes for both files: STATE_MIGRATIONS plus migrate_state, with an
  unmigratable document latching the store read-only on the same reasoning
  as the too-new case.

  Dismissed: rename_layout does NOT detach comments. Probed directly --
  each standalone comment stays with the table it annotates across a
  rename; what the rebuild adds is a blank line after it, which is
  whitespace. The fixture the finding asked for is written and locks the
  attachment.

  Also settled, from the same lane's open questions: duplicate topology is
  a REFUSAL, not first-wins. parse_profiles has always raised, and
  select_profile's own docstring says the scan is unambiguous because of
  it, so docs/09 §Edge cases was the wrong side and now says so.

  Fourteen tests; eleven fail against the pre-fix tree. The three that pass
  there are two over-rejection guards and the rename_layout fixture, which
  passes because the finding does not reproduce.

  Not covered here: state_store.py's fixed temp filename and missing writer
  lock, which this bullet inherited from the lane. That is a second-instance
  question and belongs to PERC-0049.
  **Layman:** Editing config.toml by hand while the dialog is open still loses your edit.
  Kind: fix.
  Source: review-code 2026-08-31 (lane config).

- 📋 [PERC-0060] **Close the remaining KWin backend findings.**
  Six findings outside the portal item. docs/05:140 promises recovery when
  the script disappears on a KWin crash or restart -- nothing subscribes to
  NameOwnerChanged, so every execute() then times out forever while the
  tray still reports connected. service.py leaks a _completions entry on
  CancelledError, grows latencies_ns without bound for the process
  lifetime, and never drains the queue, so a command whose future already
  expired is still applied late. is_available() claims to mirror
  _probe_session_env and disagrees with it when XDG_CURRENT_DESKTOP is
  unset. _bg_tasks is never cancelled in stop(), and the signal pump loops
  end silently on any bus error, killing every hotkey with no error and no
  restart. install.py raises unhandled when the target path is a symlink,
  and accepts PERCH_KWIN_SCRIPT_TARGET unvalidated. Four exception classes
  subclass RuntimeError against docs/03:219's ban on further subclassing,
  all reachable from start().
  **Layman:** If KWin restarts, Perch keeps reporting itself connected forever.
  Kind: fix.
  Source: review-code 2026-08-31 (lane backend-kwin).

- 📋 [PERC-0061] **Triage the static-analysis backlog check-code surfaced.**
  The whole-tree run left findings nobody has dispositioned: vulture 79
  (largely pytest fixtures, D-Bus signal methods and lazy __getattr__
  hooks, but not entirely), yamllint 68 against tool defaults with no
  .yamllint in the repo, zizmor 14 (6 unpinned-uses, 4 excessive-permissions
  from ci.yml having no top-level permissions block, 4 artipacked),
  typos 24 after calibration (16 inside docs/screenshots PNG binaries),
  bandit 3, semgrep 2 (both defusedxml in one test), and 160 from the
  project's own analyser, mostly tier-4 metrics rather than defects. The
  work is deciding which are real, then either fixing or recording a
  calibration -- this project has no false-positive ledger and no
  audit-config.json, so two runs of the sweep cannot be compared. Authoring
  that config is part of this item. Note ruff runs with select E,F,I,UP,B,
  SIM,RUF, which omits S: two asserts that vanish under `python -O` were
  found by review rather than by the linter.
  **Layman:** A pile of tool warnings nobody has sorted into real and noise yet.
  Kind: investigate.
  Source: check-code --tree 2026-08-31.

- 📋 [PERC-0062] **Fix the documentation that points at things which no longer exist.**
  Four, all verified absent on 2026-09-01. audit_config.yaml and CLAUDE.md
  both drive the project's analyser from
  /mnt/Storage/Scripts/Linux/3D_Engine/tools/audit/audit.py, on a drive that
  was retired -- so nobody following the documented command can run it; the
  surviving copy is under another project. docs/documentation-standards.md
  mandates the `/cold-eyes` skill for every new or edited design doc and
  names `/feature-test` for per-feature specs; both were retired and
  replaced by review-contract and write-test. docs/coding-standards.md:63
  cites `/audit`, replaced by check-code. And docs/06-backend-stubs.md:92
  with mutter/STATUS.md:54-57 promise a script that installs the GNOME
  extension into ~/.local/share/gnome-shell/extensions -- no such script
  exists in scripts/ or packaging/, and EXTENSION_UUID and
  BUNDLED_EXTENSION_DIR have zero consumers repo-wide. Separately,
  docs/git-commit-standards.md:57 and docs/testing-standards.md:106 both
  state local_CI.sh runs one interpreter, which has been false since it
  learned to read ci.yml's matrix. Two more of the same class. PERCH_LOG_TITLES
  is named as a privacy opt-in by docs/security-standards.md:54,
  docs/coding-standards.md:80, docs/02-state-format.md:272,
  docs/testing-standards.md:41 and logging_setup.py's own docstring, and is
  read by no code anywhere -- while logging_privacy.py:21 states the
  opposite policy outright, that redaction is unconditional. A control
  named in a security standard that nothing reads is worse than no control,
  because it invites a reader to conclude the redaction is switchable and
  audited when it is neither; decide which side is true before either
  document is trusted again. And several module docstrings still speak in
  the future tense about shipped code on a 1.1.0 release --
  core/__init__.py, state.py, reducer.py, engine.py, actions.py,
  layouts.py, identity.py -- against the project's own no-documentation-debt
  rule, whose own instruction is to grep for "planned", "will" and "not
  yet" before declaring work done.
  **Layman:** Instructions in the repo that cannot be followed because what they name is gone.
  Kind: doc-fix.
  Source: review-code 2026-08-31 (lane tooling); check-code 2026-08-31.

- 📋 [PERC-0063] **Review the test suite, which this audit deliberately did not read.**
  review-code bans its lanes from reading the test tree, because reading
  the tests imports the author's model of what the code should do. So the
  2026-08-31 sweep covered src/ and the tooling and says nothing about
  whether the 855-test suite verifies what it claims, whether any test is
  flaky or leaky, or where coverage is absent. review-tests is the skill
  for that question and has never been run here. Two signals already argue
  for it: vulture reports large numbers of apparently-unused pytest
  fixtures, and the KWin compliance tests skip wholesale on any host
  without a live KWin -- 20 skips in the local run -- so what they cover is
  unestablished on the machine that gates the pushes.
  **Layman:** The tests have not themselves been checked for whether they test anything.
  Kind: test.
  Source: review-code 2026-08-31 (coverage gap, stated in the run's report).

- 📋 [PERC-0064] **Close the app-shell and autostart findings the tranche-1 pass left open.**
  Six findings, none closed on 2026-09-01. autostart.py subscribes to the
  Background portal's Response only after RequestBackground has returned,
  so once a permission is stored the signal can fire first and the task
  blocks for the full 300 s timeout, logging a failure for a toggle that
  succeeded. The sibling copy in kwin/hotkeys.py:576 closes exactly this
  with a caller-supplied handle_token; this copy's options dict carries
  none, and the module docstring flags the duplication without naming the
  axis it has drifted on. is_enabled() returns False unconditionally while
  its docstring promises the config value, and sync() discards
  portal_set_autostart's return, so the granted result the PERC-0037 fix
  added reaches no caller and the state shown under Flatpak can never be
  right. In app.py there is still no cleanup path between the guarded
  backend.start() and the try block: reducer.start(), the ConfigDialog
  construction and open_dialog() can each raise, and backend.stop() then
  never runs. Smaller: one contextlib.suppress wraps both add_signal_handler
  calls, so a SIGINT failure silently skips SIGTERM -- the signal the
  session manager sends at logout; two asserts vanish under python -O; and
  a relative $XDG_CONFIG_HOME is honoured where the spec says to ignore it.
  **Layman:** Turning autostart on under Flatpak can report failure for something that worked.
  Kind: fix.
  Source: review-code 2026-08-31 (lane app-shell).

- 📋 [PERC-0065] **Close the tooling lane's LOW/INFO tail, which PERC-0056 did not cover.**
  PERC-0056 closed the lane's HIGH and MEDIUM findings; these are the
  rest, and they are recorded here because .audit/ is gitignored.

  python-post-edit.sh never checks for jq, so without it the hook
  silently no-ops forever -- its header documents a no-op for a missing
  ruff only. docs_check.py's SCANNED set excludes
  packaging/appimage/README.md (a version-bearing entry in bump.json)
  and packaging/flathub/SUBMISSION.md, and its Python-floor rule cannot
  fire on pyproject.toml, the RPM spec or the Flatpak manifest. aur.sh
  copies .SRCINFO verbatim and checks only that it exists; nothing
  verifies pkgver/source against the PKGBUILD beside it, and
  version_lockstep_check.py -- which covers both -- is wired only into
  bump.json's post_check, so a manual AUR push has no gate. obs.sh
  assigns USER, clobbering it for osc, curl and every child, and an
  empty awk result yields the project name "home::perch".
  scripts/i18n-update.sh documents perch_<locale>.ts and passes only
  perch_en.ts. pyproject.toml carries a static version alongside a
  [tool.hatch.version] source with no dynamic entry, so it names two
  sources of truth and honours one (bump.json bumps both, so nothing is
  broken today). docs_check.py re-reads and re-slugs the whole target
  file for every link. version_lockstep_check.py's DATE_RE is unused.

  Three questions the lane raised and could not settle. release.yml
  checks out github.ref on the workflow_dispatch path but uploads to
  inputs.tag, so a manual backfill can attach an AppImage built from a
  different commit than the tag; the comment there calls it deliberate
  and versioning-release-standards.md does not address the dispatch
  path. Should version_lockstep_check.py join the push gate -- adding it
  to local_CI.sh alone would trip ci_lockstep_check.py's question 4, so
  it goes into both or neither. And obs.sh derives the version by
  grep|cut in two places, a third parsing method alongside build.sh's
  tomllib and bump.json's regex; they agree today.
  **Layman:** Small leftovers in the release and check scripts — none of them break a build, but each one hides something.
  Kind: fix.
  Source: review-code 2026-08-31 (lane tooling, LOW/INFO tail); deferred by the PERC-0056 pass 2026-09-02.

- 📋 [PERC-0066] **Settle and implement layout disambiguation when several windows match one entry.**
  docs/09 §Apply semantics says the geometry goes to the
  most-recently-focused match and the others are left alone. Nothing
  tracks focus: WindowBackend exposes get_active_window(), a
  point-in-time poll, and no focus-change signal, so no recency order
  exists to consult. docs/09 §Implementation pointers describes a
  different algorithm again -- the engine emitting one decision per
  layout-matched window, which is what the code does and which has no
  place to prefer one window. So the contract has to be settled before
  anything is built, and settling it may extend WindowBackend, which
  CLAUDE.md routes through a doc PR. Until then a layout entry matching
  two windows stacks both on one rectangle.
  **Layman:** When two windows of the same app are open, decide which one a layout moves.
  Kind: implement.
  Source: review-code 2026-08-31 (lane core-state), split out of PERC-0057.

- 📋 [PERC-0067] **Decide a retention policy for remembered windows and stop writing last_seen unread.**
  state.json has no quota, no LRU and no age eviction, and last_seen is
  written on every record and read by nothing. The growth is milder than
  it looks -- compute_identity keys on the application, not the window
  instance, so the store holds one entry per distinct app rather than one
  per window ever opened. No doc states a retention rule, so picking one
  is a product decision, not an edit: either give last_seen a reader (age
  eviction at load) or drop the field. docs/02 needs the answer before
  the code does.
  **Layman:** Decide how long Perch should remember a window it has not seen in a long time.
  Kind: implement.
  Source: review-code 2026-08-31 (lane core-state), split out of PERC-0057.

- ✅ [PERC-0068] **Settle the four open questions the core-state lane left unresolved.**
  Three were real and are fixed; one was a doc-vs-doc wording mismatch.

  The X11 backend sent its move-resize before the desktop message and KWin
  sent them the other way round, so the two v1 backends disagreed and one
  contradicted docs/07 §Apply order step 2. X11 now matches: a window
  manager is free to re-place a window when its desktop changes, so the
  placement has to be the last word. Both still go out before one flush.

  docs/09 §Apply semantics step 4 requires a notification listing layout
  entries skipped for an absent output; the reducer only logged. The
  reducer now collects them across one apply pass and hands the list to a
  notify_skipped callback the composition root wires to the tray balloon.
  The pass is the unit -- a lone window event logs and does not notify --
  and the core builds no user-facing string, so wording and translation
  stay in ui/status.py.

  reducer.handle_window_changed's docstring read as though the method
  filtered events. It does not; docs/03 declares window_changed a title /
  type / state signal and a move arrives on geometry_changed. Reworded to
  say whose filtering it is.

  Not a defect: docs/07 triggered the maximize fallback on
  can_set_state=False and docs/02 on a caught BackendUnsupported, and the
  code implements only the latter. No shipped backend declares
  can_set_state=False, and a backend that cannot set the state raises
  BackendUnsupported either way, so the two sentences describe one event
  from two sides. docs/07 now says so rather than naming a second trigger.
  **Layman:** Four things the audit could not decide, now decided.
  Kind: fix.
  Source: review-code 2026-08-31 (lane core-state, OPEN QUESTIONS block).

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
