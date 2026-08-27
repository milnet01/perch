# KDE Store listing

The KDE Store (<https://store.kde.org>) hosts Plasma addons browsable
from Discover and Plasma's *Get New Stuff* dialogs. Perch fits the
**Utilities** category.

This directory is not a build artefact — it's the authored source for
the listing's copy, categorisation, and links. The store itself renders
from whatever the maintainer uploads via the store's web UI; keeping
the text in-repo gives us a single canonical source.

**Submission walkthrough:** `packaging/submit/kde-store.md` (the KDE
Store has no CLI — it's a web-only flow, so that file is a runbook,
not a shell script).

## Listing copy (paste into the store form)

**Title:** Perch

**Category:** System → Utilities

**Short description (one line):**
Remember where your windows belong.

**Long description (markdown):**

```
Perch is a persistent, compositor-aware window geometry manager for
Linux desktops. It lives in the system tray, remembers where each
window belongs, and restores position, size, monitor, and virtual
desktop when a window reopens.

Highlights
----------

- Per-window geometry memory across sessions.
- Snap presets and named layouts.
- Rules engine matching by window class, title, or role.
- Per-monitor profiles that reconcile on hotplug.
- Native backends for X11 and KWin / Plasma Wayland; community stubs
  for Mutter, Sway, and Hyprland.

Install options
---------------

- Flatpak (Flathub) — cross-distro, sandboxed, recommended.
- openSUSE OBS — `home:milnet01/perch`, Tumbleweed and Fedora.
- Arch Linux AUR — `perch` (stable) or `perch-git` (HEAD).

Support
-------

- Source: https://github.com/milnet01/perch
- Issues: https://github.com/milnet01/perch/issues
- Docs: https://github.com/milnet01/perch/tree/main/docs
- License: GPL-3.0-or-later
```

## Tags

`window-manager` `kde` `plasma` `wayland` `x11` `tray` `layout`
`snap` `tiling` `geometry`

## Screenshots

Upload from `docs/screenshots/`:

1. `tray-menu.png` — caption "The tray menu showing active profile
   and snap presets."
2. `rules-editor.png` — caption "The rules editor matching windows
   by class and title."

At least one screenshot is required; two is the current state; we can
add more without re-uploading the whole listing.

## Install path (GHNS)

The KDE Store entry doesn't ship its own Perch binary — it points at
the Flatpak as the install source. In the store's *Install Command*
field:

```
flatpak install --user flathub io.github.milnet01.Perch
```

Once the Flathub submission lands, this command is the whole wiring.
Users who hit *Install* in Discover get a Flatpak install, same as
clicking through from Flathub directly.

## Release flow for KDE Store updates

1. Perch ships a new version to Flathub (see
   `packaging/flathub/SUBMISSION.md`).
2. In the KDE Store web UI, bump the listing's *Version* field to the
   new Perch version.
3. Upload an updated changelog excerpt (copy the relevant
   `CHANGELOG.md` section).
4. No new tarball upload is needed — the GHNS install command keeps
   pulling the latest Flathub build automatically.

## Why not a standalone tarball?

The KDE Store supports direct tarball uploads, but maintaining a second
artefact channel that duplicates the Flatpak is net-negative: two
places to publish, two release pipelines, two places for users to find
stale versions. Pointing at the Flatpak keeps one canonical binary
distribution while still getting discovery through Discover / Plasma
*Get New Stuff*.
