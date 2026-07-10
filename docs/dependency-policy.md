# Dependency Currency Standard

**Status:** active standard (a.k.a. the *dependency policy* —
`dependency-policy.md`). Applies to *every* dependency Perch pulls in — runtime
libraries, dev/test tools, CI actions (`uses:`), the Python runtime, and any
container base image.

## 1. Principle

Run the **latest stable version** of every dependency. This is not only about
getting new features — it is a **security posture**. The latest release is the
one receiving security patches; a dependency left behind accumulates both
missed fixes and a larger, riskier eventual upgrade.

## 2. When a cap below latest is allowed

Only two cases justify pinning below the latest version. Anything else is a
defect — treat an unexplained cap like a failing test, not a safe default.

**(a) Confirmed breakage.** A shipped newer version breaks a Perch feature and
there is no reasonable workaround. Mandatory, in the *same change* that
introduces the cap:

1. A one-line reason next to the pin (in `pyproject.toml`, the CI workflow, the
   RPM spec, the PKGBUILD, etc.).
2. A row in the **Broken-version register** (§4) recording what broke and the
   version that broke it.

**(b) Precautionary major-version ceiling.** An upper bound that holds a
dependency below a future major it has not vetted — usually the next one (e.g.
`PySide6>=6.8,<7` keeps Perch on Qt 6 until Qt 7 is vetted), occasionally wider
(`pytest>=8.4,<10` allows 8.x–9.x but blocks 10). This serves currency rather
than fighting it — it is a **tested gate, not a permanent pin**:

1. A row in the ceiling table (§5) recording the version it guards and the
   retest trigger — that row is the authoritative reason. A terse inline
   comment next to the pin (e.g. `# guards Qt 7`) is welcome but optional.
2. When the guarded major actually ships, it must be **tested promptly** (a
   sweep, §3) and the ceiling **lifted if clean** — or, if it breaks, converted
   to a case (a) cap with a register row. A ceiling left un-retested across a
   release cycle *after* the guarded major is available is itself a currency
   violation.

A ceiling does **not** need a register row while the guarded major does not yet
exist — there is nothing broken to record. Ceilings are tracked in §5.

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

Confirmed breakages only (case (a), §2) — a version that shipped and broke a
feature. When a version *newer than* the "first broken" one later ships, that
is the signal to **retest**: if the breakage is gone, lift the cap, refresh
call-sites, delete the row.

| Dependency | Working cap | First broken version | What it breaks | Recorded | Retest when |
|---|---|---|---|---|---|
| _(none)_ | — | — | No dependency currently carries a confirmed-breakage cap. | — | — |

Precautionary major-version ceilings (case (b)) are **not** recorded here — the
major they guard has not shipped, so nothing is broken yet. They live in §5.

## 5. Precautionary major-version ceilings

These are case-(b) ceilings (§2): each holds Perch below a dependency's next
untested major — or minor, for tools like `ruff` whose minor bumps carry
breaking changes — until that release ships and is vetted. Each must be retested
and then lifted (or converted to a §4 row) when its guarded version becomes
available. Together with the §4 register, this table accounts for **every** cap
in `pyproject.toml`; a pyproject cap in neither is a defect (§2). Pins in other
manifests (CI actions, the RPM spec, PKGBUILDs, base images) are governed by the
§3 sweep and inline reasons, not tracked in this table.

| Cap | Where | Guards against | Retest trigger |
|---|---|---|---|
| `PySide6>=6.8,<7` | runtime | Qt 6 → 7 major | PySide6 7.0 ships |
| `qasync>=0.28,<1` | runtime | qasync 1.0 major | qasync 1.0 ships |
| `sdbus>=0.14.2,<1` | runtime | sdbus 1.0 major | sdbus 1.0 ships |
| `tomlkit>=0.13,<1` | runtime | tomlkit 1.0, expected to reshape the comment-preserving round-trip API (`docs/02-state-format.md` §Read / write split) | tomlkit 1.0 ships → retest the config round-trip contract |
| `i3ipc>=2.2.1,<3` | `sway` extra | i3ipc 3.0 major | i3ipc 3.0 ships → retest the Sway backend |
| `ruff>=0.15,<0.16` | dev | ruff's pre-1.0 minor-as-major cadence (0.16 can carry breaking lint/format changes) | ruff 0.16 ships → retest lint + format |
| `mypy>=1.20,<3` | dev | mypy 2 → 3 major (2.x vetted 2026-07-10, see below) | mypy 3.0 ships → retest `--strict` |
| `pytest>=8.4,<10` | dev | pytest 10 (8.x–9.x allowed) | pytest 10 ships → retest the suite |
| `pytest-qt>=4.5,<5` | dev | pytest-qt 5 major | pytest-qt 5.0 ships |
| `pytest-asyncio>=1.3,<2` | dev | pytest-asyncio 2 major | pytest-asyncio 2.0 ships |

`python-xlib` and `pytest-xvfb` carry a lower bound only — no ceiling, nothing
to track here.

As of 2026-07 — verified by a **manual** sweep (§3; there is no automated CI
currency job) — every runtime, dev, and `sway`-extra dependency sits at its
latest stable release within these ceilings; none is behind latest.

**mypy history** (context for the `<3` row above): `mypy` was capped `<2` while
`2.2.0` was available — a behind-latest state. Retested 2026-07-10 under mypy
2.2.0 with `strict = true`, clean across the full tree with `local_CI.sh` green,
so the cap was lifted to the `<3` ceiling.

## 6. Recording a new broken version

1. Reproduce the breakage, naming the failing feature or test.
2. Pin to the last working version with a one-line inline reason.
3. Add a register row (§4), including the retest trigger.
4. Note it in `CHANGELOG.md` if it changes what users can install.

---

See also: [`contributing-dev-setup.md`](contributing-dev-setup.md) for the dev
environment, and [`10-packaging.md`](10-packaging.md) for the packaged-runtime
version constraints.
