# Perch

> Persistent, compositor-aware window geometry manager with a system-tray UI for Linux desktops.

**Status:** design / pre-implementation. Perch is currently in documentation-first design mode — see [`docs/`](docs/) for the architecture, backend specs, and roadmap.

## What Perch will do

- Run in the system tray; launch automatically at login.
- Remember position, size, monitor, and virtual desktop of every managed window.
- Restore windows to their remembered spot when they reopen.
- Provide a live-editable list of open windows (x, y, width, height).
- One-click snap presets: center, left half, right half, top-left, top-right, bottom-left, bottom-right, plus quarter snaps and "maximize on this monitor".
- Named layouts ("coding", "media", "writing") switchable from the tray.
- Rules engine: *"always open Firefox on monitor 2, maximized"*.
- Per-monitor-layout profiles — separate positions for docked vs. laptop-only.
- Global hotkeys for snap presets.
- Exclusion list for windows that shouldn't be managed (splash screens, transient dialogs).
- Export / import configs so layouts survive a reinstall.

## Supported display servers

Perch uses a backend-plugin architecture so it can target any mainstream Linux display server / compositor.

| Backend | Status | How it works |
|---|---|---|
| X11 (any EWMH window manager) | planned for v1 | `python-xlib` + an in-tree EWMH helper |
| KWin / Plasma Wayland | planned for v1 | KWin D-Bus + a bundled KWin JavaScript script |
| Mutter / GNOME Wayland | stub + docs | GNOME Shell extension (contributor-welcome) |
| Sway / wlroots | stub + docs | `swaymsg` |
| Hyprland | stub + docs | `hyprctl` |

Writing a new backend means implementing the `WindowBackend` interface described in [`docs/03-backend-interface.md`](docs/03-backend-interface.md) — no core changes required.

## Installation (planned)

Perch will be distributed through:

- **Flathub** (Flatpak) — primary cross-distro channel
- **openSUSE OBS** — RPM
- **AUR** — Arch / Manjaro
- **Fedora COPR** — RPM
- **KDE Store** (store.kde.org) — as a KWin-aware utility

Nothing is published yet — these land in milestone M8.

## Building from source (planned)

Perch targets Python 3.11+ with PySide6. Until the first implementation milestone lands, there is nothing to build.

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).

## Contributing

Design-first: please read [`CONTRIBUTING.md`](CONTRIBUTING.md) and the relevant file in [`docs/`](docs/) before opening a PR. Any behavior change should be reflected in the docs either before or in the same PR as the code.
