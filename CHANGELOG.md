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

### Changed

### Deprecated

### Removed

### Fixed

### Security

[Unreleased]: https://github.com/milnet01/perch/tree/main
