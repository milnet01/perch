# Flathub submission — notes and checklist

Perch cannot actually be submitted to Flathub until it has a tagged release artefact (Flathub's review process needs something to build). This document records what's already done, what remains, and the exact steps for the final submission at M8/M9.

## Current state (Phase 0–3)

- **App ID reserved (de facto)**: `io.github.milnet01.Perch`. The ID follows GitHub reverse-DNS per Flathub convention. Reservation is implicit — nobody else will use this ID because only `milnet01` on GitHub can.
- **Manifest scaffold**: `packaging/flathub/io.github.milnet01.Perch.yml` in this repo. References `v1.0.0` as a placeholder tag; must be replaced with the real tag at submission time.
- **Dependencies not in `org.kde.Platform`**: `sdbus`, `qasync`, `python-xlib`, `tomlkit`. Each needs a generated include file (see §3 below).
- **Runtime target**: KDE Platform 6.8 (current Flathub LTS tier as of April 2026).

## What must exist before submitting

1. **A tagged release** (`v1.0.0`) on `milnet01/perch` with a source tarball GitHub generates automatically.
2. **`data/io.github.milnet01.Perch.desktop`** — populated. Built at M3.
3. **`data/io.github.milnet01.Perch.metainfo.xml`** — populated with screenshots, summary, description, release history mirrored from `CHANGELOG.md`. Validated with `appstream-util validate-relax --nonet`. Built at M8.
4. **Screenshots** committed under `docs/screenshots/` and referenced from the metainfo. Minimum one; ideally three.
5. **`src/perch/backends/kwin/script/`** populated with `metadata.json` and `contents/code/main.js`.
6. **Generated Python-dep include files**:
   ```bash
   # From https://github.com/flatpak/flatpak-builder-tools/tree/master/pip
   python3 flatpak-pip-generator sdbus
   python3 flatpak-pip-generator qasync
   python3 flatpak-pip-generator python-xlib
   python3 flatpak-pip-generator tomlkit
   ```
   Each run produces `python3-<name>.yml` in the cwd. Drop these into `packaging/flathub/` next to the manifest.

## Submission steps (at M8/M9, not now)

Flathub documents the full flow at <https://docs.flathub.org/docs/for-app-authors/submission>. Perch's specifics:

1. **Fork `flathub/flathub`** on GitHub (an empty repo — the fork is a convention).
2. **Create a branch** named `new-pr/io.github.milnet01.Perch`.
3. **Add two files** on that branch:
   - `io.github.milnet01.Perch.yml` — the manifest, with the real tagged commit pinned.
   - Any generated `python3-*.yml` include files the manifest references.
4. **Test locally** first:
   ```bash
   flatpak-builder --user --install --force-clean build-dir io.github.milnet01.Perch.yml
   flatpak run io.github.milnet01.Perch
   ```
5. **Open the PR** at `flathub/flathub` using the `new-pr/` branch. Title: `New: Perch — persistent window geometry manager`.
6. **Review cycle**:
   - Reviewers will run the manifest through Flathub's automated checker.
   - Common asks: tighten `finish-args`, add a more detailed metainfo description, include screenshots.
   - Budget 2–6 weeks for the first review round.
7. **Merge**: on approval, Flathub merges the manifest into `flathub/flathub`, which triggers their build infrastructure to create the actual per-app repo `flathub/io.github.milnet01.Perch` and first build.

## Why we're not opening a speculative PR now

Flathub explicitly asks submitters to have a buildable release. Opening a PR with `v1.0.0` as an unresolvable tag wastes reviewer time and trains a "Perch's submitter is sloppy" association that the project doesn't want. The correct move is to get the manifest and include files ready **in this repo**, then submit only once M8 ships.

## Ownership of the eventual `flathub/io.github.milnet01.Perch` repo

After the first submission merges, Flathub creates a dedicated per-app repo (`flathub/io.github.milnet01.Perch`) and grants commit access to the app maintainer. Subsequent updates are PRs against **that** repo, not against `flathub/flathub`. Standard update cadence: one PR per Perch release, updating the tag and any changed dep includes.

## Follow-up links

- Flathub contributor docs: <https://docs.flathub.org/>
- `org.kde.Platform` version tracker: <https://invent.kde.org/flatpak/flatpak-kde-runtime>
- flatpak-builder-tools (pip generator): <https://github.com/flatpak/flatpak-builder-tools/tree/master/pip>
- `appstream-util` reference: <https://www.freedesktop.org/software/appstream-glib/appstream-util.1.html>

## Doc-drift note

When M8 submits this to Flathub, update `docs/10-packaging.md` to change the Flathub channel's status from **planned/target** to **submitted / in review / live** as the PR progresses. Per the no-documentation-debt rule.
