# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Perch** — a persistent, compositor-aware window geometry manager for Linux desktops. Sits in the system tray, remembers where each window belongs, and restores geometry (position, size, monitor, virtual desktop) when a window reopens. Also offers snap presets, named layouts, a rules engine, and per-monitor profiles.

Home: https://github.com/milnet01/perch — license: **GPL-3.0-or-later**.

## Current phase

Perch is at **v1.0.0**. Phases 0–4 are complete; see `docs/11-roadmap.md` for the per-milestone history and `CHANGELOG.md` for release notes.

Phase sequence:

0. Repo bootstrap — **done**.
1. Design docs — **done**.
2. Review + online research to validate design assumptions — **done**.
3. Revise docs based on findings — **done**.
4. Implementation (M1…M9) — **done**.

## Docs-first rule (hard rule)

Any behavior change must land in the relevant `docs/` file **before or in the same PR as** the code that implements it. Do not write implementation code that isn't backed by a doc. If a user request implies a behavior that isn't covered by an existing doc, the correct first step is to propose a doc change.

## No documentation debt (hard rule)

Docs and code must stay in sync, always. This is a stronger rule than "docs-first":

- When you change code, update the relevant `docs/` file in the same change. Never later.
- When you learn something during implementation that makes an existing doc wrong, fix the doc immediately — do not leave "TODO: update doc" comments.
- When a feature ships, rewrite any future-tense sentences about it in the docs to present tense in the same PR. Grep for `planned`, `will`, `to be`, `not yet` before declaring work done.
- When a feature is removed, remove every doc reference to it in the same PR. No ghost features.
- If you notice stale docs while working on something unrelated, fix them (or open a dedicated doc PR) — don't walk past them.

The invariant: **reading `docs/` at any commit on `main` tells the reader what the code does at that commit.** Drifting from that invariant is treated as breaking the build.

## Dependency currency (hard rule)

Every dependency — runtime library, dev/test tool, CI action, Python runtime, base image — runs the **latest stable version**. This is a security posture as much as a feature one: the latest release is the one getting security patches. Pin below latest **only** when a newer version explicitly breaks a Perch feature and there's no workaround; when you do, add an inline reason *and* a row in the Broken-version register — both in the same change. The full standard, the register, and the outstanding-cap audit live in [`docs/dependency-policy.md`](docs/dependency-policy.md). Run `.venv/bin/python -m pip list --outdated` on a currency sweep each release cycle.

## Never push without a green `local_CI.sh` (hard rule)

`./local_CI.sh` mirrors `.github/workflows/ci.yml` exactly (both jobs). Run it and get `safe to push` **before every push** — a red push burns a CI run to tell us what the script would have caught in seconds. If you edit `ci.yml`, edit `local_CI.sh` in the same commit; they must never drift.

## Tech stack

- **Language:** Python 3.12+
- **UI toolkit:** PySide6 (Qt ≥ 6.8) — tray icon via `QSystemTrayIcon`, config dialog in Qt Widgets, integrates naturally on KDE.
- **Async glue:** `qasync` — one event loop drives both Qt and asyncio.
- **D-Bus:** `sdbus-python` (async, C-backed via libsystemd). `dbus-next` was the initial pick but is effectively dormant upstream since 2022; swapped during Phase 2 research (see `docs/11-roadmap.md` findings log).
- **X11:** `python-xlib` directly, with a small in-tree EWMH wrapper. `python-ewmh` was the initial pick but is unmaintained since 2017 and not packaged on Fedora/openSUSE.
- **Packaging:** Hatchling build backend; Flatpak manifest for Flathub; RPM spec for openSUSE OBS + Fedora COPR; PKGBUILD for AUR.

## Backend-plugin architecture

The core (tray, UI, state, rules engine, hotkey dispatcher) is backend-agnostic and talks to the `WindowBackend` interface defined in `docs/03-backend-interface.md`. Backends:

| Backend | Transport | Priority |
|---|---|---|
| X11 (any EWMH WM) | `python-xlib` + in-tree EWMH helper | v1 |
| KWin / Plasma Wayland | KWin D-Bus + bundled KWin JS script | v1 |
| Mutter / GNOME Wayland | GNOME Shell extension | stub, community |
| Sway / wlroots | `swaymsg` | stub, community |
| Hyprland | `hyprctl` | stub, community |

When adding compositor-specific behavior, the rule is: if it fits the `WindowBackend` interface, put it in a backend; if it doesn't, that's a sign the interface needs to change — discuss in a doc PR first.

## Repo layout

```
perch/
  CLAUDE.md             ← this file
  LICENSE               ← GPL-3.0-or-later
  README.md
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  CHANGELOG.md
  pyproject.toml
  .gitignore
  .github/              ← issue templates, PR template, CI
  src/perch/            ← Python package (core, ui, backends)
  tests/                ← pytest suite (unit + backend compliance + live X11/KWin)
  docs/                 ← design docs (00 … 11)
  data/                 ← AppStream metainfo, desktop entry, icons
  packaging/            ← Flatpak / RPM / AUR / KDE Store recipes
  translations/         ← Qt Linguist .ts sources
  scripts/              ← dev helpers (i18n, screenshot rendering)
  experiments/          ← archived spikes (M2.5 KWin IPC)
```

## Parent context

`/mnt/Storage/Scripts/Linux/perch/` sits under the OS work root at `/mnt/Storage/`. See `/mnt/Storage/CLAUDE.md` for OS-wide conventions — notably, use `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A` instead of bare `sudo` for any privileged command.

## Working notes for future Claude sessions

- The project directory was renamed from `window_manager` to `perch` on 2026-04-20. If you see stale references to `window_manager`, fix them.
- The user prefers short, terse responses and explicit phased plans for non-trivial work (see auto-memory `feedback_workflow.md`).
- When in doubt on a design call, write the doc first and let the user review before writing code.

## Project tooling (Claude Code)

The repo ships with a small amount of Claude-Code-specific tooling at `.claude/`. Use it rather than reimplementing equivalent logic ad hoc.

**Hooks** (run automatically, configured in `.claude/settings.json`):

- `.claude/hooks/docs-drift-check.sh` — Stop hook. If the turn modified code under `src/perch/` / `perch/` / `data/` without touching `docs/` or `CLAUDE.md`, emits a reminder about the no-documentation-debt rule. Silent when there's no drift. Never blocks.
- `.claude/hooks/python-post-edit.sh` — PostToolUse hook on `Edit`/`Write`. Runs `ruff check` (report-only) on any edited `.py` file, so issues surface in the next tool result instead of CI. No-op before M1 creates the dev env.

**Project-local skill:**

- `/perch-docs-check` — on-demand drift scan across `docs/`. Grep-based, read-only, no subagents. Invoke after non-trivial doc changes and before `/release`.

**Built-in skills and subagents to prefer over bespoke work:**

- `/audit` → drives `/mnt/Storage/Scripts/Linux/3D_Engine/tools/audit/audit.py` against the project using Perch's `audit_config.yaml` at the repo root. Pipes raw findings through the `audit-triage` subagent and returns only the actionable list. The config includes Perch-specific drift detectors (retired KWin API symbols, swapped libraries like `dbus-next` / `python-ewmh`, deprecated `asyncio.get_event_loop()`, Python 3.11 floor strays). Reports write to `.audit/report.md` (gitignored). Use after any non-trivial batch of code changes.
- `/feature-test` → scaffolds a regression test (spec.md + test file + CMake/pytest wiring) via the `feature-test-writer` subagent. Use after every bug fix.
- `/triage` → locate the subsystem responsible for a vague bug report; proposes a fix plan. Use when a bug report doesn't pin a file.
- `/simplify`, `/review`, `/security-review` — quality passes on changed code.
- `/bump`, `/release` — once `.claude/bump.json` is populated at M8/M9, these run the release flow.
- `general-purpose` subagent — for web research (e.g. the Phase 2 / 2.5 research dispatches). Isolates the research round-trip from the main context window.
- `Explore` subagent — for broad codebase surveys.
- `Plan` subagent — for design-intensive planning that shouldn't pollute the main context.

**Not added deliberately:** no project-specific subagents. The built-ins cover everything Perch needs; adding more would only fragment attention.

**Permission allowlist** (`.claude/settings.json`): safe read-only dev commands (`git status/log/diff`, `ruff check`, `mypy`, `pytest --collect-only`, `appstream-util validate`, `desktop-file-validate`, `xmllint --noout`, stdlib `python` version / package inspection). Anything destructive or with side effects still prompts.
