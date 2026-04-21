# Contributing to Perch

Thanks for your interest in improving Perch.

## Design-first workflow

Perch is developed in a strict **documentation-first** flow:

1. The design lives in [`docs/`](docs/) — architecture, backend specs, state format, rules engine, UI, packaging, roadmap.
2. Any behavior change, however small, starts with a change to the relevant doc **before or in the same PR as** the code.
3. Pull requests that modify behavior without a corresponding doc update will be asked to add one.

This keeps the docs in sync with reality and lets reviewers focus on intent before implementation.

## No documentation debt — ever

Perch treats stale documentation as a **bug**, not paperwork. The invariant is:

> At every commit on `main`, the state of `docs/` is an accurate description of what the code does, and vice versa.

What that means in practice:

- A PR that adds, removes, or changes user-visible behaviour **must** update the relevant `docs/` file in the same PR. "I'll write up the docs later" is not accepted.
- A PR that changes an internal contract (the `WindowBackend` interface, the config schema, the identity rules) **must** update the corresponding doc in the same PR.
- A PR that removes a feature **must** also remove every mention of it from `docs/` — no ghost features left in the prose.
- Language in `docs/` that says *"Perch will…"* / *"planned for v1"* for something that has now shipped **must** be rewritten in present tense in the same PR that ships it. Grep for `planned`, `will`, `to be`, `not yet` before merging.
- When research or experience contradicts a doc, **update the doc immediately** (even if the only code change is a constant). We do not let a stale doc live next to fresh code.

Reviewers: treat a "docs-first check" failure in the PR template as a blocker. If you approve a PR with doc drift, that drift is on you.

Rationale: Perch is a long-running design-led project with contributors coming and going. The docs are the only artefact new contributors can rely on. Once you lose trust in them, you lose the contributor pipeline.

## Getting started

1. Pick an issue labeled `good-first-issue` or `help-wanted`, or open one describing what you want to change.
2. Read the relevant file(s) in `docs/`. If the change you want isn't covered, open a doc-only PR first so the design can be discussed.
3. Fork, branch (`feat/short-name`, `fix/short-name`, `docs/short-name`), and implement.
4. Run the linter and tests: `ruff check src tests && mypy --strict src && pytest`.
5. Open a PR using the template.

## Contributing a backend

Perch's compositor support is pluggable. Adding a new backend (or taking over ongoing maintenance of an existing stub) follows a fixed workflow.

### 1. Read the interface first

The `WindowBackend` contract is the source of truth:

- [`docs/03-backend-interface.md`](docs/03-backend-interface.md) — data shapes, async method surface, error taxonomy, event-ordering guarantees.
- [`docs/06-backend-stubs.md`](docs/06-backend-stubs.md) — per-compositor capability targets and known constraints for Mutter / Sway / Hyprland.

If the backend you're planning to add doesn't fit the interface, **open a docs-only PR first** that discusses the interface gap. Don't paper over it with backend-private state or reach-around calls into the core.

### 2. Scaffold the package

A backend lives under `src/perch/backend/<name>/`:

```
src/perch/backend/<name>/
├── __init__.py        # lazy re-export of the backend class
├── backend.py         # implements WindowBackend
└── STATUS.md          # honest status: what works, what doesn't, tested versions
```

Follow the pattern in `src/perch/backend/kwin/` (fully featured) or `src/perch/backend/sway/` / `src/perch/backend/hyprland/` (stubs) for the import-lazy `__init__.py` so `import perch.backend` doesn't drag in compositor-specific runtime deps.

### 3. Declare capabilities honestly

The `Capabilities` dataclass is how the core decides which UI controls to enable. Over-declaring is a **bug**: the UI will offer an action that the backend can't perform, and the user sees the failure instead of a greyed-out control.

Under-declaring is fine. Start with only the capabilities you've actually verified, and widen as you add coverage. Use the `notes` field to quote any caveats the core should surface in tooltips.

### 4. Implement `is_available()`

The compliance suite filters backends by `cls.is_available()` at test-collection time, and `perch.backend.select()` uses the same probe to pick the backend at start-up. The probe is **cheap** — env-vars and binaries only, no D-Bus round-trips, no socket connections. Match the environment signal your backend actually needs (e.g. `$SWAYSOCK` for Sway, `$HYPRLAND_INSTANCE_SIGNATURE` + `hyprctl` for Hyprland).

### 5. Pass the compliance suite

Every backend — stub or full — must pass:

```
pytest tests/backend/test_compliance.py
```

The suite parameterises over [`tests/backend/conftest.py::BACKEND_CLASSES`](tests/backend/conftest.py). Register your backend in `_all_backends()`; the suite picks it up automatically and skips any test whose required capability your backend declares off.

If a test fails because the *contract* is wrong for your compositor, that's a docs discussion (see §1). If it fails because your backend is wrong, fix the backend.

### 6. Write a `STATUS.md`

Stubs aren't allowed to be silently incomplete. `STATUS.md` documents:

- Capabilities — one table, matching the dataclass you return from `capabilities`. Include one-line evidence for each true entry and a reason for each false entry.
- Tested compositor versions — at a minimum the version the author ran against locally; widen as contributors report.
- Known skews — anything the protocol does differently across minor releases, anything your defensive parsing currently tolerates.
- What doesn't work — be concrete; "hotkeys blocked on schema" beats "hotkeys TODO".

The rest of the team reads `STATUS.md` to decide whether to route a bug at the backend or at the core.

### 7. Version-skew policy

GNOME Shell extensions must maintain per-GNOME-major-version source branches (the de-facto upstream convention — Dash to Dock, Pop Shell, Just Perfection all do it). Hyprland's `.socket2.sock` event format has broken across minor releases; Sway's i3-IPC is stable but growing.

The invariant: if a new compositor release breaks your backend, that breakage is visible in CI (the stub's live-integration tests fail) or in `STATUS.md`'s known-skew list — **never** in a user's system log.

### 8. Interact with the wider repo

- Docs-first rule still applies. Any capability change or known-skew finding lands in `docs/06-backend-stubs.md` and your `STATUS.md` in the same PR.
- No `# TODO:` markers in shipped backend code. If a feature is deferred, `STATUS.md` is the place.
- No `# WORKAROUND:` without citing the underlying compositor bug / doc.

If any of this is unclear, open an issue — the backend contract is the one contract we explicitly budget time to evolve for contributors.

## Commit messages

Keep the subject line under 72 characters and written in the imperative mood (*"Add X"*, not *"Added X"* / *"Adds X"*). The body should explain **why** the change exists, not restate the diff.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to uphold it.

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0-or-later, matching the rest of the project.
