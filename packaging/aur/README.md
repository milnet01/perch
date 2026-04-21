# Perch AUR packaging

Two AUR packages, both mirrored from this directory:

| AUR name | Source | What it builds |
|---|---|---|
| [`perch`](https://aur.archlinux.org/packages/perch) | This directory's `PKGBUILD` | Latest tagged release tarball from GitHub. |
| [`perch-git`](https://aur.archlinux.org/packages/perch-git) | `perch-git/PKGBUILD` | `HEAD` of `main`. For testers and trackers. |

The AUR entries conflict with each other via `provides=('perch')` /
`conflicts=('perch')` on the `-git` side, so users install one or the
other — not both.

## Maintenance flow

1. Keep this directory in sync with release reality. When we tag
   `v1.2.3`, `/bump` rewrites `pkgver=` and `sha256sums=` in the stable
   PKGBUILD. The `-git` PKGBUILD doesn't need editing — its `pkgver()`
   function derives from `git describe` on each build.
2. Generate `.SRCINFO` next to each PKGBUILD **before** pushing to AUR:
   ```bash
   cd packaging/aur
   makepkg --printsrcinfo > .SRCINFO
   cd perch-git
   makepkg --printsrcinfo > .SRCINFO
   ```
   `.SRCINFO` is tracked in git alongside the PKGBUILD (AUR requires it).
3. Push to AUR via each package's git remote:
   ```bash
   # One-time setup (per machine):
   # git remote add aur-stable ssh://aur@aur.archlinux.org/perch.git
   # git remote add aur-git    ssh://aur@aur.archlinux.org/perch-git.git
   git subtree push --prefix=packaging/aur          aur-stable master
   git subtree push --prefix=packaging/aur/perch-git aur-git   master
   ```
4. Co-maintainer requests land via a GitHub issue. See
   `CONTRIBUTING.md` §Package maintenance.

## Local smoke build (Arch / Manjaro / EndeavourOS)

```bash
cd packaging/aur
makepkg -sf           # build + install missing deps; --force overwrites old dist/
makepkg --printsrcinfo > .SRCINFO
sudo pacman -U perch-*.pkg.tar.zst
perch --version
```

The `check()` step runs `appstream-util validate-relax` and
`desktop-file-validate` during `makepkg`, so a spec / metadata
regression aborts the build before installation.

## Why not use Arch's `python-build`/`installer` macros?

We do — the PKGBUILD uses `python -m build --wheel` + `python -m installer`.
That's the canonical modern Arch Python packaging flow (per the Arch
packaging guidelines, 2024 rewrite).  Older `setup.py install` patterns
are deprecated and `makepkg` on current Arch warns on them.

## Known gotchas

- **`sha256sums=('SKIP')` in the pre-v1.0.0 scaffold** — correct for an
  unreleased project. `/bump` rewrites this to the tarball's real
  SHA-256 when we ship `v1.0.0`. Leaving SKIP after the first tagged
  release would fail `namcap` / `aurpublish` lint.
- **PySide6 version float**: Arch rolls PySide6 current; `pyside6>=6.8`
  is mostly a no-op but guards against a hypothetical downgrade.
- **`python-i3ipc` is an optdepends**, not a depends — Perch on Arch
  might be used on KDE / X11, so forcing the Sway optional transport
  onto every install is wrong.
