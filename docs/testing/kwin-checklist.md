# KWin backend — manual smoke checklist

Runs alongside the automated `kwin_wayland --virtual` integration suite
(`tests/backend/kwin/test_live_kwin.py`). The automated tests cover the
protocol surface in a private session; this checklist covers the things
that only a real Plasma 6 session on real hardware can exercise —
KGlobalAccel, portal interactions, per-output scaling, and the visible
"does pre-placement flicker?" question.

**Exit criterion from `11-roadmap.md` §M5**: Plasma 6.6.x smoke-tested,
every checkbox ticked.

## Prerequisites

- A working Plasma 6 Wayland session (the maintainer's reference is
  openSUSE Tumbleweed 2026-04-20 with Plasma 6.6.4).
- Perch installed from the repo:
  `pip install --user --break-system-packages -e .`
- `PERCH_BACKEND=kwin perch --check-config` exits 0 and lists at least
  one output. (The `--check-config` flag is introduced by M7; until then
  substitute `perch --version`.)

## Environment: Plasma 6 Wayland (reference)

The primary development target. A complete run here is the exit
criterion for M5.

- [ ] `perch` launches; the bundled script loads (check
      `kpackagetool6 -t KWin/Script -l | grep perch`).
- [ ] Tray icon appears (Plasma's SNI host is native).
- [ ] Opening Firefox, moving it, closing Perch, reopening Perch →
      Firefox geometry restored.
- [ ] Spawn four xterms (or Konsole instances); each lands at
      last-seen geometry.
- [ ] Hotkey registered via Perch appears in
      *System Settings → Shortcuts* under the "Perch" component.
- [ ] Rebinding that hotkey in System Settings takes effect without
      restarting Perch (KGlobalAccel autoloads the new binding).
- [ ] Moving a window between outputs in a multi-monitor setup updates
      the recorded `monitor` in `state.json`.
- [ ] Toggling fullscreen via KWin's native shortcut (Alt+F11) is
      reflected in Perch's state log as `state=fullscreen`.
- [ ] Virtual-desktop changes (Ctrl+F1..F4 or `Meta+Tab` with dynamic
      desktops) fire `current_desktop` correctly.

## Pre-placement (best-effort)

Pre-paint placement under Wayland is best-effort per
`docs/05-backend-kwin.md` §Pre-placement hook. Subjective test — fails
if a user would notice a flicker.

- [ ] With Perch running and a remembered geometry for Firefox,
      cold-start Firefox from a fresh launcher invocation. The first
      frame should appear at or very close to the remembered rectangle
      (within a few pixels is acceptable; a visible flight-across-
      screen flicker is a failure).
- [ ] Same for Konsole.
- [ ] Same for an XWayland client (`xterm` or a Steam game).

## Reload / crash recovery

- [ ] `kpackagetool6 -t KWin/Script -r org.milnet01.perch`, then
      restart Perch — it re-installs and re-loads the script without
      warning to the user.
- [ ] SIGKILL the Perch process while it's running; restart it. The
      defensive `unloadScript` in `start()` should handle the ghost
      — no `WindowAdded` flood for already-managed windows beyond
      what's expected from the fresh enumeration.
- [ ] `killall kwin_wayland` (via KDE's crash-recovery path, not
      actually killing the compositor — this is a "KWin script was
      unloaded out from under us" stand-in). Perch should re-install
      and re-load within ~2 s.

## Script-version pinning

- [ ] Edit
      `~/.local/share/kwin/scripts/org.milnet01.perch/metadata.json`
      to change `KPlugin.Version` to `"0.0.1-stale"` while Perch is
      not running. Restart Perch. It must detect the mismatch and
      rewrite the script to the bundled version
      (`perch.backend.kwin.BUNDLED_SCRIPT_VERSION`).

## XWayland caveat sweep

If a user is running an XWayland client under Plasma Wayland:

- [ ] XWayland windows appear in Perch's window list with
      `wm_class` set and `app_id` often empty — core falls back to
      `wm_class` for identity.
- [ ] XWayland window `type` reports correctly (dialog, utility, etc.)
      via KWin's already-translated `windowType`.
- [ ] Coordinates are in logical pixels (KWin does the XWayland ↔
      logical translation); Perch stores as-is.

## Known non-issues

- xdg-desktop-portal chatter on the private bus in the automated
  `kwin_wayland --virtual` harness. Warnings about
  `fusermount3 … Permission denied` and
  `Error calling StartServiceByName for
  org.freedesktop.impl.portal.desktop.kwallet` are expected in an
  unprivileged test environment and don't affect the test outcome.
- The virtual-output name from `kwin_wayland --virtual` shifts between
  `Virtual-0` and `Virtual-1` across KWin point releases. The
  integration suite asserts "non-empty" rather than a specific string.
- The KWin scripting API has no formal stability promise. A new 6.x
  point release may rename a property; re-run this checklist after
  each Plasma update and file a bug if anything breaks.
