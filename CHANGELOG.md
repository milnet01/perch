# Changelog

All notable changes to Perch are documented here.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Sections under each release are populated on a best-effort basis — empty sections are omitted at release time.

## [Unreleased]

### Added

- Phase 0 bootstrap: LICENSE (GPL-3.0-or-later), README, CONTRIBUTING, CODE_OF_CONDUCT, `.github/` templates, `pyproject.toml` scaffold.
- Phase 1 design docs: `docs/00-overview.md` through `docs/11-roadmap.md` — twelve docs covering architecture, backend interface, state format, per-backend designs (X11, KWin, stubs), rules engine, UI, layouts/profiles, packaging, and the phased roadmap.
- Phase 2 validation: stack swaps (`dbus-next` → `sdbus-python`, `python-ewmh` → `python-xlib`), GNOME floor raised to 48, pre-paint placement declared best-effort.
- Phase 2.5 implementation-readiness: concrete 2026 version pins, canonical qasync bootstrap pattern, KWin IPC long-poll design (replaces the original tight-polling sketch), concrete X11 patterns.
- Project tooling under `.claude/`: docs-drift Stop hook, Python post-edit ruff hook, `/perch-docs-check` skill, permission allowlist.
- `audit_config.yaml` wired to the /audit pipeline with Perch-specific drift detectors.
- Icon: `data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg` (stylised crested bird on a perch; symbolic-ready, scales cleanly).
- `CHANGELOG.md` (this file) and `packaging/flathub/` scaffolds for the eventual Flathub submission.
- **M1 — Skeleton + config:** `src/perch/` package with the canonical `asyncio.run(main(), loop_factory=QEventLoop)` entry point; config subsystem (`tomllib` read, `tomlkit` comment-preserving write, atomic-write recipe, schema validation, migration registry); `RotatingFileHandler` logging + Qt → Python bridge; XDG path helpers; `AppState`. `perch --version` / `perch` / `perch --debug` all work end-to-end.
- **M1 test suite:** pytest covering schema validation, loader fallback to `config.toml.bak`, atomic-write semantics, logging wiring, XDG path resolution, CLI exit codes, and the release-blocking tomlkit round-trip fixture.
- **M1 CI:** GitHub Actions matrix (Ubuntu 24.04 × Python 3.12 / 3.13 / 3.14) running `ruff`, `mypy --strict`, and `pytest`. PySide6 installed from PyPI to step over Ubuntu 24.04's 6.4 distro package.
- `docs/contributing-dev-setup.md` covering editable install, smoke-test, and the house rules.
- **`apply = { maximized = true | false }` rule vocabulary** (design, lands in code with the rules engine at M2). Toggles the compositor's native maximized state via `WindowBackend.set_state(wid, WindowState.MAXIMIZED)`, distinct from the existing `geometry = "maximize"` preset which writes a work-area-sized rectangle. Sway and Hyprland raise `BackendUnsupported` for the maximize state (their tiling models have no equivalent); the core substitutes work-area geometry and logs at DEBUG. Documented in `docs/02-state-format.md` §Apply actions, `docs/07-rules-engine.md` §Apply order + §Validation, `docs/06-backend-stubs.md` (Sway, Hyprland).
- **M2.a — Backend interface + MockBackend + compliance suite:** `src/perch/backend/` package — `types.py` (frozen dataclasses, `WindowType`/`WindowState` enums, `Capabilities`), `base.py` (error taxonomy + `WindowBackend` abstract base class extending `QObject` with the event signal surface), `mock.py` (`MockBackend` with a driver API — `_spawn_window`, `_move_window`, output lifecycle, `_fire_hotkey`, `_fail_state` for the MAXIMIZED fallback contract). Reusable compliance tests at `tests/backend/test_compliance.py` parameterised over `BACKEND_CLASSES` in `tests/backend/conftest.py` — covers lifecycle, shape validation, capability↔behaviour alignment, event ordering, and the error taxonomy (22 new tests; 66 total green).
- **M2.b — Profiles + topology:** `src/perch/core/profiles.py` — `Profile` / `ProfileOverride` dataclasses, `compute_topology_key(outputs)` (sorted, connected-only, refresh/scale/serial deliberately excluded per `docs/09`), `parse_profiles(raw)` (validates duplicate names, duplicate topologies, malformed segments, and unknown keys), and `select_profile(profiles, key)` (first-match-wins). `config/schema.py::validate` now delegates `[[profiles]]` to the typed parser; `Config.profiles` is `list[Profile]` instead of `list[dict]`. 28 new tests; 94 total green.

### Changed

- `pyproject.toml`: hatchling `src/`-layout wheel + sdist config wired; `tool.hatch.version` sources `__version__` from the package; `ruff.target-version` lifted from the stray `py311` to `py312` to match the locked Python floor; `mypy --strict` and `pytest-qt`/`asyncio_mode = "auto"` knobs added.
- **Backend lifecycle methods renamed `connect()` / `disconnect()` → `start()` / `stop()`** to avoid the collision with `QObject.connect` / `QObject.disconnect` (Qt's signal/slot staticmethods). Signal names (`backend_connected`, `backend_disconnected`) are unchanged. Docs updated across `01-architecture.md`, `03-backend-interface.md`, `05-backend-kwin.md`, `06-backend-stubs.md`, `11-roadmap.md`.

### Deprecated

### Removed

### Fixed

### Security

[Unreleased]: https://github.com/milnet01/perch/tree/main
