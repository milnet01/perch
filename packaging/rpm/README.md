# Perch RPM packaging

This directory carries the unified RPM spec that openSUSE OBS and Fedora
COPR both consume. One spec, two distro targets, distinguished by the
`%if 0%{?suse_version}` / `%if 0%{?fedora}` guards inline where package
names legitimately differ.

## Files

| File | Purpose |
|---|---|
| `perch.spec` | Authoritative RPM spec. Single-source for OBS and COPR. |
| `_service` | OBS source-service descriptor — clones `main`, tars it, rewrites `Version:` from the tag. Only read by OBS; COPR ignores it. |

## openSUSE OBS flow

1. **Project**: `home:milnet01` on <https://build.opensuse.org>. Promote
   to `X11:Utilities` or `KDE:Extra` once the app is Flathub-listed and
   has user interest.
2. **Setup**:
   ```bash
   osc checkout home:milnet01 perch
   cp packaging/rpm/perch.spec home:milnet01/perch/
   cp packaging/rpm/_service    home:milnet01/perch/
   osc add perch.spec _service
   osc commit -m "Initial Perch package"
   ```
3. **Targets enabled**: openSUSE Tumbleweed (primary), Leap 16.0 once
   its PySide6 is ≥ 6.8 (Leap 15.x ships 6.4 — too old, same story as
   Ubuntu 24.04).
4. **Tag-driven rebuilds**: the `_service` file picks up new git tags
   automatically via `obs_scm`. Manual re-triggers via
   `osc service runall`.

## Fedora COPR flow

1. **Project**: `milnet01/perch` on <https://copr.fedorainfracloud.org>.
2. **Build source**: COPR's "Custom script" or "SCM" build type pointed
   at `https://github.com/milnet01/perch.git`. Script:
   ```bash
   #!/bin/sh
   VERSION=$(git describe --tags --abbrev=0 | sed 's/^v//')
   sed -i "s/^Version:.*/Version:        ${VERSION}/" packaging/rpm/perch.spec
   tar -czf /tmp/perch-${VERSION}.tar.gz --transform "s|^|perch-${VERSION}/|" .
   mkdir -p /tmp/rpmbuild/SOURCES /tmp/rpmbuild/SPECS
   cp /tmp/perch-${VERSION}.tar.gz /tmp/rpmbuild/SOURCES/
   cp packaging/rpm/perch.spec /tmp/rpmbuild/SPECS/
   rpmbuild --define "_topdir /tmp/rpmbuild" -bs /tmp/rpmbuild/SPECS/perch.spec
   cp /tmp/rpmbuild/SRPMS/*.src.rpm "$OUTPUTDIR"/
   ```
3. **Targets enabled**: Fedora latest, Fedora latest-1, EPEL 10 (for
   Rocky / Alma on CentOS Stream 10).
4. **Webhook**: wire GitHub releases to trigger a COPR rebuild via the
   tagged API; see <https://docs.pagure.org/copr.copr/user_documentation.html#webhooks>.

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
- COPR rebuild is triggered manually (or via webhook — see Fedora flow).
- `docs/10-packaging.md` moves the OBS and COPR channel rows to "live".
