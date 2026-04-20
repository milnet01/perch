# 10 — Packaging

Where Perch ships and how each channel is built.

This doc was updated during Phase 2 research. Notable changes:

- Flatpak **cannot** load a KWin script from `/app/share/...` — KWin runs on the host and cannot see Flatpak's internal paths. Corrected strategy: copy the script to `$XDG_DATA_HOME/kwin/scripts/` on first run.
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

| Channel | Who uses it | Status at v1 |
|---|---|---|
| **Flathub (Flatpak)** | Anyone — primary cross-distro channel | target |
| **openSUSE OBS** | openSUSE Tumbleweed & Leap users | target |
| **Fedora COPR** | Fedora / RHEL clones | target |
| **AUR** | Arch / Manjaro / EndeavourOS | target (user-maintained is acceptable) |
| **KDE Store** | Plasma users browsing Discover / Get New Stuff | target |
| **PyPI** | Python devs who want to `pipx install perch` | not v1 |

## Flatpak (primary)

### Manifest outline

```yaml
# io.github.milnet01.Perch.yml
app-id: io.github.milnet01.Perch
runtime: org.kde.Platform
runtime-version: "6.8"
sdk: org.kde.Sdk
base: com.riverbankcomputing.PyQt.BaseApp
base-version: "6.8"
command: perch

finish-args:
  - --share=ipc
  - --socket=x11                       # X11 fallback; required for XWayland
  - --socket=wayland
  - --socket=fallback-x11
  - --socket=session-bus               # D-Bus: KWin, GlobalShortcuts portal, notifications
  - --device=dri                        # may be needed for Qt; audit at M8
  - --talk-name=org.kde.KWin
  - --talk-name=org.kde.kglobalaccel    # non-Flatpak Plasma fallback path only (see 05)
  - --talk-name=org.freedesktop.Notifications
  - --talk-name=org.freedesktop.portal.Desktop   # for GlobalShortcuts portal
  - --own-name=io.github.milnet01.Perch          # Perch's own D-Bus service (incl. KWin1 iface)
  - --filesystem=xdg-config/perch:create         # so users can symlink their config
  - --filesystem=xdg-data/kwin/scripts:create    # so we can install the KWin script host-side
  - --metadata=X-DConf=migrate-path=/io/github/milnet01/Perch/

modules:
  - name: perch
    buildsystem: simple
    build-commands:
      - pip3 install --prefix=/app .
      - install -Dm644 data/io.github.milnet01.Perch.desktop    /app/share/applications/
      - install -Dm644 data/io.github.milnet01.Perch.metainfo.xml /app/share/metainfo/
      - install -Dm644 data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg /app/share/icons/hicolor/scalable/apps/
      # The KWin script is shipped here, but is copied to ~/.local/share/kwin/scripts/
      # at first run by KWinBackend (see docs/05-backend-kwin.md) — KWin runs on the host
      # and cannot read /app/share/.
      - install -Dm644 perch/backends/kwin/script/metadata.json  /app/share/perch/kwin/metadata.json
      - install -Dm644 perch/backends/kwin/script/contents/code/main.js /app/share/perch/kwin/contents/code/main.js
    sources:
      - type: dir
        path: .
```

### KWin script delivery from Flatpak — the critical detail

Phase 2 research (see `11-roadmap.md` log) invalidated the original assumption that KWin could `loadScript("/app/share/perch/kwin")` directly. KWin runs on the host, the Flatpak `/app/` tree is only visible inside the sandbox, so the host path resolution fails.

**Corrected strategy**: on first run, `KWinBackend` copies the bundled script from `/app/share/perch/kwin/` to `$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/`. Both paths are host-visible via the Flatpak `xdg-data/kwin/scripts` filesystem permission. `loadScript()` is then called with the host-side path.

The copy is idempotent, checksummed against the bundled source, and re-done whenever Perch's version (or the bundled script's version) changes. This keeps the user's host state aligned with the installed Flatpak automatically.

Non-Flatpak installs don't need the copy — the RPM/PKGBUILD drops the script under `/usr/share/perch/kwin/` and `KWinBackend` symlinks or passes that path directly.

### GNOME extension: two-step install (Flatpak limitation)

Flatpak **cannot** install a GNOME Shell extension. There is no portal for shell-extension installation, and the sandbox cannot write trusted files into `~/.local/share/gnome-shell/extensions/`. For Flatpak Perch on GNOME:

1. Flatpak ships Perch itself (the tray, core, Mutter backend *Python* glue).
2. The extension is delivered separately: a distro package (COPR/OBS/AUR/Debian), or via extensions.gnome.org (EGO), or by asking the user to install `com.mattjakeman.ExtensionManager` from Flathub and point it at EGO.
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

install -Dm644 perch/backends/kwin/script/metadata.json \
    %{buildroot}%{_datadir}/perch/kwin/metadata.json
install -Dm644 perch/backends/kwin/script/contents/code/main.js \
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

- Project: `home:milnet01` initially → promote to `X11:Utilities` or `KDE:Extra` if accepted.
- Multi-distro targets: Tumbleweed (primary), Leap 16 (if PySide6 is available), Fedora via COPR (not OBS).
- Uses `_service` file to auto-pull new tags.

## Fedora COPR

Same RPM spec, hosted at `copr.fedorainfracloud.org/coprs/milnet01/perch`. COPR builds on Fedora's infra and distributes via `dnf`. Targets: Fedora current + previous, CentOS Stream 10.

The COPR spec is identical to the OBS one modulo package name differences (`python3-PySide6` vs `python3-pyside6` etc.); a small substitution header in the spec handles this.

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
  install -Dm644 perch/backends/kwin/script/metadata.json "$pkgdir/usr/share/perch/kwin/metadata.json"
  install -Dm644 perch/backends/kwin/script/contents/code/main.js "$pkgdir/usr/share/perch/kwin/contents/code/main.js"
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
4. `/usr/share/perch/kwin/...` (the KWin script, staged here; copied to `$XDG_DATA_HOME/kwin/scripts/` at runtime by the KWin backend on both Flatpak and non-Flatpak installs for uniformity)

`data/` in the repo is the canonical source of the first three.

## Ubuntu 24.04 LTS — dependency caveats

Ubuntu 24.04 "Noble" ships Python **3.12** (OK) but **PySide6 6.4** (too old; we need ≥ 6.8). Distro-only install on 24.04 doesn't work.

Workarounds, in preference order:

1. **Use the Flatpak** — the `org.kde.Platform` 6.8 runtime ships a current PySide6 and is self-contained.
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

Two paths:

- **Non-Flatpak**: `/usr/share/autostart/io.github.milnet01.Perch.desktop` with `X-GNOME-Autostart-enabled=false`. The "Start at login" checkbox in Perch's dialog copies (or removes) a user-local version at `~/.config/autostart/`.
- **Flatpak**: uses `org.freedesktop.portal.Background` to request autostart. The checkbox toggles that portal call.

## Versioning

- **SemVer** — `MAJOR.MINOR.PATCH`.
- Schema version of config / state is independent (see [02-state-format.md](02-state-format.md)).
- KWin script version is independent (bundled, pinned by the Python backend).

## Release mechanics

1. Update `CHANGELOG.md` and `metainfo.xml` `<release>` entry.
2. Bump `pyproject.toml` `version`, `metadata.desktop` `Version=`, the KWin script's version field, and the KWin backend's expected-script-version constant in sync.
3. Tag: `v1.2.3`.
4. CI builds:
   - PyPI source + wheel artefact (kept for users who want it manually; not published to PyPI in v1).
   - Flatpak manifest PR to Flathub repo.
   - OBS `_service` picks up the tag.
   - COPR build triggered manually.
   - AUR updated manually (or via a `aurpublish` script in `contrib/`).
5. KDE Store: updated from the Flatpak artefact.

This is the checklist the `/release` skill will drive; see CLAUDE.md for skill wiring.

## Signed binaries / reproducible builds

- Source tarballs from GitHub are SHA256-summed; the sums are included in the release notes.
- No GPG signing of tarballs in v1 (GitHub release signatures are the tamper-evident story).
- Flatpak ships with Flathub's standard verification; OBS signs its RPMs with the openSUSE build keys.
- Reproducible builds are not a v1 target but the Python-only + static-data shape makes them attainable. Tracked in the roadmap.
