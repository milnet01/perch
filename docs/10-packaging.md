# 10 — Packaging

Where Perch ships and how each channel is built.

Authoritative packaging artefacts live under `packaging/`:

| Path | Channel |
|---|---|
| `packaging/flathub/io.github.milnet01.Perch.yml` + `SUBMISSION.md` | Flathub |
| `packaging/rpm/perch.spec` + `README.md` | openSUSE OBS (openSUSE and Fedora RPMs) |
| `packaging/aur/PKGBUILD` + `.SRCINFO`, `packaging/aur/perch-git/PKGBUILD` + `.SRCINFO`, `README.md` | AUR |
| `packaging/kde-store/LISTING.md` | KDE Store |

Submission runbooks live under `packaging/submit/`:

| Channel | Runbook | Notes |
|---|---|---|
| Flathub | `packaging/submit/flathub.sh` | Needs `flatpak-builder`; stages by default, `--push` opens the PR. |
| openSUSE OBS | `packaging/submit/obs.sh` | Needs `osc` + `~/.config/osc/oscrc`. Builds the Fedora RPM too. |
| AUR | `packaging/submit/aur.sh <perch\|perch-git>` | Needs SSH key registered on AUR account. |
| KDE Store | `packaging/submit/kde-store.md` | Web-only submission — runbook, not CLI. |

`.github/workflows/ci.yml` has a `packaging` job that runs
`appstreamcli validate` on the metainfo, `desktop-file-validate` on the
desktop entry, `yamllint` on the Flatpak manifest, `rpmspec -P` on the
RPM spec, and `bash -n` on every PKGBUILD — so submission-blocking
regressions surface on every PR.

This doc was updated during Phase 2 research. Notable changes:

- Flatpak **cannot** load a KWin script from `/app/share/...` — KWin runs on the host and cannot see Flatpak's internal paths. Corrected strategy: copy the script to the host's `~/.local/share/kwin/scripts/` on first run.
- Flatpak **cannot** install a GNOME Shell extension — that backend is an explicit two-step install.
- Ubuntu 24.04 LTS ships PySide6 6.4 (too old) — documented caveat and PyPI-wheel fallback.
- D-Bus and X11 dependency lines updated to match the revised stack (`sdbus-python`, `python-xlib`).

## Application ID

Everything downstream keys off the reverse-DNS app id:

- **App ID:** `io.github.milnet01.Perch`
- **Desktop file:** `io.github.milnet01.Perch.desktop`
- **Icon name:** `io.github.milnet01.Perch`
- **Metainfo:** `io.github.milnet01.Perch.metainfo.xml`
- **D-Bus service** (Perch's own D-Bus endpoint, v1.x): `io.github.milnet01.Perch`

The GitHub namespace (`milnet01`) is chosen as the project owner's stable identity. If the project moves or gets its own domain later, a renamed app id ships as v2 with an AppStream `<provides><id>` line pointing at the old id for continuity.

## Channels

| Channel | Who uses it | Status |
|---|---|---|
| **AppImage** | Anyone — download one file, run it, no install | recipe at `packaging/appimage/`; the self-contained download attached to each GitHub release (§ AppImage below). **The available download today.** |
| **Flathub (Flatpak)** | Anyone — primary cross-distro store channel | manifest authored at `packaging/flathub/`; Flathub submission tracked as PERC-0002 in `ROADMAP.md` |
| **openSUSE OBS** | openSUSE Tumbleweed & Leap users, and Fedora / RHEL clones | spec authored at `packaging/rpm/`; OBS builds both distro families from the one spec; live at OBS project `home:milnet:perch`, building green on openSUSE_Tumbleweed and Fedora_44 |
| **AUR** | Arch / Manjaro / EndeavourOS | `perch` + `perch-git` PKGBUILDs authored at `packaging/aur/`; AUR push tracked under v1.0.1 (user-maintained is acceptable) |
| **KDE Store** | Plasma users browsing Discover / Get New Stuff | listing authored at `packaging/kde-store/LISTING.md`; entry created when Flathub goes live |
| **PyPI** | Python devs who want to `pipx install perch` | not v1 |

The store channels ship their recipes today; getting them *live* (the
submission + review round-trip) is the v1.0.1 milestone. Until then the
**AppImage** is the way an end user installs Perch without building from source.

## AppImage (self-contained download)

The AppImage is the *download → `chmod +x` → run* channel: one file, **zero
dependencies for the user to install**. It bundles the Python interpreter,
PySide6/Qt, and the system libraries the Qt `xcb` platform plugin needs, so it
runs on a bare desktop with nothing pre-installed. Recipe and full rationale:
[`packaging/appimage/`](../packaging/appimage/README.md).

```bash
./packaging/appimage/build.sh          # -> dist/Perch-<version>-x86_64.AppImage
```

**Build shape** (a Python + Qt app, so not a plain `linuxdeploy` build):

1. `pip wheel` builds the `perch` wheel.
2. [`python-appimage`](https://github.com/niess/python-appimage) assembles an
   AppDir around a **manylinux_2_28** interpreter — glibc **2.28** floor, so the
   AppImage runs on Ubuntu 20.04+, Debian 10+, Fedora, openSUSE, Arch — and
   pip-installs perch + its deps into it.
3. `harvest-libs.sh` runs in an **AlmaLinux 8** container (matching that glibc
   2.28 baseline) and bundles the libraries `python-appimage` leaves out but the
   GUI dlopens at runtime: `libxcb-cursor`, the `xcb-util` family,
   `libxkbcommon-x11`, and the vendor-neutral glvnd `EGL`/`GL` dispatchers. They
   are sourced from old glibc so they stay portable. Without this step Perch's
   window fails with *"could not load the Qt platform plugin xcb"* on a minimal
   system.
4. `appimagetool` packs the AppDir behind the AppImage runtime.

**What is deliberately *not* bundled** (host-provided): glibc, the GL/DRM driver
stack (`libGL`/`libdrm`/`libgbm` — driver-specific), and the X core libs
(`libX11`, `libxcb.so.1`) that every X server already ships. Bundling those
would break hardware acceleration or clash with the live X server.

**glibc floor.** `manylinux_2_28` (glibc 2.28) is the bundled-interpreter
baseline and the AppImage's effective floor. It is pinned in
`packaging/appimage/build.sh` (`MANYLINUX_TAG`); moving it is a portability
decision — bump it here and in that script in lockstep, and re-run the
bare-container check below.

**Verification.** The build is validated by extracting the AppImage on a **bare
`ubuntu:22.04` container** (none of the Qt/xcb libraries installed) and
confirming `QApplication` initialises with the `xcb` platform — i.e. the bundle
is genuinely self-contained, not silently borrowing the build host's libraries.

**Runtime stub.** `appimagetool` fetches the AppImage `runtime-x86_64` from
GitHub; `build.sh` accepts `PERCH_APPIMAGE_RUNTIME=/path` to use a local copy
when that download is unreachable. CI (GitHub Actions) is the intended release
build — the fetch is reliable there.

## Flatpak (primary)

### Manifest

The manifest is [`packaging/flathub/io.github.milnet01.Perch.yml`](../packaging/flathub/io.github.milnet01.Perch.yml)
and is the only copy — it is what gets submitted, so a second copy here
would be a second thing to keep true. [`packaging/flathub/SUBMISSION.md`](../packaging/flathub/SUBMISSION.md)
is the runbook. The decisions worth knowing without opening either:

- **`org.kde.Platform//6.11`**, with **`io.qt.PySide.BaseApp//6.11`**
  supplying PySide6 and Qt. The BaseApp is built against that same runtime
  and ships python 3.13, which is the ABI the pinned wheels target. Perch
  is a Plasma application, so the KDE runtime is the right base rather than
  freedesktop.
- **The remaining dependencies are sha256-pinned and committed** in
  `packaging/flathub/python3-deps.yaml`, generated from `pyproject.toml` by
  `generate-pip-sources.sh`. Flathub's builders have no network, so nothing
  may be resolved at build time — including the `hatchling` build backend,
  which is why it is in the closure too.
- **`flathub.json` restricts the buildbot to x86_64**, the arch the pinned
  `sdbus` wheel covers.
- **`finish-args` carries no `--socket=session-bus`.** Named `--talk-name`
  entries are how a sandboxed app reaches specific services; the blanket
  socket makes them meaningless and Flathub's linter rejects it. Each
  service Perch needs must therefore be named — including
  `org.kde.StatusNotifierWatcher`, without which the tray icon, and so the
  whole interface, never appears.
- **No `--device=dri`** — Perch renders no 3D surface, and the tray icon and
  dialogs work on llvmpipe.

Build it locally with [`packaging/flathub/flatpak-build.sh`](../packaging/flathub/flatpak-build.sh),
which builds offline exactly as Flathub does.

### KWin script delivery from Flatpak — the critical detail

Phase 2 research (see `11-roadmap.md` log) invalidated the original assumption that KWin could `loadScript("/app/share/perch/kwin")` directly. KWin runs on the host, the Flatpak `/app/` tree is only visible inside the sandbox, so the host path resolution fails.

**Corrected strategy**: on first run, `KWinBackend` copies the bundled script from `/app/share/perch/kwin/` to the host's `~/.local/share/kwin/scripts/org.milnet01.perch/`, made writable by the `xdg-data/kwin/scripts` filesystem permission. `loadScript()` is then called with the host-side path.

The destination is resolved from `$HOME`, **not** from `$XDG_DATA_HOME`: inside a Flatpak that variable points at `~/.var/app/io.github.milnet01.Perch/data`, which KWin cannot read, so honouring it would silently disable the whole backend.

The copy is idempotent, checksummed against the bundled source, and re-done whenever Perch's version (or the bundled script's version) changes. This keeps the user's host state aligned with the installed Flatpak automatically.

Non-Flatpak installs don't need the copy — the RPM/PKGBUILD drops the script under `/usr/share/perch/kwin/` and `KWinBackend` symlinks or passes that path directly.

### GNOME extension: two-step install (Flatpak limitation)

Flatpak **cannot** install a GNOME Shell extension. There is no portal for shell-extension installation, and the sandbox cannot write trusted files into `~/.local/share/gnome-shell/extensions/`. For Flatpak Perch on GNOME:

1. Flatpak ships Perch itself (the tray, core, Mutter backend *Python* glue).
2. The extension is delivered separately: a distro package (OBS/AUR/Debian), or via extensions.gnome.org (EGO), or by asking the user to install `com.mattjakeman.ExtensionManager` from Flathub and point it at EGO.
3. On first run, if the extension is absent, Perch's tray icon shows a warning state ("awaiting GNOME extension") and the config dialog surfaces install instructions.

This is documented prominently in the README and the config dialog; it is not considered a regression because Perch's Mutter support is a stub (see [06-backend-stubs.md](06-backend-stubs.md)).

### Other open issues for M8

- **Autostart from Flatpak**: supported via the `org.freedesktop.portal.Background` portal. Perch uses the portal when running under Flatpak and the XDG autostart `.desktop` file otherwise.
- **SELinux-enforcing hosts** (Fedora, RHEL): `~/.local/share/kwin/scripts/` is user-owned and writable from Flatpak via the granted permission; KWin reads it as the user. No known SELinux obstruction, but smoke-test on Fedora during M8.

### Metainfo

`data/io.github.milnet01.Perch.metainfo.xml` is required by Flathub. It contains:

- Summary + description.
- Screenshots (hosted in the repo's `docs/screenshots/`).
- Release history (mirrored from `CHANGELOG.md`).
- `<content_rating type="oars-1.1">` — all-zero, Perch has no content.
- Categories: `Utility`, `DesktopUtility`.

## openSUSE OBS (RPM)

### Spec sketch

```spec
Name:           perch
Version:        1.0.0
Release:        0
Summary:        Persistent, compositor-aware window geometry manager
License:        GPL-3.0-or-later
URL:            https://github.com/milnet01/perch
Source0:        https://github.com/milnet01/perch/archive/v%{version}/perch-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel >= 3.12
BuildRequires:  python3-hatchling
BuildRequires:  python3-pip
BuildRequires:  appstream-glib
BuildRequires:  desktop-file-utils

Requires:       python3 >= 3.12
Requires:       python3-PySide6 >= 6.8
Requires:       python3-qasync >= 0.28
Requires:       python3-sdbus >= 0.14.2
Requires:       python3-xlib >= 0.33
Requires:       python3-tomlkit >= 0.13

%description
Perch sits in the system tray and remembers where each window belongs …

%prep
%autosetup

%build
# hatchling

%install
pip3 install --prefix=%{buildroot}%{_prefix} --no-deps --no-build-isolation .

install -Dm644 data/io.github.milnet01.Perch.desktop    %{buildroot}%{_datadir}/applications/
install -Dm644 data/io.github.milnet01.Perch.metainfo.xml %{buildroot}%{_metainfodir}/
install -Dm644 data/icons/hicolor/scalable/apps/*.svg     %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/

install -Dm644 src/perch/backend/kwin/script/metadata.json \
    %{buildroot}%{_datadir}/perch/kwin/metadata.json
install -Dm644 src/perch/backend/kwin/script/contents/code/main.js \
    %{buildroot}%{_datadir}/perch/kwin/contents/code/main.js

%check
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/*.metainfo.xml
desktop-file-validate %{buildroot}%{_datadir}/applications/*.desktop

%files
%license LICENSE
%doc README.md
%{_bindir}/perch
%{python3_sitelib}/perch/
%{python3_sitelib}/perch-*.dist-info/
%{_datadir}/applications/io.github.milnet01.Perch.desktop
%{_metainfodir}/io.github.milnet01.Perch.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg
%{_datadir}/perch/
```

### OBS setup

- Project: `home:milnet:perch` — a subproject, matching the convention used by
  this maintainer's other OBS projects. Promote to `X11:Utilities` or
  `KDE:Extra` if accepted.
- Users install from
  <https://software.opensuse.org/download.html?project=home%3Amilnet%3Aperch&package=perch>,
  which the README links.
- Multi-distro targets: Tumbleweed (primary), Leap 16 (if PySide6 is available), and Fedora — all built by OBS from the one spec.
- `packaging/submit/obs.sh` uploads the release tarball; there is no OBS source service (see packaging/rpm/README.md for why).

## Fedora

Fedora RPMs come from OBS, built from the same spec as the openSUSE ones — OBS builds Fedora targets, so one project covers both distro families.

Fedora COPR was considered and dropped (2026-08-27): it would have been a second build service producing one artefact from one spec, with a second set of credentials and a second thing to keep current. The `%if 0%{?fedora}` guards in the spec stay, because package names differ between the families (`python3-PySide6` vs `python3-pyside6`); that is unrelated to which service builds them.

## AUR

Two packages:

- `perch` (stable, from latest tagged release tarball).
- `perch-git` (from `HEAD` of `main`).

### PKGBUILD outline

```bash
# Maintainer: milnet01 <…>
pkgname=perch
pkgver=1.0.0
pkgrel=1
pkgdesc="Persistent, compositor-aware window geometry manager"
arch=('any')
url="https://github.com/milnet01/perch"
license=('GPL-3.0-or-later')
depends=('python>=3.12' 'pyside6>=6.8' 'python-qasync>=0.28' 'python-sdbus>=0.14.2' 'python-xlib>=0.33' 'python-tomlkit>=0.13')
makedepends=('python-build' 'python-installer' 'python-hatchling')
source=("$pkgname-$pkgver.tar.gz::https://github.com/milnet01/perch/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  cd "$pkgname-$pkgver"
  python -m build --wheel --no-isolation
}

package() {
  cd "$pkgname-$pkgver"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 data/io.github.milnet01.Perch.desktop    "$pkgdir/usr/share/applications/io.github.milnet01.Perch.desktop"
  install -Dm644 data/io.github.milnet01.Perch.metainfo.xml "$pkgdir/usr/share/metainfo/io.github.milnet01.Perch.metainfo.xml"
  install -Dm644 data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg \
                 "$pkgdir/usr/share/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg"
  install -Dm644 src/perch/backend/kwin/script/metadata.json "$pkgdir/usr/share/perch/kwin/metadata.json"
  install -Dm644 src/perch/backend/kwin/script/contents/code/main.js "$pkgdir/usr/share/perch/kwin/contents/code/main.js"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
```

Community co-maintainers are welcome — the AUR entry documents that we accept co-maintainer requests via issue.

## KDE Store

KDE Store hosts Plasma addons browsable from Discover and Plasma's *Get New Stuff* dialogs. Perch fits the "Utilities" category. Upload format is a tarball + `metadata.json` + screenshots.

The KDE Store build is essentially the Flatpak artefact wrapped for the store's GHNS (Get Hot New Stuff) system, pointing at our Flatpak as the install path. It is a discoverability channel rather than an independent build.

## Shared artefacts

Every channel installs the same four shared-data files:

1. `/usr/share/applications/io.github.milnet01.Perch.desktop`
2. `/usr/share/metainfo/io.github.milnet01.Perch.metainfo.xml`
3. `/usr/share/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg`
4. `/usr/share/perch/kwin/...` (the KWin script, staged here; copied to the user's `kwin/scripts/` directory at runtime by the KWin backend on both Flatpak and non-Flatpak installs for uniformity)

`data/` in the repo is the canonical source of the first three.

## Ubuntu 24.04 LTS — dependency caveats

Ubuntu 24.04 "Noble" ships Python **3.12** (OK) but **PySide6 6.4** (too old; we need ≥ 6.8). Distro-only install on 24.04 doesn't work.

Workarounds, in preference order:

1. **Use the Flatpak** — the `org.kde.Platform` runtime plus the PySide BaseApp ship a current PySide6, and the bundle is self-contained.
2. **`pipx install perch`** — pipx resolves Perch's pins and installs `PySide6>=6.8` from PyPI into its own venv, independent of the distro package.
3. **Snap** (if we ever ship one) — bundles its own Qt.

Ubuntu 25.04/25.10 ship PySide6 6.7/6.8 and work with the distro package. Ubuntu 26.04 LTS (April 2026, releasing around the same time as this doc is written) is expected to ship PySide6 ≥ 6.8.

The `perch` DEB is built only for **Ubuntu 25.04+ / Debian 13+**. 24.04 users are pointed at Flathub or pipx.

## CI

Matrix:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04]           # runner OS; we install deps via pip not apt
    python: ["3.12", "3.13", "3.14"]
```

Notes confirmed in Phase 2.5 research:

- **Install PySide6 from PyPI**, not `apt` — Ubuntu 24.04's distro PySide6 is 6.4, too old. `pip install -e ".[dev]"` resolves Perch's pin and pulls a current wheel.
- **Use `pytest-xvfb`** (Florian Bruhin, actively maintained) rather than `xvfb-run` wrappers or third-party GH Actions. `pytest-xvfb` auto-starts an Xvfb for any test touching Qt widgets.
- System deps (`libxkbcommon-x11-0`, `libxcb-*`, `libegl1`, `x11-utils`) are installed via `apt` at the start of the workflow — PySide6's wheels expect these at runtime.
- **KWin integration tests are nightly, not per-PR** — see [05-backend-kwin.md](05-backend-kwin.md).

Lint / type / test pins (from the Phase 2.5 "ruff + mypy + pytest" research):

```
ruff>=0.15,<0.16     # pre-1.0; pin minor because style-guide rules change between minors
mypy>=1.20,<2
pytest>=8.4,<10
pytest-qt>=4.5,<5
pytest-asyncio>=1.3,<2
pytest-xvfb>=3
```

## Autostart

`src/perch/autostart.py` implements both paths behind a single
`sync(enabled)` façade, invoked on startup and from the config
dialog's `saved` signal so the `Start Perch at login` checkbox takes
effect immediately without a restart:

- **Non-Flatpak**: writes or removes
  `$XDG_CONFIG_HOME/autostart/io.github.milnet01.Perch.desktop` with
  `X-GNOME-Autostart-enabled=true`. Atomic temp-and-rename so a
  half-written file never reaches the session manager.
- **Flatpak**: calls `org.freedesktop.portal.Background.RequestBackground`
  with `autostart=true` and `commandline=["perch"]`. That method returns
  the object path of an `org.freedesktop.portal.Request`, not the result —
  the outcome arrives as that request's `Response` signal, carrying
  `(uint32 response, a{sv} results)`, and `autostart` is read from there.
  The portal shows a permission prompt on first use and silently flips the
  flag thereafter, so the wait for the response is long. A refusal, a
  timeout, or an exception from the portal is logged at WARNING and
  swallowed — a portal outage must not block a config save.

Which path we pick is driven by `/.flatpak-info` — the canonical
sandbox marker.

## Versioning

SemVer, the independent config/state schema and KWin-script versions, and the
five version-bearing files are governed by
[versioning-release-standards.md](versioning-release-standards.md) — that
standard is the single source for versioning policy. Packaging-specific note
only: the schema version is independent of the app version (see
[02-state-format.md](02-state-format.md)), so a package rebuild never implies a
schema migration.

## Release mechanics

The authoritative release sequence (content → `/bump` → tag → CI builds and
attaches the AppImage) and the versioning policy live in
[versioning-release-standards.md](versioning-release-standards.md) §Release flow
— that is the single source; it is not restated here. This section covers only
the **packaging-channel delta**: what happens to each distribution channel once
a release is tagged.

- **AppImage** — built and attached to the GitHub release automatically by
  `.github/workflows/release.yml` (`packaging/appimage/build.sh`), plus a
  `SHA256SUMS.txt`. The `sdist` + wheel are buildable for anyone who wants them
  manually; not published to PyPI.
- **Downstream channels — manual / external, and only once each is live** (the
  going-live work is PERC-0002, see [`ROADMAP.md`](../ROADMAP.md)):
  - Flathub: open/refresh the manifest PR against the Flathub repo.
  - openSUSE OBS: re-run `packaging/submit/obs.sh` to upload the new tarball.

  - AUR: `perch` PKGBUILD `pkgver` bumped and pushed manually.
  - KDE Store: updated from the Flatpak artefact.

The `/release` skill drives the full sequence; see CLAUDE.md for skill wiring.

## Signed binaries / reproducible builds

- Source tarballs from GitHub are SHA256-summed; the sums are included in the release notes.
- No GPG signing of tarballs in v1 (GitHub release signatures are the tamper-evident story).
- Flatpak ships with Flathub's standard verification; OBS signs its RPMs with the openSUSE build keys.
- Reproducible builds are not a v1 target but the Python-only + static-data shape makes them attainable. Tracked in the roadmap.
