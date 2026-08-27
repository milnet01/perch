# Perch RPM packaging

This directory carries the unified RPM spec that openSUSE OBS builds for
both distro families. One spec, two distro targets, distinguished by the
`%if 0%{?suse_version}` / `%if 0%{?fedora}` guards inline where package
names legitimately differ.

## Files

| File | Purpose |
|---|---|
| `perch.spec` | Authoritative RPM spec. Single-source for the openSUSE and Fedora builds. |
| `_service` | OBS source-service descriptor — clones `main`, tars it, rewrites `Version:` from the tag. |

## openSUSE OBS flow

**One-shot submission:** `./packaging/submit/obs.sh`

That script checks out `home:<user>/perch` (creating the package if
absent), copies this directory's `perch.spec` + `_service`, stages,
and commits — OBS runs the source service + build on its nodes.

Prerequisites:
- `osc` installed (`zypper install osc` on Tumbleweed).
- `osc -A https://api.opensuse.org login` completed (once, writes
  `~/.oscrc`).

**Project**: `home:<user>` on <https://build.opensuse.org>. Promote
to `X11:Utilities` or `KDE:Extra` once the app is Flathub-listed and
has user interest.

**Targets enabled**: openSUSE Tumbleweed (primary), Leap 16.0 once
its PySide6 is ≥ 6.8 (Leap 15.x ships 6.4 — too old, same story as
Ubuntu 24.04).

**Tag-driven rebuilds**: the `_service` file picks up new git tags
automatically via `obs_scm`. Manual re-triggers via
`osc service runall`.

## Fedora

Fedora RPMs are built by OBS from this same spec — OBS builds for Fedora
targets as well as openSUSE ones, so there is no second pipeline. Fedora
COPR was considered and dropped for that reason (2026-08-27): it would
have been a second build service producing one artefact from one spec,
with two sets of credentials and two things to keep current.

The `%if 0%{?fedora}` guards in the spec stay — they exist because
package names differ between the distro families, which is unrelated to
which service does the building.

## Local smoke build

Tumbleweed or a Fedora container:

```bash
# Work around the spec's Version: 0.0.0 placeholder during local builds.
sed "s/^Version:.*/Version:        $(python3 -c 'from perch import __version__; print(__version__)')/" \
    packaging/rpm/perch.spec > /tmp/perch.spec

# Pack the working tree as if it were the tarball.
VERSION=$(python3 -c 'from perch import __version__; print(__version__)')
tar --transform "s|^|perch-${VERSION}/|" -czf /tmp/perch-${VERSION}.tar.gz \
    --exclude=.git --exclude=__pycache__ .

rpmbuild --define "_topdir /tmp/rpmbuild" \
         --define "_sourcedir /tmp" \
         -ba /tmp/perch.spec
```

The build should exit 0 with an RPM landing under `/tmp/rpmbuild/RPMS/`.
`%check` runs `appstream-util validate-relax` and `desktop-file-validate`
inline — failures abort the build.

## Why one spec, not two

The divergence between Fedora and openSUSE amounts to the PySide6 package
name (mixed-case vs. lowercase) and not much else at the M8 scope. Two
specs would duplicate 50+ lines for the sake of avoiding one `%if`
guard; CI would need to keep them in sync; users would be confused by
which one the upstream considers authoritative. One spec with guards is
the standard practice across projects packaged on both infrastructures
(KDE frameworks do this, for example).

## What happens at v1.0.0

- `perch.spec` `Version:` is bumped by `/bump`.
- CHANGELOG entry for the release.
- OBS rebuild fires automatically on tag (via `_service`).
- `docs/10-packaging.md` moves the OBS channel row to "live".
