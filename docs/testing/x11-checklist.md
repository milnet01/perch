# X11 backend — manual smoke checklist

Runs alongside the automated Xvfb + openbox integration suite (see
`tests/backend/x11/test_live_openbox.py`). The automated tests cover the
protocol surface; this checklist covers the compositor-quirks surface that
needs a human eye on a real session.

**Exit criterion from `11-roadmap.md` §M4**: all three environments below
smoke-tested, every checkbox ticked.

## Prerequisites

- A working login session on the target compositor.
- `xclock`, `xterm`, or `firefox` available for window-spawn probes.
- Perch installed from the repo: `pip install --user --break-system-packages -e .`
- `PERCH_BACKEND=x11 perch --check-config` exits 0 and lists one output.

## Environment: Openbox (reference)

Openbox is the automated reference; a manual run here is a sanity check
that nothing drift-broke between CI and a real desktop.

- [ ] `perch` launches; tray icon appears.
- [ ] Opening Firefox, moving it, closing Perch, reopening Perch → Firefox
      geometry restored.
- [ ] Spawn four xterms; each lands at last-seen geometry.

## Environment: Plasma-X11

Plasma-X11 adds GTK-shadow frame reporting and KGlobalAccel contention on
common accelerators.

- [ ] Tray icon appears (Plasma SNI host is native).
- [ ] `Meta+Left` hotkey registered via Perch does not conflict with
      KWin's own `Meta+Left` (KDE's default tiling half — expect
      "hotkey unavailable: Meta+Left is already grabbed"). Prompt user to
      pick another accelerator.
- [ ] Move a GTK app (Firefox, Nautilus, GIMP); recorded geometry matches
      the visible window within ±4 px (GTK client-side shadows).
- [ ] Virtual-desktop changes fire `current_desktop` correctly — switch
      via `Ctrl+Alt+F1..F4` and confirm Perch's state log agrees.

## Environment: i3

i3 doesn't publish `_NET_WORKAREA` and ignores `_NET_MOVERESIZE_WINDOW`
on tiled windows.

- [ ] Tray visible (i3bar's systray region).
- [ ] Spawning a floating window → geometry restore works.
- [ ] Spawning a tiled window → geometry write is silently skipped
      (i3 quirk documented in `docs/04-backend-x11.md`). Perch emits a
      `backend_error` with a clarifying message; no crash.
- [ ] Workspaces 1..10 map correctly to `DesktopIndex 0..9`.

## Environment: Xfce (xfwm4)

Xfce is the most common "pure EWMH, no WM bells" setup outside Openbox.

- [ ] Tray icon appears (xfce4-panel).
- [ ] Firefox restore round-trips pixel-accurate (±1 px for Xfwm's 1 px
      border policy).
- [ ] Xfce's own shortcut manager conflicts are surfaced as
      "hotkey unavailable" rather than silent.

## XWayland caveat sweep

If the user runs Perch under XWayland (Plasma/GNOME Wayland session with
`PERCH_BACKEND=x11`):

- [ ] Output names are `XWAYLAND0`, `XWAYLAND1`, … — Perch displays them
      verbatim; no attempt to correlate with the Wayland compositor's
      logical names.
- [ ] Fractional scale is invisible from X11; coordinates are in logical
      pixels.
- [ ] Document the environment in any bug report (Wayland-under-XWayland
      behaviour diverges enough that it deserves its own label).

## Known non-issues

- GTK client-side shadows cause visible geometry to be smaller than the
  `_NET_FRAME_EXTENTS`-reported frame. Documented in
  `docs/04-backend-x11.md` — not a Perch bug.
- Openbox's 50 ms map race for `_NET_FRAME_EXTENTS` is handled by the
  identity code; users should never see pre-decoration geometry.
