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
- **KWin bundled-script version** — `BUNDLED_SCRIPT_VERSION` in `src/perch/backend/kwin/__init__.py`. It moves only when the bundled KWin JS script's protocol changes, per [05-backend-kwin.md](05-backend-kwin.md) §"Script installation strategy". It is deliberately **not** listed in `.claude/bump.json`.

## Version-bearing files (must stay in lockstep)

`cut-release` rewrites these nine files, wired as eleven entries in
`.claude/bump.json` (`.SRCINFO` and `README.md` each carry the version in two
distinct shapes). They must all carry the same version at every release:

| File | Field | Occurrences |
|---|---|---|
| `pyproject.toml` | `version = "X.Y.Z"` — the canonical source the rest are checked against | 1 |
| `src/perch/__init__.py` | `__version__ = "X.Y.Z"` | 1 |
| `packaging/rpm/perch.spec` | `Version:        X.Y.Z` | 1 |
| `packaging/aur/PKGBUILD` | `pkgver=X.Y.Z` | 1 |
| `packaging/aur/.SRCINFO` | `pkgver = X.Y.Z`, and `source =` (tarball name + archive URL) | 2 |
| `packaging/flathub/io.github.milnet01.Perch.yml` | `tag: vX.Y.Z` | 1 |
| `README.md` | `**Status:** vX.Y.Z`, and the AppImage download filename | 1 + 3 |
| `packaging/appimage/README.md` | the AppImage download filename | 2 |
| `data/io.github.milnet01.Perch.metainfo.xml` | the two screenshot URLs pinned to the release tag | 2 |

The last three are not packaging metadata but are machine-consequential all the
same: `packaging/appimage/build.sh` derives the AppImage filename from
`pyproject.toml`, so a README left behind names a file the release does not
carry; and the metainfo screenshot URLs are what software centres display for
the *current* version.

Do not hand-edit these individually — `cut-release <version>` edits all eleven
entries and runs `tools/version_lockstep_check.py` to verify lockstep. Editing
one and forgetting another is the failure this recipe exists to prevent.

`tools/version_lockstep_check.py` reads the file list out of `.claude/bump.json`
rather than repeating it, so adding a file to the recipe is enough to put it
under the check. It asks two questions per entry: whether the new text is there
at all, and whether *every* line of that shape carries the canonical version —
the second being what catches a partial rewrite of a filename the README names
three times.

**Not listed, deliberately** — beyond the two independent version lines above,
the GNOME extension's own version in
`src/perch/backend/mutter/extension/extension.js`; CHANGELOG headings and the
metainfo `<release>` blocks, which record what happened once and would be made
false by a bump; and the spec and PKGBUILD excerpts in
[10-packaging.md](10-packaging.md), which are illustrative sketches rather than
machine-read fields.

## CHANGELOG

`CHANGELOG.md` is **Keep a Changelog 1.1.0**: an `## [Unreleased]` section with the six standard buckets (Added / Changed / Deprecated / Removed / Fixed / Security), and one dated `## [X.Y.Z] — YYYY-MM-DD` section per release. Empty buckets are omitted at release time. Entries accrue under `[Unreleased]` as work lands; the release step promotes them to a dated header.

## Release flow

This is the authoritative release sequence; the `cut-release` skill drives it end to end. [10-packaging.md](10-packaging.md) §Release mechanics covers the per-channel packaging specifics (what CI builds, how each downstream channel updates), not a competing sequence.

1. **Content first** — promote `[Unreleased]` in `CHANGELOG.md` to a dated `## [X.Y.Z] — YYYY-MM-DD` header (em dash, matching §CHANGELOG above). `cut-release` checks this section exists and refuses to run without it; it never drafts one from `git log`. Confirm every roadmap ID the section cites is already ✅ in the roadmap store — an ID still 📋 stops the release.
2. **`cut-release <X.Y.Z>`** — rewrites the version-bearing files above, runs `tools/version_lockstep_check.py` to verify lockstep, then prepends the matching `<release>` entry to `data/io.github.milnet01.Perch.metainfo.xml` (a recipe todo; its body mirrors the CHANGELOG and is drafted by the changelog-writer subagent in mode A).
3. **Build and test the bumped tree**, then run `./local_CI.sh` — on the bumped tree, before the commit, not before the push. A failure found here costs an edit; found after the tag it costs a moved tag, which [10-packaging.md](10-packaging.md) forbids once anyone has fetched it.
4. **Commit** `release: vX.Y.Z`, then **tag** `vX.Y.Z` (annotated, its body the CHANGELOG section — the `tag` template is in `bump.json`).
5. **Push** (public repo — CI minutes free; a release push goes without asking, per [git-commit-standards.md](git-commit-standards.md)).
6. **Publish** the GitHub release, notes verbatim from the CHANGELOG section.
7. **CI on release publish** — `.github/workflows/release.yml` builds the self-contained AppImage on GitHub's runners (`packaging/appimage/build.sh`) and attaches it, plus a `SHA256SUMS.txt`, to the GitHub release as the end-user download. It triggers on release publish and via `workflow_dispatch` with a tag input; it does **not** touch `ci.yml`, so the `local_CI.sh` lockstep is unaffected. The release therefore carries no assets until this run finishes.
8. Downstream channels (Flathub PR, OBS, AUR, KDE Store) follow as described in the packaging doc. OBS builds from an uploaded release tarball — there is no `_service` file, and one must not be reinstated (see [10-packaging.md](10-packaging.md)).

## Integrity

Release artefacts are SHA256-summed — the AppImage's `SHA256SUMS.txt` is attached to the release; source-tarball sums go in the release notes. No GPG signing in v1; GitHub's release signatures are the tamper-evident story ([10-packaging.md](10-packaging.md) §Signed binaries).

## See also

- [10-packaging.md](10-packaging.md) — §Versioning, §Release mechanics, §AppImage, §Signed binaries (the authoritative mechanical checklist).
- [dependency-policy.md](dependency-policy.md) — dependency-currency standard; run the sweep each release cycle.
