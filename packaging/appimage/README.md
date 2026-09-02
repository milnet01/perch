# AppImage packaging

Builds a **single-file, zero-dependency** Perch AppImage: the user downloads one
file, marks it executable, and runs it — no Python, no PySide6, no system
packages to install. Everything the GUI needs is bundled inside.

```bash
./build.sh                 # -> dist/Perch-<version>-x86_64.AppImage
```

## What the user gets

```bash
chmod +x Perch-1.1.0-x86_64.AppImage
./Perch-1.1.0-x86_64.AppImage
```

Runs on any glibc ≥ 2.28 desktop (Ubuntu 20.04+, Debian 10+, Fedora, openSUSE,
Arch, …) with an X11 session or a compositor that offers Xwayland.

## How it works

Perch is a Python + Qt (PySide6) app, so the AppImage is built in four stages
(see `build.sh` for the annotated steps):

1. **Wheel** — `pip wheel` builds the `perch` wheel.
2. **AppDir** — [`python-appimage`](https://github.com/niess/python-appimage)
   assembles an AppDir around a portable **manylinux_2_28** interpreter (glibc
   2.28 floor) and pip-installs perch + its deps (PySide6, qasync, sdbus,
   python-xlib, tomlkit) into it.
3. **Harvest** — `harvest-libs.sh` runs in an **AlmaLinux 8** container and
   bundles the system libraries the Qt `xcb` platform plugin and the glib/dbus
   stack need but that `python-appimage` leaves out (`libxcb-cursor`,
   `libxkbcommon-x11`, the glvnd `EGL`/`GL` dispatchers, …). They are harvested
   from *old* glibc (EL8) so they stay portable on older targets. `entrypoint.sh`
   puts them on `LD_LIBRARY_PATH`. Without this step Perch's window fails with
   *"could not load the Qt platform plugin xcb"* on a bare desktop.
4. **Pack** — `appimagetool` compresses the AppDir behind the AppImage runtime.
5. **Verify** — the packed AppImage is extracted on a bare `ubuntu:22.04`
   container, and the `xcb` platform plugin and Qt Core/Gui/Widgets/DBus must
   resolve there, bar the host-provided sonames step 3 deliberately excludes.
   A library we forgot to bundle fails the build here rather than on a user's
   desktop. Qt's unused plugins (database, GTK, speech, Wayland compositor) are
   out of scope — their dependencies are absent by design.

What is *not* bundled (and must not be): glibc itself, the GL/DRM driver stack,
and the X core libs (`libX11`, `libxcb.so.1`) — every graphical desktop already
ships these, and bundling them would break hardware acceleration.

## Requirements

- `python3`, `podman` (or `docker`), network for pip + the base image.
- The AppImage **runtime stub** is fetched from GitHub. If your network stalls
  on the release CDN, extract a runtime from any existing AppImage and point
  `PERCH_APPIMAGE_RUNTIME` at it:
  ```bash
  PERCH_APPIMAGE_RUNTIME=/path/to/runtime-x86_64 ./build.sh
  ```
  In GitHub Actions the download just works — CI is the intended release build.

## Files

| File | Role |
|---|---|
| `build.sh` | orchestrator (wheel → AppDir → harvest → pack → verify) |
| `harvest-libs.sh` | runs in AlmaLinux 8; bundles the portable Qt/xcb system libs, and writes the host-provided soname list `build.sh` verifies against |
| `entrypoint.sh` | AppImage launcher; widens `LD_LIBRARY_PATH` to the bundled libs, and records the host's own value for `src/perch/hostenv.py` to restore when Perch spawns a host program |
| `perch.desktop` | desktop entry embedded in the AppImage |

See [`docs/10-packaging.md`](../../docs/10-packaging.md) § AppImage for the
channel's place in the wider packaging story.
