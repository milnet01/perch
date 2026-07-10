# 00 — Overview

## What Perch is

**Perch** is a persistent, compositor-aware window-geometry manager for Linux desktops. It runs in the system tray, remembers where each window belongs, and restores that geometry (position, size, monitor, virtual desktop) whenever the window reopens.

Think of it as "SessionRestore, but just for *where* windows live, and for every app — not only the ones that remember their own geometry."

## Why it exists

On Linux, window-geometry persistence is inconsistent:

- Some toolkits (GTK, Qt) remember it per-app; many don't.
- The window manager usually forgets everything on close.
- Under Wayland, an application can no longer set its own position — only the compositor can — so per-app "remember my position" code silently became a no-op on most desktops.
- Multi-monitor users who dock/undock a laptop lose their layout every time the monitor topology changes.
- Power users who want "Firefox always on monitor 2, maximized" have to configure that separately in every tool that supports it (and most don't).

Perch aims to own this one job, across compositors, so users don't have to rely on per-app memory or per-compositor hacks.

## Goals (v1)

1. **Persist geometry** of user-designated windows across app restarts, logouts, and reboots.
2. **Restore on open** — when a window appears, move/resize it to its remembered spot before the user sees it jump.
3. **Snap presets** — one-click halves, quarters, maximize, centered — both from the tray and via global hotkeys.
4. **Named layouts** — "coding", "media", "writing" — selectable from the tray; applies a set of windows to a set of positions.
5. **Rules engine** — declarative "if window matches X, put it at Y" rules (e.g. *"Firefox → monitor 2, maximized"*).
6. **Per-monitor-setup profiles** — "docked" vs "laptop-only" vs "external-TV" — separate geometries per topology.
7. **Exclusion list** — never touch splash screens, transient dialogs, or apps the user names.
8. **Export / import** — user config survives a reinstall or moves to a new machine.
9. **Cross-compositor** — works on X11 and KWin/Plasma Wayland at v1; contributor path to Mutter, Sway, Hyprland.

## Non-goals (v1)

- **Not a tiling window manager.** Perch restores positions; it does not tile, cascade, or enforce a grid in real time.
- **Not a session manager.** Perch restores *geometry* of whatever applications happen to reopen. It does not relaunch apps, restore terminal tabs, or remember browser tabs. (That's SessionRestore, `krestoresession`, or tmux-resurrect territory.)
- **Not a replacement for the WM / compositor.** Perch sits on top of whichever compositor is running and speaks its protocol.
- **Not a virtual-desktop manager.** It can put windows *on* a specific desktop, but it doesn't add/remove/rename desktops — that's the compositor's job.
- **Not cross-platform.** Linux only. There is no Windows or macOS port planned.
- **Not a KDE-exclusive utility.** KDE/Plasma is the primary desktop but the core is compositor-agnostic.
- **No cloud sync** in v1. Export/import is file-based; users can put that file in their own dotfiles repo or sync tool.

## Primary user

Someone who:

- Runs KDE Plasma, GNOME, or a tiling/wlroots setup on Linux.
- Uses multiple monitors, at least sometimes.
- Has opinions about where windows belong.
- Has been frustrated at least once by an app forgetting its size, or by docking a laptop and losing their layout.

## Glossary

| Term | Meaning in Perch |
|---|---|
| **Window** | A top-level application window as reported by the compositor. Child windows, menus, and popups are not managed. |
| **Geometry** | `(x, y, width, height, monitor, virtual_desktop)` — the full spatial state Perch persists. |
| **Backend** | A plugin implementing the `WindowBackend` interface for a specific compositor (X11, KWin, Mutter, …). See [03-backend-interface.md](03-backend-interface.md). |
| **Monitor topology** | The set of connected outputs, their resolutions, positions, and scale. Perch keys profiles off this. |
| **Profile** | A set of window geometries associated with a specific monitor topology. |
| **Layout** | A user-named, manually-triggered arrangement of windows. Unlike a profile, a layout is switched on demand (from the tray). |
| **Rule** | A declarative `match → action` entry: "if the window matches these criteria, set this geometry / this layout." |
| **Snap preset** | A named geometric action ("left half", "top-right quarter", …) applicable to the focused window via hotkey or menu. |
| **Identity** | The stable key Perch uses to recognise "the same window again." Typically `WM_CLASS` on X11, `app_id` on Wayland, with optional title regex. See [02-state-format.md](02-state-format.md). |
| **Exclusion** | A rule that says *don't manage this window*. |
| **Core** | The backend-agnostic part of Perch: tray UI, config dialog, rules engine, state, hotkey dispatch. |

## Document map

The rest of `docs/`:

- [01-architecture.md](01-architecture.md) — process model and how the core talks to backends.
- [02-state-format.md](02-state-format.md) — what Perch writes to disk and where.
- [03-backend-interface.md](03-backend-interface.md) — the contract every backend implements.
- [04-backend-x11.md](04-backend-x11.md), [05-backend-kwin.md](05-backend-kwin.md), [06-backend-stubs.md](06-backend-stubs.md) — per-backend designs.
- [07-rules-engine.md](07-rules-engine.md) — how rules are matched and evaluated.
- [08-ui.md](08-ui.md) — tray menu, config dialog, hotkeys.
- [09-layouts-profiles.md](09-layouts-profiles.md) — named layouts and per-topology profiles.
- [10-packaging.md](10-packaging.md) — Flatpak, RPM, Arch, KDE Store.
- [11-roadmap.md](11-roadmap.md) — phased milestones.

Standards (apply across the project, not tied to one milestone):

- [dependency-policy.md](dependency-policy.md) — dependency currency: run the latest, document any exception, retest capped versions when a newer one ships.
- [contributing-dev-setup.md](contributing-dev-setup.md) — dev environment and the pre-push `local_CI.sh` gate.
