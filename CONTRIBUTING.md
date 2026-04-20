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
4. Run the linter and tests (commands will be added in milestone M1).
5. Open a PR using the template.

## Backend contributions

Perch's compositor support is pluggable. Adding a new backend (Mutter, Sway, Hyprland, …) means implementing the `WindowBackend` interface defined in [`docs/03-backend-interface.md`](docs/03-backend-interface.md). No core changes should be required — if they are, that's a backend-interface bug and we should discuss fixing the interface instead.

## Commit messages

Keep the subject line under 72 characters and written in the imperative mood (*"Add X"*, not *"Added X"* / *"Adds X"*). The body should explain **why** the change exists, not restate the diff.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating you agree to uphold it.

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0-or-later, matching the rest of the project.
