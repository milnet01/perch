# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Perch** — a persistent, compositor-aware window geometry manager for Linux desktops. Sits in the system tray, remembers where each window belongs, and restores geometry (position, size, monitor, virtual desktop) when a window reopens. Also offers snap presets, named layouts, a rules engine, and per-monitor profiles.

Home: https://github.com/milnet01/perch — license: **GPL-3.0-or-later**.

## Current phase

Perch is at **v1.0.0**. Phases 0–4 are complete. Live and planned work is `ROADMAP.md` at the repo root (`PERC-NNNN` items, backed by the roadmap store); `docs/11-roadmap.md` holds the per-milestone history, the ground rules and the research logs; `CHANGELOG.md` has release notes.

Phase sequence:

0. Repo bootstrap — **done**.
1. Design docs — **done**.
2. Review + online research to validate design assumptions — **done**.
3. Revise docs based on findings — **done**.
4. Implementation (M1…M9) — **done**.

## Roadmap lives in the store, not the file (hard rule)

`ROADMAP.md` is a **generated render** of the roadmap store — the store is the
source of truth. Do not hand-edit `ROADMAP.md`: the next `roadmap_log` write
re-renders the whole file and silently reverts your edit. Add and change items
with the Ants MCP verbs (`roadmap_log` op `append` / `append_batch` / `flip` /
`annotate`), and query with `roadmap_query` rather than reading the file.

Two things that will otherwise look like bugs. The renderer **strips the
trailing full stop from every `**Layman:**` line** and reports it as restyling,
so a hand-added period will vanish. And a byte-identical `ROADMAP.md` right
after a migration is correct — the file is re-rendered by the next write, not
by the migration itself.

Milestone history, ground rules and the Phase 2 / 2.5 research logs stay in
`docs/11-roadmap.md`, which is an ordinary hand-edited document. Roughly thirty
citations from `src/`, `tests/`, `pyproject.toml` and `audit_config.yaml` point
into it — do not rename or restructure it casually.

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

Every dependency — runtime library, dev/test tool, CI action, Python runtime, base image — runs the **latest stable version** (a security posture as much as a feature one: the latest release is the one getting security patches). Two things justify a cap below latest: a **confirmed breakage** (needs an inline reason *and* a Broken-version-register row, same change) or a precautionary **upper-bound ceiling** (usually `<next-major`) that must be tested and lifted when the guarded version ships. The full standard, register, ceiling list, and the currency-sweep command live in [`docs/dependency-policy.md`](docs/dependency-policy.md) (run the sweep each release cycle and whenever you touch a manifest); packaged-runtime version constraints live in [`docs/10-packaging.md`](docs/10-packaging.md).

## Never push without a green `local_CI.sh` (hard rule)

`./local_CI.sh` runs the same test, docs and packaging checks as `.github/workflows/ci.yml` (every job), including the test job once per interpreter in CI's matrix — it reads the versions out of `ci.yml` and builds a `uv`-managed environment per version under `.venvs/`, so a version-specific failure cannot slip past a green local run. A matrix entry this machine cannot build fails the gate rather than being skipped. Run it and get `safe to push` **before every push** — a red push burns a CI run to tell us what the script would have caught in seconds. If you edit `ci.yml`, edit `local_CI.sh` in the same commit; they must never drift. Fuller dev-setup detail: [`docs/contributing-dev-setup.md`](docs/contributing-dev-setup.md).

## Tech stack

- **Language:** Python 3.12+
- **UI toolkit:** PySide6 (Qt ≥ 6.8) — tray icon via `QSystemTrayIcon`, config dialog in Qt Widgets, integrates naturally on KDE.
- **Async glue:** `qasync` — one event loop drives both Qt and asyncio.
- **D-Bus:** `sdbus-python` (async, C-backed via libsystemd). `dbus-next` was the initial pick but is effectively dormant upstream since 2022; swapped during Phase 2 research (see `docs/11-roadmap.md` findings log).
- **X11:** `python-xlib` directly, with a small in-tree EWMH wrapper. `python-ewmh` was the initial pick but is unmaintained since 2017 and not packaged on Fedora/openSUSE.
- **Packaging:** Hatchling build backend; Flatpak manifest for Flathub; RPM spec for openSUSE OBS, which builds the Fedora RPM too; PKGBUILD for AUR.

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
  ROADMAP.md            ← live + planned work (PERC-NNNN, roadmap-store backed)
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

`/mnt/Games/Scripts/Linux/perch/` sits under the games-and-scripts drive at `/mnt/Games/`. See `/mnt/Games/CLAUDE.md` for drive-wide conventions — notably, use `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A` instead of bare `sudo` for any privileged command. The `/mnt/Storage/` paths older documents cite are retired; the drive was failing and everything moved here.

## Working notes for future Claude sessions

- The project directory was renamed from `window_manager` to `perch` on 2026-04-20. If you see stale references to `window_manager`, fix them.
- The user prefers short, terse responses and explicit phased plans for non-trivial work (see auto-memory `feedback_workflow.md`).
- When in doubt on a design call, write the doc first and let the user review before writing code.

## Project tooling (Claude Code)

The repo ships with a small amount of Claude-Code-specific tooling at `.claude/`. Use it rather than reimplementing equivalent logic ad hoc.

**Hooks** (run automatically, configured in `.claude/settings.json`):

- `.claude/hooks/docs-drift-check.sh` — Stop hook. If work that has not left this machine — uncommitted changes plus commits ahead of the upstream — touches code under `src/perch/` / `perch/` / `data/` without touching `docs/` or `CLAUDE.md`, emits a reminder about the no-documentation-debt rule. It looks past the commit deliberately: scoped to the working tree alone it went silent the moment the turn committed, which is the normal flow. Silent when there's no drift. Never blocks.
- `.claude/hooks/python-post-edit.sh` — PostToolUse hook on `Edit`/`Write`. Runs `ruff check` (report-only) on any edited `.py` file, so issues surface in the next tool result instead of CI. A no-op where the dev environment is absent.

**Project-local skill:**

- `/perch-docs-check` — on-demand drift scan across `docs/`. Grep-based, read-only, no subagents. Invoke after non-trivial doc changes and before `cut-release`.

**Built-in skills and subagents to prefer over bespoke work:**

- `check-code` → the routine static-analysis sweep. Runs the tools Perch's languages call for and names every applicable tool that did **not** run, with the reason.
- `write-test` → writes the test that fails before the fix exists and proves it red by running it. Use after every bug fix.
- `locate-defect` → narrows a vague bug report to one file:line and one testable hypothesis. Use when a report doesn't pin a file.
- `review-code`, `review-tests`, `review-contract`, `close-findings` → the cold-review family. The first three report and stop; `close-findings` is where a findings list goes.
- `/simplify`, `/code-review`, `/security-review` — built-in commands, diff- or branch-scoped, where the skills above are corpus-scoped.
- The **Perch-specific drift analyser** is a hand-invoked extra that `check-code` does not cover: `audit_config.yaml` at the repo root carries detectors for retired KWin API symbols, swapped libraries (`dbus-next` / `python-ewmh`), `asyncio.get_event_loop()`, and Python 3.11 floor strays. Run it with `python3 /mnt/Games/Scripts/Linux/Vestige/tools/audit/audit.py --config audit_config.yaml` — the analyser lives under a neighbouring project by historical accident, not by design. Reports write to `.audit/` (gitignored).
- `cut-release` — drives the release flow end to end (pre-flight → bump → build/test → `local_CI.sh` → commit → tag → push → publish), wired to `.claude/bump.json`. `cut-release --check` is the read-only readiness report and the cheapest way to ask "can we ship?".
- `general-purpose` subagent — for web research (e.g. the Phase 2 / 2.5 research dispatches). Isolates the research round-trip from the main context window.
- `Explore` subagent — for broad codebase surveys.
- `Plan` subagent — for design-intensive planning that shouldn't pollute the main context.

**Not added deliberately:** no project-specific subagents. The built-ins cover everything Perch needs; adding more would only fragment attention.

**Permission allowlist** (`.claude/settings.json`): safe read-only dev commands (`git status/log/diff`, `ruff check`, `mypy`, `pytest --collect-only`, `appstream-util validate`, `desktop-file-validate`, `xmllint --noout`, stdlib `python` version / package inspection). Anything destructive or with side effects still prompts.
