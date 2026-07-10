# Git & commit standard

How Perch's history is kept legible: the commit-message shapes actually in use, atomic-commit discipline, branch naming, and the push gate. Grounded in the current `git log`, not an imported house style.

## Commit message format

Two subject-line shapes coexist in the history, chosen by what the commit is:

- **Milestone-id prefix** — `M<n>[.<letter>][.<n>]: <imperative summary>` for roadmap work.
  Examples: `M9.g: submission scaffolding for v1.0.0 external channels`, `M5.f: hotkeys via KGlobalAccel + pluggable provider protocol`, `M9.f.15: drop broken preplace; stops windows getting stuck on top`. A trailing `+` (`M9.g+:`) marks follow-up work past a milestone's original close.
- **Conventional `type(scope): summary`** for standalone changes outside a milestone.
  Types seen in the log: `fix`, `docs`, `build`, `chore`, `test`, `content`, and `release`. Scope is optional and names the touched area: `fix(local_CI): …`, `docs(changelog): …`, `test(conftest): …`, `fix(ci): …`, `chore(audit): …`. Scope-less forms (`build: lift mypy cap to <3`, `docs: add dependency-currency standard`) are equally valid.

`release: v<X.Y.Z>` is the fixed subject for a version bump (see [versioning-release-standards.md](versioning-release-standards.md)); it is set by `.claude/bump.json`'s `commit_message_template`.

### Subject line rules

- **Imperative mood** — "Add X", not "Added"/"Adds X".
- **Target ≤72 characters.** Keep subjects short; the occasional longer subject (e.g. a milestone commit enumerating a doc set) is tolerated but not the norm.
- These rules are the project's stated commit policy (`CONTRIBUTING.md` §Commit messages).

### Body

- Explain **why** the change exists — the constraint, the tradeoff, the thing that would otherwise be non-obvious — not a restatement of the diff (e.g. `07b11e2`, a prose "why" body).
- Wrap prose at ~72–80 columns. Bullet lists and short build-shape recipes are fine (e.g. `a4e73c7`, a numbered build-shape recipe).

### Co-Authored-By trailer

Every recent commit carries, as the last body line:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Keep this trailer on any Claude-assisted commit. It is separated from the body by a blank line.

## Atomic commits

One logical change per commit; the subject should describe it in full without an "and".
- Code + its required doc update land **together** (the no-documentation-debt hard rule — see [../CLAUDE.md](../CLAUDE.md)). This is not a violation of atomicity: the doc is part of the change.
- If `ci.yml` changes, `local_CI.sh` changes in the same commit — they must never drift.
- Bundle unrelated chore/debt/docs trivia into one sweep commit rather than scattering it.

## Branch naming

- **External contributors** (forks, per `CONTRIBUTING.md`): `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
- **Authored feature work** (per the global convention in `../CLAUDE.md`): `<author>/<id>-<topic>`, where `<id>` is the milestone key this project uses (e.g. `milnet01/M10.a-learn-mode`), not a `PROJ-1234` tracker id — Perch has no external issue tracker.
- The default branch is `main`.

## Direct-to-main vs PR

- **Land directly on `main`:** bug fixes, docs-only changes, chores/debt sweeps, and release commits. This is the routine path — most of Perch's history is direct-to-main.
- **PR (review-before-merge):** available for new-feature (`implement`-kind) work and the standing path for external-contributor forks, where a reviewer benefits from seeing intent before it merges (PRs use `.github/PULL_REQUEST_TEMPLATE.md` — its **Docs-first check** block is a merge blocker, not a formality). In practice Perch's authored history is entirely direct-to-main; the PR path is optional for the author and expected only when review adds value or a contributor opens one.

## The push gate — green `local_CI.sh` before every push

Hard rule: run `./local_CI.sh` and get `safe to push` **before every push**. It mirrors both jobs of `.github/workflows/ci.yml` on one interpreter (CI additionally runs a 3.12 / 3.13 / 3.14 matrix, so a version-specific failure can still slip past a green local run — that is the one gap the local gate cannot close). A red push wastes a CI run to report what the script catches in seconds.

## Push cadence (public repo)

`github.com/milnet01/perch` is **public**, so Linux-runner CI minutes are free. Push freely after commits and releases once `local_CI.sh` is green — there is no minute-quota reason to batch. The only push precondition is the green-gate above (and, for private repos elsewhere, the batching discipline in `../CLAUDE.md` §6 — which does **not** bind here).

## See also

- [../CONTRIBUTING.md](../CONTRIBUTING.md) — §Commit messages, design-first workflow, PR expectations.
- [../CLAUDE.md](../CLAUDE.md) — the hard rules (no-doc-debt, green-`local_CI.sh`-before-push) and the global git/push discipline they layer on.
