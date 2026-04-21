# ============================================================================
# RPM spec for Perch — persistent, compositor-aware window geometry manager.
# ============================================================================
# Single spec targets both openSUSE (OBS) and Fedora (COPR); distro splits
# are handled with %%if 0%%{?suse_version} / %%if 0%%{?fedora} conditionals
# where package names legitimately differ (PySide6 case, mainly).
#
# Build invocation (local smoke):
#   rpmbuild -bb --define "_sourcedir $(pwd)" packaging/rpm/perch.spec
#
# Build invocation (OBS): driven by the _service file next to this spec.
# Build invocation (COPR): COPR reads the spec + source from the srpm we
#   upload; see packaging/rpm/COPR.md.
# ============================================================================

Name:           perch
Version:        0.0.0
Release:        0
Summary:        Persistent, compositor-aware window geometry manager
License:        GPL-3.0-or-later
URL:            https://github.com/milnet01/perch
Source0:        https://github.com/milnet01/perch/archive/v%{version}/perch-%{version}.tar.gz

BuildArch:      noarch

# Python build backend (hatchling) + pip-driven install.
BuildRequires:  python3-devel >= 3.12
BuildRequires:  python3-pip
BuildRequires:  python3-hatchling >= 1.24
BuildRequires:  python3-wheel

# %check + install-time linting.
BuildRequires:  appstream-glib
BuildRequires:  desktop-file-utils
BuildRequires:  libxml2-tools

Requires:       python3 >= 3.12
Requires:       python3-qasync >= 0.28
Requires:       python3-sdbus >= 0.14.2
Requires:       python3-xlib >= 0.33
Requires:       python3-tomlkit >= 0.13

# PySide6 package name casing differs per distro. openSUSE ships
# `python3-PySide6`; Fedora ships `python3-pyside6` (all lower). The
# `%if` guards keep this spec consumable by both OBS and COPR.
%if 0%{?suse_version}
Requires:       python3-PySide6 >= 6.8
%else
Requires:       python3-pyside6 >= 6.8
%endif

# Runtime compositor helpers. KWin scripting lives in plasma-workspace on
# openSUSE and in plasma-desktop/kwin on Fedora; we don't Requires: it —
# Perch degrades gracefully to X11 if KWin isn't the session compositor.
Recommends:     xdg-desktop-portal

%description
Perch is a persistent, compositor-aware window geometry manager for Linux
desktops. It lives in the system tray, remembers where each window
belongs, and restores position, size, monitor, and virtual desktop when a
window reopens. Perch also offers snap presets, named layouts, a rules
engine, and per-monitor profiles that reconcile on hotplug.

Native backends ship for X11 (any EWMH-compliant WM) and KWin / Plasma
Wayland. Community-maintained stub backends cover Mutter, Sway, and
Hyprland.

%prep
%autosetup -n %{name}-%{version}

%build
# hatchling wheel build; %pyproject_wheel exists on both Fedora and
# openSUSE Tumbleweed via python-rpm-macros.
%pyproject_wheel

%install
%pyproject_install

# Shared-data payload shipped from data/ (icons, desktop entry, metainfo).
# These already live under share/ in the wheel's shared-data tree thanks
# to pyproject.toml's [tool.hatch.build.targets.wheel.shared-data] map —
# but pyproject_install doesn't always relocate them on every distro, so
# we install them explicitly to the canonical FHS locations.
install -Dm644 data/io.github.milnet01.Perch.desktop \
    %{buildroot}%{_datadir}/applications/io.github.milnet01.Perch.desktop
install -Dm644 data/io.github.milnet01.Perch.metainfo.xml \
    %{buildroot}%{_metainfodir}/io.github.milnet01.Perch.metainfo.xml
install -Dm644 data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg
install -Dm644 data/icons/hicolor/symbolic/status/perch-tray-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/status/perch-tray-symbolic.svg
install -Dm644 data/icons/hicolor/symbolic/status/perch-tray-warning-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/status/perch-tray-warning-symbolic.svg
install -Dm644 data/icons/hicolor/symbolic/status/perch-tray-error-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/status/perch-tray-error-symbolic.svg

# KWin script — staged under /usr/share/perch/kwin/; the KWin backend
# mirrors it to $XDG_DATA_HOME/kwin/scripts/ at first run (KWin on the
# host can't load scripts from /app/ paths on Flatpak; to keep one code
# path everywhere we do the copy unconditionally).
install -Dm644 src/perch/backend/kwin/script/metadata.json \
    %{buildroot}%{_datadir}/perch/kwin/metadata.json
install -Dm644 src/perch/backend/kwin/script/contents/code/main.js \
    %{buildroot}%{_datadir}/perch/kwin/contents/code/main.js

# Translations — compiled .qm files. Contributors run scripts/i18n-update.sh
# to keep the .ts sources in sync; the build compiles them here.
if [ -f translations/perch_en.ts ]; then
    for ts in translations/*.ts; do
        qm="%{buildroot}%{_datadir}/perch/translations/$(basename "${ts%.ts}").qm"
        install -d "$(dirname "$qm")"
        lrelease-qt6 "$ts" -qm "$qm" 2>/dev/null || \
            pyside6-lrelease "$ts" -qm "$qm" 2>/dev/null || true
    done
fi

%check
appstream-util validate-relax --nonet \
    %{buildroot}%{_metainfodir}/io.github.milnet01.Perch.metainfo.xml
desktop-file-validate \
    %{buildroot}%{_datadir}/applications/io.github.milnet01.Perch.desktop
# KWin script metadata.json is not AppStream; a schema-free well-formedness
# check is all we can do portably.
python3 -c 'import json, sys; json.load(open("%{buildroot}%{_datadir}/perch/kwin/metadata.json"))'

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/perch
%{python3_sitelib}/perch/
%{python3_sitelib}/perch-*.dist-info/
%{_datadir}/applications/io.github.milnet01.Perch.desktop
%{_metainfodir}/io.github.milnet01.Perch.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg
%{_datadir}/icons/hicolor/symbolic/status/perch-tray-symbolic.svg
%{_datadir}/icons/hicolor/symbolic/status/perch-tray-warning-symbolic.svg
%{_datadir}/icons/hicolor/symbolic/status/perch-tray-error-symbolic.svg
%dir %{_datadir}/perch
%dir %{_datadir}/perch/kwin
%dir %{_datadir}/perch/kwin/contents
%dir %{_datadir}/perch/kwin/contents/code
%{_datadir}/perch/kwin/metadata.json
%{_datadir}/perch/kwin/contents/code/main.js
%{_datadir}/perch/translations/

%changelog
# The RPM %changelog is deliberately empty. Perch's upstream changelog is
# CHANGELOG.md; OBS/COPR auto-generate %changelog entries from git tags
# via osc / tito conventions respectively. Keeping a hand-maintained
# second changelog here is a documented anti-pattern.
