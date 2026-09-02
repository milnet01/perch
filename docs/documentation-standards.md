# Documentation standard

How Perch's documentation is written, structured, and kept in lockstep with the code. Perch is docs-first with a no-documentation-debt hard rule; this document codifies the conventions that make those rules mechanical rather than aspirational. [`../CLAUDE.md`](../CLAUDE.md) holds the binding wording of the **docs-first** and **no-documentation-debt** hard rules; this doc paraphrases those and adds the conventions and review gates (§Review gates) that make them mechanical. Where this doc and CLAUDE.md overlap and ever diverge, CLAUDE.md wins.

## Docs-first

Any behaviour change lands in the relevant `docs/` file **before or in the same PR as** the code that implements it. There is no "code now, document later." If a request implies behaviour no existing doc covers, the first deliverable is the doc change — propose it and let it be reviewed before writing implementation code. CONTRIBUTING calls this the [§Design-first workflow](../CONTRIBUTING.md#design-first-workflow) — the same rule under a different heading.

## No documentation debt

Docs and code are edited in the **same change**, never in a follow-up:

- Adding, changing, or removing user-visible behaviour updates the relevant `docs/` file in the same PR.
- Changing an internal contract (the `WindowBackend` interface, the state/config schema, identity rules) updates the corresponding numbered doc in the same PR.
- Removing a feature removes **every** mention of it from `docs/` — no ghost features left in the prose.
- Before declaring work done, grep the touched docs for future-tense tells (`planned`, `will be`, `to be added`, `not yet`, `in progress`, `coming`) and rewrite any that describe now-shipped behaviour. The `/perch-docs-check` scan looks for the same set, but grep first.

The invariant this protects: **reading `docs/` at any commit on `main` tells the reader what the code does at that commit.** Drift from it is treated as a broken build, not paperwork.

## Structure of `docs/`

Two kinds of file live under `docs/`:

- **Numbered design docs** `NN-topic.md` (`00`…`11`) — the ordered design narrative, from [`00-overview.md`](00-overview.md) through [`11-roadmap.md`](11-roadmap.md). Each owns one subsystem or concern; the [document map](00-overview.md#document-map) in `00` is the index. A new numbered doc is added only for a genuinely new subsystem, and `00`'s map is updated in the same change.
- **Non-numbered standards / how-to docs** — cross-cutting policy or process that isn't tied to one milestone, e.g. [`dependency-policy.md`](dependency-policy.md), [`contributing-dev-setup.md`](contributing-dev-setup.md), and this file. These are referenced from `00`'s "Standards" list.

Filenames are **kebab-case** (`.md`); numbered docs keep their `NN-` prefix. See [`filename-standards.md`](filename-standards.md) for the full naming rules.

## Present tense for shipped features

Perch is at v1.0.0 — Phases 0–4 are done. Describe shipped behaviour in the **present tense** ("Perch restores geometry on open"), not the future ("Perch will restore…"). Future/aspirational phrasing is reserved for genuinely unshipped work, and only in [`ROADMAP.md`](../ROADMAP.md). When a feature ships, its doc prose is flipped to present tense in the same PR that ships it.

## Tone and audience

Match the register to the document:

- **User-facing prose** (overview, UI, packaging) is plain-language: lead with what the user gets, define unavoidable jargon inline, prefer concrete file/menu names over abstract ones. `00-overview.md`'s framing is the template.
- **Design docs** (architecture, backend interface, state format, rules engine) are technical and precise: exact type shapes, method surfaces, error taxonomies, and event-ordering guarantees. The audience is a contributor implementing against the contract.

Either way, apply the **six-month test**: a reader opening the doc six months on should understand *why* the design is the way it is without the author present. Record the rationale, not just the mechanism — especially for non-obvious trade-offs (why `sdbus-python` over `dbus-next`, why capabilities under-declare rather than over-declare).

## Cross-reference integrity

- Links between docs are **relative** (`[03-backend-interface.md](03-backend-interface.md)`, `[../CLAUDE.md](../CLAUDE.md)`), never absolute paths or bare URLs to the repo.
- When linking to a heading, verify the anchor resolves against the current heading text — renamed headings silently break `#anchor` links.
- When a doc is renamed, moved, or a section removed, fix every inbound link in the same change. `/perch-docs-check` flags broken cross-references but does not repair them.

## Review gates

- **`/perch-docs-check`** — the on-demand, read-only drift scan across `docs/` (plus `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`): stale library names, retired API symbols, obsolete Python-version floors, future-tense claims on shipped features, broken cross-references. Run it after any non-trivial doc change and before every release. It reports; it does not edit.
- **`review-contract`** — every new or edited **spec / standards / design doc** (the numbered `NN-` docs, this file, other non-numbered standards docs) runs through the `review-contract` skill the moment the draft is complete. Run it *before* implementation — a wrong contract makes the implementation wrong by construction. Later loops run cold (no briefing on prior findings), and the skill caps the loop rather than running to zero findings. **Exempt:** per-feature test specs — when written, they live at `tests/features/<name>/spec.md` (the `write-test` skill's output; the directory is created on first use) — these are tiny per-feature test contracts, not multi-file design docs, and a self-read suffices.

## See also

- [filename-standards.md](filename-standards.md) — file and directory naming rules.
- [contributing-dev-setup.md](contributing-dev-setup.md) — dev environment and the pre-push `local_CI.sh` gate.
- [../CLAUDE.md](../CLAUDE.md) — the binding docs-first / no-documentation-debt hard rules.
- [00-overview.md](00-overview.md) — the `docs/` document map and standards index.
