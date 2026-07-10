# Dependency Currency Standard

**Status:** active standard. Applies to *every* dependency Perch pulls in —
runtime libraries, dev/test tools, CI actions (`uses:`), the Python runtime,
and any container base image.

## 1. Principle

Run the **latest stable version** of every dependency. This is not only about
getting new features — it is a **security posture**. The latest release is the
one receiving security patches; a dependency left behind accumulates both
missed fixes and a larger, riskier eventual upgrade.

## 2. The only exception

Pin below the latest version **only** when a newer version **explicitly breaks
a Perch feature** and there is no reasonable workaround. When that happens,
both of the following are mandatory, in the *same change* that introduces the
pin:

1. A one-line reason next to the pin (in `pyproject.toml`, the CI workflow, the
   RPM spec, the PKGBUILD, etc.).
2. A row in the **Broken-version register** (§4) recording what broke and the
   version that broke it.

A cap with no register row and no inline reason is a defect — treat it like a
failing test, not a safe default.

## 3. Sweep cadence

- **Every release cycle**, and whenever you touch a manifest for any other
  reason, run the currency sweep:
  - Python packages: `.venv/bin/python -m pip list --outdated`
  - CI actions: check each `uses:` against its latest release
    (`gh api repos/<owner>/<action>/releases/latest`)
  - Python runtime / base images: track the current stable / LTS.
- Bump the dependency **and refresh the code that calls it in the same change**
  — a bump that leaves stale call-sites is half-done.
- `./local_CI.sh` must be green after every bump before it is committed.

## 4. Broken-version register

When a newer version breaks a feature, record it here. When a version *newer
than* the "first broken" version later ships, that is the signal to **retest**:
if the breakage is gone, lift the cap, refresh call-sites, delete the row.

| Dependency | Working cap | First broken version | What it breaks | Recorded | Retest when |
|---|---|---|---|---|---|
| `tomlkit` | `<1` | `1.0` (anticipated) | The 1.0 release reshapes the API Perch relies on for comment-preserving config round-trips (`docs/02-state-format.md` §Read / write split). | 2026-04 (Phase 2.5) | `tomlkit` 1.0 ships → retest the config round-trip contract, then lift or keep. |

*Only `tomlkit` has a confirmed, documented reason so far. Every other upper
cap in `pyproject.toml` is provisional and must be either justified with a row
here or lifted — see §5.*

## 5. Outstanding cap audit

These caps exist without a recorded breakage. Each must be retested against the
latest release and then either **lifted** or given a **register row (§4)**:

| Pin | Latest | Action |
|---|---|---|
| `PySide6>=6.8,<7` | `6.x` | `<7` guards the Qt 6→7 major bump; keep, but add a register row once Qt 7 exists and is tested. |
| `qasync>=0.28,<1` · `sdbus>=0.14.2,<1` · `ruff>=0.15,<0.16` | within cap | Confirm each cap's intent; document the reason inline or widen the range. |

Every runtime and dev dependency is currently **at its latest stable release**;
no dependency is behind latest.

**Resolved:** `mypy` was capped `<2` while `2.2.0` was available. Retested
2026-07-10 under mypy 2.2.0 with `strict = true` — clean (no issues in 141
source files, full `local_CI.sh` green) — so the cap was lifted to `<3`, which
now only guards the eventual 2→3 major bump.

## 6. Recording a new broken version

1. Reproduce the breakage, naming the failing feature or test.
2. Pin to the last working version with a one-line inline reason.
3. Add a register row (§4), including the retest trigger.
4. Note it in `CHANGELOG.md` if it changes what users can install.

---

See also: [`contributing-dev-setup.md`](contributing-dev-setup.md) for the dev
environment, and [`10-packaging.md`](10-packaging.md) for the packaged-runtime
version constraints.
