# Flathub submission — notes and checklist

## TL;DR — one-shot submission

```bash
./packaging/submit/flathub.sh            # stage only — review the diff
./packaging/submit/flathub.sh --push     # push fork + open PR on Flathub
```

Prerequisites:
- `gh` authed (already done).
- `flatpak-builder` installed (`zypper install flatpak-builder` on
  Tumbleweed, `dnf install flatpak-builder` on Fedora, etc.).
- `org.kde.Platform//6.8` + `org.kde.Sdk//6.8` flatpak runtimes (the
  script installs them if missing).

The script clones `flatpak-builder-tools`, regenerates
`python3-*.yml` dep includes from the pyproject.toml pins, forks
`flathub/flathub`, stages the manifest + generated includes on a
branch named after the app id, and runs a local build smoke test.
By default it stops there so you can review the diff; `--push`
completes the submission by pushing the fork branch and opening the
PR via `gh`.

The rest of this doc explains what's under the hood — read if the
script fails, you need to modify the deps list, or you're bringing
up a new Flathub channel (e.g. Beta).

---

This document records what's already done, what remains, and the
exact steps for the Flathub submission (both automated and manual).

## Current state (through M8)

- **App ID reserved (de facto)**: `io.github.milnet01.Perch`. The ID follows GitHub reverse-DNS per Flathub convention. Reservation is implicit — nobody else will use this ID because only `milnet01` on GitHub can.
- **Manifest finalised**: `packaging/flathub/io.github.milnet01.Perch.yml`. Tightened `finish-args` to the minimum set (no `--device=dri` — Perch doesn't render a 3D surface; Qt's tray icon and `QDialog` work on llvmpipe); per-service `--talk-name` instead of an open-name allowlist; KWin script install path corrected (`src/perch/backend/kwin/` — the package name is singular). Still references `v1.0.0` as a placeholder tag; replaced with the real tag at submission time.
- **Dependencies not in `org.kde.Platform`**: `sdbus`, `qasync`, `python-xlib`, `tomlkit`. Each needs a generated include file (see §"Generated Python-dep include files" below).
- **Runtime target**: KDE Platform 6.8 (current Flathub LTS tier as of April 2026).
- **Metainfo + desktop entry validated**: `appstream-util validate-relax --nonet` and `desktop-file-validate` are part of the CI packaging job (`.github/workflows/ci.yml`), so submission-blockers surface in every PR.

## What must exist before submitting

1. **A tagged release** (`v1.0.0`) on `milnet01/perch` with a source tarball GitHub generates automatically.
2. **`data/io.github.milnet01.Perch.desktop`** — populated (landed M3.e).
3. **`data/io.github.milnet01.Perch.metainfo.xml`** — populated with screenshots, summary, description, release history mirrored from `CHANGELOG.md` (landed M3.e; validated in CI as of M8.f).
4. **Screenshots** committed under `docs/screenshots/` and referenced from the metainfo (landed M3.e).
5. **`src/perch/backend/kwin/script/`** populated with `metadata.json` and `contents/code/main.js` (landed M5.a).
6. **Generated Python-dep include files** (regenerated at submission, not committed — see §Generated Python-dep include files below).

## Generated Python-dep include files

Flatpak builds run without network access, so the manifest needs each
Python dependency's source URL and SHA-256 pinned inline. The
`flatpak-pip-generator` tool from `flatpak-builder-tools` produces one
`python3-<pkg>.yml` per dep that wires those pins as a buildsystem-simple
module.

**Not committed to this repo.** These files are regenerated at each
submission / dep bump because they bind to a specific dep version, and
committing them creates a second place to update on every bump — which
reliably drifts from `pyproject.toml` and produces build failures that
are painful to debug.

Regen command (run from `packaging/flathub/`):

```bash
git clone https://github.com/flatpak/flatpak-builder-tools.git /tmp/fbt
python3 /tmp/fbt/pip/flatpak-pip-generator \
    --yaml \
    --output python3-sdbus    sdbus
python3 /tmp/fbt/pip/flatpak-pip-generator \
    --yaml \
    --output python3-qasync   qasync
python3 /tmp/fbt/pip/flatpak-pip-generator \
    --yaml \
    --output python3-xlib     python-xlib
python3 /tmp/fbt/pip/flatpak-pip-generator \
    --yaml \
    --output python3-tomlkit  tomlkit
```

Then uncomment the four `python3-*.yml` lines in the manifest's
`modules:` list.

## Submission steps (at M9, not now)

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

## History — why we held the PR until v1.0.0

Flathub explicitly asks submitters to have a buildable release. M8
authored the manifest and the `packaging/submit/flathub.sh` runbook
in-repo so the PR could be opened the same day `v1.0.0` tagged,
with nothing speculative landing in `flathub/flathub`.

## Ownership of the eventual `flathub/io.github.milnet01.Perch` repo

After the first submission merges, Flathub creates a dedicated per-app repo (`flathub/io.github.milnet01.Perch`) and grants commit access to the app maintainer. Subsequent updates are PRs against **that** repo, not against `flathub/flathub`. Standard update cadence: one PR per Perch release, updating the tag and any changed dep includes.

## Follow-up links

- Flathub contributor docs: <https://docs.flathub.org/>
- `org.kde.Platform` version tracker: <https://invent.kde.org/flatpak/flatpak-kde-runtime>
- flatpak-builder-tools (pip generator): <https://github.com/flatpak/flatpak-builder-tools/tree/master/pip>
- `appstream-util` reference: <https://www.freedesktop.org/software/appstream-glib/appstream-util.1.html>

## Doc-drift note

When M8 submits this to Flathub, update `docs/10-packaging.md` to change the Flathub channel's status from **planned/target** to **submitted / in review / live** as the PR progresses. Per the no-documentation-debt rule.
