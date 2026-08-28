---
name: perch-docs-check
description: Run a drift scan across docs/ for common documentation-debt indicators — stale library names, retired API symbols, obsolete Python version floors, future-tense claims about shipped features, broken doc cross-references. Use on demand or before any release. Non-destructive; read-only.
---

# /perch-docs-check

Scan Perch's docs for documentation debt. Report findings tersely, separating **actionable drift** (fix it) from **expected historical references** (ignore).

## Scope

Run only against the Perch project directory. Do not search outside `docs/`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`.

## Checks

Run these in order; use Grep (not Bash) for all pattern matching. Report each check's findings compactly.

### 1. Retired API symbols (Plasma 5 scripting)

These were renamed in the Plasma 5 → 6 transition and should only appear in the Phase 2 research log (`docs/11-roadmap.md`) as historical context.

```
clientAdded, clientList, clientRemoved, clientActivated
```

Any occurrence in files *other than* `docs/11-roadmap.md` and `docs/05-backend-kwin.md` (Plasma 5 comparison section) is drift.

### 2. Swapped libraries

Phase 2 research swapped `dbus-next` → `sdbus-python` and `python-ewmh` → `python-xlib`. The old names should only appear in:
- `docs/11-roadmap.md` (Phase 2 research log)
- `docs/01-architecture.md` (comparison paragraph)
- `pyproject.toml` comment block

```
dbus-next, python-ewmh, asyncqt, tomli_w
```

Any active usage in other docs is drift.

### 3. Python version floor

Perch floors Python 3.12 (Phase 2.5 research). `>=3.11` or `>= 3.11` in version-bearing fields is drift. Mentions of "Python 3.11" in prose contexts (e.g. "stdlib `tomllib`, available since 3.11") are fine.

Pattern:

```
requires-python.*3\.11
python_requires.*3\.11
>= *3\.11
```

### 4. Shipped-but-tense-wrong claims

After each milestone ships, future-tense claims about that milestone become stale. Grep for the usual suspects:

```
\bplanned\b, \bwill be\b, \bto be added\b, \bnot yet\b, \bin progress\b, \bcoming\b
```

Cross-reference with the roadmap's current milestone state. Anything in "done" milestones that still uses future tense is drift.

### 5. Broken doc cross-references

For every `[text](file.md)` or `[text](../file.md)` link in `docs/*.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`:

- Verify the linked file exists (relative to the linking file's directory).
- Verify any anchor like `#section-name` plausibly exists (grep the target file for the heading).

### 6. Orphan docs

Every file in `docs/` should be referenced from at least one other doc (or from README/CLAUDE.md). An unreferenced doc is either abandoned or the map in `docs/00-overview.md` needs an update.

### 7. Version-bearing file consistency

If multiple files carry the project version (`pyproject.toml` `version = "X.Y.Z"`, `CHANGELOG.md`'s latest section, `data/*.metainfo.xml`'s latest `<release>`, RPM spec `Version:`, PKGBUILD `pkgver=`), they must all match. (These files don't all exist yet; skip any that are absent.)

## Reporting

Structure the report as:

```
Actionable drift (fix before moving on):
- <file:line> <one-line description of the drift>
...

Expected historical references (no action):
- <file:line> <why this is fine>
...

Clean: <list of checks that found nothing>
```

If there are **no** actionable findings, say so in one sentence: *"docs/ is clean — no actionable drift."* Do not pad.

## When to invoke

- After any non-trivial doc change, before declaring the turn done.
- Before running `cut-release`.
- At the start of a new Perch session, as a sanity check that nothing drifted since last commit.

Do NOT invoke from inside another skill/hook — this is for interactive use.
