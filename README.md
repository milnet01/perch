# Perch

> Persistent, compositor-aware window geometry manager with a system-tray UI for Linux desktops.

**Status:** v1.0.0 — see [`CHANGELOG.md`](CHANGELOG.md) and [`docs/11-roadmap.md`](docs/11-roadmap.md) for the per-milestone history.

## What Perch does

- Runs in the system tray; launches automatically at login.
- Remembers position, size, monitor, and virtual desktop of every managed window.
- Restores windows to their remembered spot when they reopen.
- Provides a live-editable list of open windows (x, y, width, height).
- One-click snap presets: center, left half, right half, top-left, top-right, bottom-left, bottom-right, plus quarter snaps and "maximize on this monitor".
- Named layouts ("coding", "media", "writing") switchable from the tray.
- Rules engine: *"always open Firefox on monitor 2, maximized"*.
- Per-monitor-layout profiles — separate positions for docked vs. laptop-only.
- Global hotkeys for snap presets (via `xdg-desktop-portal` GlobalShortcuts, with KGlobalAccel / `XGrabKey` fallbacks).
- Exclusion list for windows that shouldn't be managed (splash screens, transient dialogs).
- Export / import configs so layouts survive a reinstall.

## Supported display servers

Perch uses a backend-plugin architecture so it can target any mainstream Linux display server / compositor.

| Backend | Status | How it works |
|---|---|---|
| X11 (any EWMH window manager) | full | `python-xlib` + an in-tree EWMH helper |
| KWin / Plasma Wayland | full | KWin D-Bus + a bundled KWin JavaScript script |
| Mutter / GNOME Wayland | stub | GNOME Shell extension (contributor-welcome) |
| Sway / wlroots | stub | `swaymsg` |
| Hyprland | stub | `hyprctl` |

Writing a new backend means implementing the `WindowBackend` interface described in [`docs/03-backend-interface.md`](docs/03-backend-interface.md) — no core changes required.

## Installation

Perch is distributed through:

- **Flathub** (Flatpak) — primary cross-distro channel
- **openSUSE OBS** — RPM
- **AUR** — Arch / Manjaro (`perch` stable, `perch-git` HEAD)
- **Fedora COPR** — RPM
- **KDE Store** (store.kde.org) — links at the Flatpak

Packaging recipes live under [`packaging/`](packaging/). See [`docs/10-packaging.md`](docs/10-packaging.md) for the per-channel installation commands.

## Building from source

Perch targets **Python 3.12+** with PySide6 ≥ 6.8.

```bash
git clone https://github.com/milnet01/perch.git
cd perch
pip install --user --break-system-packages -e ".[dev]"
perch --version
```

See [`docs/contributing-dev-setup.md`](docs/contributing-dev-setup.md) for the full dev workflow (system packages, test commands, pre-commit expectations).

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).

## Contributing

Design-first: please read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the relevant file in [`docs/`](docs/) before opening a PR. Any behavior change should be reflected in the docs either before or in the same PR as the code.
