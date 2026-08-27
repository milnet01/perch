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
- The runtimes:
  ```sh
  flatpak install flathub org.kde.Platform//6.11 org.kde.Sdk//6.11 \
      io.qt.PySide.BaseApp//6.11 org.flatpak.Builder
  ```

The script owns none of the work itself — it runs the pieces in the
order a submission needs. It confirms `python3-deps.yaml` still matches
`pyproject.toml` (by regenerating and diffing), builds the manifest in
submission mode, runs Flathub's own linter, then forks `flathub/flathub`
and stages the three submission files on a branch cut from `new-pr`. By
default it stops there; `--push` opens the PR.

The rest of this doc explains what's under the hood — read if the
script fails, you need to modify the deps list, or you're bringing
up a new Flathub channel (e.g. Beta).

---

This document records what's already done, what remains, and the
exact steps for the Flathub submission (both automated and manual).

## Current state (through M8)

- **App ID reserved (de facto)**: `io.github.milnet01.Perch`. The ID follows GitHub reverse-DNS per Flathub convention. Reservation is implicit — nobody else will use this ID because only `milnet01` on GitHub can.
- **Manifest**: `packaging/flathub/io.github.milnet01.Perch.yml`, pinned to the `v1.0.0` tag and its immutable commit. `finish-args` is the minimum set that still works: no `--device=dri` (Perch renders no 3D surface; the tray icon and dialogs work on llvmpipe), and named `--talk-name` entries rather than a session-bus socket.
- **Runtime target**: KDE Platform 6.11, with `io.qt.PySide.BaseApp//6.11` supplying PySide6 and Qt. The BaseApp is built against that same runtime, and ships python 3.13 — which is the ABI the pinned wheels target.
- **Dependencies not supplied by the runtime or the BaseApp**: `qasync`, `sdbus`, `python-xlib`, `tomlkit`, plus the `hatchling` build backend. All are sha256-pinned in the committed `python3-deps.yaml`.
- **Metainfo + desktop entry validated**: `appstream-util validate-relax --nonet` and `desktop-file-validate` are part of the CI packaging job (`.github/workflows/ci.yml`), so submission-blockers surface in every PR.

## What must exist before submitting

1. **A tagged release** (`v1.0.0`) on `milnet01/perch` with a source tarball GitHub generates automatically.
2. **`data/io.github.milnet01.Perch.desktop`** — populated (landed M3.e).
3. **`data/io.github.milnet01.Perch.metainfo.xml`** — populated with screenshots, summary, description, release history mirrored from `CHANGELOG.md` (landed M3.e; validated in CI as of M8.f).
4. **Screenshots** committed under `docs/screenshots/` and referenced from the metainfo (landed M3.e).
5. **`src/perch/backend/kwin/script/`** populated with `metadata.json` and `contents/code/main.js` (landed M5.a).
6. **`python3-deps.yaml`**, committed and current — see §The pinned dependency closure below.

## The pinned dependency closure

Flathub's builders have no network, so every dependency must arrive as a
sha256-pinned source. `packaging/flathub/generate-pip-sources.sh` produces
that closure as a single `python3-deps.yaml`, and **it is committed**.

It reads `[project.dependencies]` from `pyproject.toml` (minus PySide6,
which the BaseApp supplies and which the generator refuses to pin for that
reason) plus `[build-system].requires`, so `pyproject.toml` stays the one
source of truth. The build backend is in there because the manifest
installs Perch with `--no-build-isolation`; with isolation on, pip would
try to fetch `hatchling` from PyPI and the offline build would fail.

```sh
packaging/flathub/generate-pip-sources.sh   # needs network; the build does not
```

It needs `requirements-parser` and `PyYAML` in the interpreter that runs
it — the generator's own imports. Install them into `.venv`; a distro
python3 is usually PEP-668 externally-managed.

**This reverses the earlier decision not to commit these files.** That
call was made to avoid a second place to update on every dependency bump.
The cost was worse: a manifest whose dependency sources are produced at
submission time cannot be built, reviewed, or reproduced by anyone else,
and the manifest shipped with its dep includes commented out, so a fresh
clone could not build it at all. The drift the old rationale worried about
is real, and is handled by proving currency instead of by omission —
`packaging/submit/flathub.sh` regenerates and diffs before every
submission, where an empty diff *is* the confirmation.

## Submission steps (at M9, not now)

Flathub documents the full flow at <https://docs.flathub.org/docs/for-app-authors/submission>. Perch's specifics:

1. **Re-pin the release.** Set the `perch` module's `tag:` and `commit:` to
   the newest release, and regenerate the closure if it moved.
2. **Build what Flathub will build**: `LOCAL=0
   packaging/flathub/flatpak-build.sh`. The default `LOCAL=1` swaps in your
   working tree and so proves nothing about the submission.
3. **Run Flathub's linter.** Their infrastructure runs it and a failure
   blocks the PR:
   ```sh
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
       manifest packaging/flathub/io.github.milnet01.Perch.yml
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
       appstream data/io.github.milnet01.Perch.metainfo.xml
   ```
   See §Known linter exceptions below for the three that survive by design.
4. **Do the manual checks** a headless build cannot make — the tray icon on
   a real Plasma session, the KWin script installing to
   `~/.local/share/kwin/scripts/` at first run, geometry surviving a window
   close and reopen, and the config dialog saving.
5. **Fork `flathub/flathub`, branch from `new-pr`.** A new app is PR'd
   against the `new-pr` branch, not `master` — a PR to `master` is the
   wrong queue. Name the branch after the app id, and put three files at
   the repo root: `io.github.milnet01.Perch.yml`, `python3-deps.yaml` and
   `flathub.json`. No `packaging/` directory travels with the submission,
   which is why the manifest reaches Perch's own files through its git
   clone rather than by relative path.
6. **Open the PR**, titled `Add io.github.milnet01.Perch`. Ask their bot
   for a test build by commenting `bot, build`. Budget several weeks for
   the first round.
7. **On merge**, Flathub creates `flathub/io.github.milnet01.Perch` and
   builds it. Accept the repo invitation within a week, with 2FA on the
   GitHub account — both are Flathub requirements.

## Known linter exceptions

`flatpak-builder-lint` reports three `finish-args` entries that Perch keeps
because removing them removes the app's function. Each needs a written
justification in the PR; `packaging/submit/flathub.sh` puts them in the PR
body.

| Entry | Why it stays |
|---|---|
| `--talk-name=org.kde.KWin` | Perch drives window placement through KWin's scripting interface. This is the core function on Plasma Wayland, and there is no portal equivalent. |
| `--filesystem=xdg-data/kwin/scripts:create` | KWin runs on the host and cannot read `/app`, so the bundled script is mirrored into the host's script directory at first run. |
| `--filesystem=xdg-config/perch:create` | Shares one config file with a non-Flatpak install on the same machine. This is the one of the three that is a preference rather than a requirement — dropping it would leave Flatpak Perch with its own sandboxed config, which is the Flathub norm. |

Three others were removed after the linter reported them, and should not
be reinstated: `--socket=session-bus` (blanket bus access, which makes the
named `--talk-name` grants meaningless), `--own-name=io.github.milnet01.Perch`
and `--talk-name=org.freedesktop.portal.Desktop` (both granted by default).

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
