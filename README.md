# Perch 🪟

> **Your windows, where you left them.** Perch quietly remembers where each of
> your windows lives — which screen, which spot, what size — and puts them back
> there every time they reopen.

Perch sits in your system tray and does one thing well: it stops you from
dragging the same windows into the same places every single day. Open your
editor and it lands on the left half of your second monitor, like it always
does. Reconnect your laptop to your desk and everything shuffles back to where
it belongs.

**Status:** v1.0.0 · Linux · free & open source (GPL-3.0). See
[`CHANGELOG.md`](CHANGELOG.md) for what's new.

---

## Download & run

Perch ships as an **AppImage** — a single file you download and run. **No
installing, no dependencies, no Python to set up.** It works on any modern Linux
desktop (Ubuntu 20.04+, Debian, Fedora, openSUSE, Arch, and more).

1. Download `Perch-1.0.0-x86_64.AppImage` from the
   [**Releases page**](https://github.com/milnet01/perch/releases/latest).
2. Make it runnable (once):
   ```bash
   chmod +x Perch-1.0.0-x86_64.AppImage
   ```
3. Run it:
   ```bash
   ./Perch-1.0.0-x86_64.AppImage
   ```

Perch appears in your system tray. Right-click the tray icon for everything —
snap presets, layouts, and settings. To start it automatically at login, use
the **General → Start at login** toggle in its settings.

> **Coming soon:** one-command installs via Flathub, the AUR, and openSUSE —
> see the [roadmap](ROADMAP.md#v101--get-it-downloadable).
> For now, the AppImage above is the easy button.

---

## What it does

- **Remembers everything** about each window — position, size, which monitor,
  which virtual desktop — and restores it when the window reopens.
- **Snap presets** from the tray: centre, left/right half, the four quarters,
  and "maximise on this screen".
- **Named layouts** — flip your whole screen between "coding", "media", and
  "writing" arrangements in one click.
- **Rules** — *"always open Firefox on monitor 2, maximised"* and it just
  happens.
- **Docked vs. laptop profiles** — different window positions for when your
  laptop is at your desk versus on its own.
- **Global hotkeys** for snap presets.
- **An exclusions list** so splash screens and little dialogs are left alone.
- **Export / import** your setup so it survives a reinstall or moves to a new
  machine.

## Will it work on my desktop?

Perch supports the mainstream Linux display servers through a plug-in design.

| Your desktop | Support |
|---|---|
| **KDE Plasma** (X11 or Wayland) | ✅ full |
| **Any X11 desktop** (Xfce, MATE, Cinnamon, i3, …) | ✅ full |
| GNOME (Wayland) | 🚧 stub — help wanted |
| Sway / wlroots | 🚧 stub — help wanted |
| Hyprland | 🚧 stub — help wanted |

The "stub" backends have the wiring in place but need a contributor to finish
them — adding one means implementing a single interface
([`docs/03-backend-interface.md`](docs/03-backend-interface.md)), no changes to
Perch's core.

## Windows?

Not yet — Perch is Linux-only today. A Windows edition (same idea, native
Win32 backend, fully self-contained installer) is on the
[roadmap](ROADMAP.md#windows-edition--separate-track).

---

## For developers

Perch is Python 3.12+ with PySide6 (Qt 6). To run from source:

```bash
git clone https://github.com/milnet01/perch.git
cd perch
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
perch --version
```

- **Full dev setup, tests, and the pre-push check:**
  [`docs/contributing-dev-setup.md`](docs/contributing-dev-setup.md).
- **Build the AppImage yourself:** [`packaging/appimage/`](packaging/appimage/README.md).
- **Design docs (how it all works):** [`docs/`](docs/).

Contributions welcome — please read [`CONTRIBUTING.md`](CONTRIBUTING.md) first.
Perch is **docs-first**: any behaviour change updates the relevant `docs/` file
in the same change.

## License

[GPL-3.0-or-later](LICENSE).
