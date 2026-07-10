# Versioning & release standard

How Perch numbers releases and how a version reaches users. The mechanical checklist lives in [10-packaging.md](10-packaging.md) §Release mechanics; this doc states the policy and the lockstep invariant behind it.

## SemVer policy

Perch follows **Semantic Versioning 2.0.0** — `MAJOR.MINOR.PATCH`. CHANGELOG.md declares the adherence at its head.

For this app the bump rules read as:

- **MAJOR** — a breaking change to a user-facing contract: the config/state schema in an incompatible way, the `WindowBackend` interface as consumed by out-of-tree backends, or removal of a documented feature/CLI surface.
- **MINOR** — backward-compatible new capability: a new backend, snap preset, rules-engine feature, UI pane, or packaging channel.
- **PATCH** — backward-compatible bug fixes and internal changes with no new surface.

Two version lines are **independent** of the app version and never move with it:

- **Config/state schema version** — see [02-state-format.md](02-state-format.md).
- **KWin bundled-script version** — `BUNDLED_SCRIPT_VERSION` in `src/perch/backend/kwin/__init__.py` (currently `1.1.2`). It moves only when the bundled KWin JS script's protocol changes, per [05-backend-kwin.md](05-backend-kwin.md) §Version pinning. It is deliberately **not** listed in `.claude/bump.json`.

## Version-bearing files (must stay in lockstep)

`/bump` rewrites exactly these five files, wired in `.claude/bump.json`. They must all carry the same version at every release:

| File | Field |
|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `src/perch/__init__.py` | `__version__ = "X.Y.Z"` |
| `packaging/rpm/perch.spec` | `Version:        X.Y.Z` |
| `packaging/aur/PKGBUILD` | `pkgver=X.Y.Z` |
| `packaging/flathub/io.github.milnet01.Perch.yml` | `tag: vX.Y.Z` |

Do not hand-edit these individually — `/bump <version>` edits all five and runs its post-check to verify lockstep. Editing one and forgetting another is the failure this recipe exists to prevent.

## CHANGELOG

`CHANGELOG.md` is **Keep a Changelog 1.1.0**: an `## [Unreleased]` section with the six standard buckets (Added / Changed / Deprecated / Removed / Fixed / Security), and one dated `## [X.Y.Z] — YYYY-MM-DD` section per release. Empty buckets are omitted at release time. Entries accrue under `[Unreleased]` as work lands; the release step promotes them to a dated header.

## Release flow

The full checklist is [10-packaging.md](10-packaging.md) §Release mechanics; in outline:

1. **Content first** — promote `[Unreleased]` in `CHANGELOG.md` to a dated `## [X.Y.Z]` header, and add the matching `<release>` entry to `data/io.github.milnet01.Perch.metainfo.xml` (its body mirrors the CHANGELOG). These are content changes, so they sit outside `bump.json` and are drafted by the changelog-writer subagent.
2. **`/bump <X.Y.Z>`** — rewrites the five version-bearing files above; verifies lockstep.
3. **Commit** `release: vX.Y.Z`, then **tag** `vX.Y.Z` (templates in `bump.json` `post_bump`).
4. **Push** (public repo — CI minutes free; gate on green `local_CI.sh` first, per [git-commit-standards.md](git-commit-standards.md)).
5. **CI on release publish** — `.github/workflows/release.yml` builds the self-contained AppImage on GitHub's runners (`packaging/appimage/build.sh`) and attaches it, plus a `SHA256SUMS.txt`, to the GitHub release as the end-user download. It triggers on release publish and via `workflow_dispatch` with a tag input; it does **not** touch `ci.yml`, so the `local_CI.sh` lockstep is unaffected.
6. Downstream channels (Flathub PR, OBS `_service`, COPR, AUR, KDE Store) follow as described in the packaging doc.

The **`/release`** skill drives this checklist end to end (`/bump` → drift check → build → test → commit → push).

## Integrity

Release artefacts are SHA256-summed — the AppImage's `SHA256SUMS.txt` is attached to the release; source-tarball sums go in the release notes. No GPG signing in v1; GitHub's release signatures are the tamper-evident story ([10-packaging.md](10-packaging.md) §Signed binaries).

## See also

- [10-packaging.md](10-packaging.md) — §Versioning, §Release mechanics, §AppImage, §Signed binaries (the authoritative mechanical checklist).
- [dependency-policy.md](dependency-policy.md) — dependency-currency standard; run the sweep each release cycle.
