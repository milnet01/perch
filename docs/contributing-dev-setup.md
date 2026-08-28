# Contributing — dev setup

How to get a working Perch dev environment and run the checks CI runs.

## Requirements

- **Python `>=3.12`** (see [`docs/01-architecture.md`](01-architecture.md) §Dependencies). 3.12, 3.13, and 3.14 are all supported; CI runs the full matrix.
- A Linux session. Perch is Linux-only by design.
- `git`, a POSIX shell.
- System packages for a Qt runtime. On openSUSE Tumbleweed:
  ```sh
  sudo zypper install libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
      libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
      libxcb-xinerama0 libxcb-xkb1 libEGL libGL libdbus-1-3
  ```
  Equivalent lists for Fedora / Debian live in `.github/workflows/ci.yml`.
- `xvfb` if you want to run the full test suite without a real X server.

## Clone + editable install

```sh
git clone https://github.com/milnet01/perch.git
cd perch
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable install gives you `perch` as a console script driven by `src/perch/__main__.py::cli`.

## Smoke-test

```sh
perch --version          # prints: perch <version>
perch                    # loads (or seeds) ~/.config/perch/config.toml and exits cleanly
PERCH_DEBUG=1 perch      # same, with DEBUG-level logging
```

Fresh-environment behaviour (no existing config) is that Perch writes a default `config.toml` into `$XDG_CONFIG_HOME/perch/` and exits `0`. A malformed `config.toml` with no `config.toml.bak` causes a non-zero exit and a pinpoint error in `$XDG_STATE_HOME/perch/perch.log` and on stderr.

## Checks CI runs

**Before every push, run [`local_CI.sh`](../local_CI.sh)** — it runs the same
checks as `.github/workflows/ci.yml` (every job), so a failure surfaces locally
in a few minutes instead of burning a CI run.

```sh
./local_CI.sh
```

It runs every check rather than stopping at the first failure like CI does, and
prints `safe to push` only when all pass. It must stay in lockstep with
`ci.yml` — see the hard rule in [`CLAUDE.md`](../CLAUDE.md), which
`tools/ci_lockstep_check.py` enforces mechanically.

**The test job runs once per interpreter in `ci.yml`'s matrix**, as CI does —
the versions are read out of `ci.yml`, so adding one there cannot leave the
gate testing the old set. Each gets a `uv`-managed environment under
`.venvs/py<version>` (gitignored, built on first use, and holding the same
`-e ".[dev]"` install CI performs), so the first run after a matrix change
takes a few minutes to populate and later ones do not. A version CI tests that
this machine cannot build is reported as a **failure**, never skipped quietly:
a matrix entry that silently drops is exactly the hole that let a 3.14-only
failure through a green 3.13 run (CI run 33145715623). This needs
[`uv`](https://docs.astral.sh/uv/) on `PATH`; it fetches the interpreters
itself.

The project `.venv` is still the environment to point an editor at — the gate
does not use it for the test job.

### Documentation-only pushes

`./local_CI.sh --docs` runs the docs job alone — `tools/docs_check.py`, which
verifies every relative link in the docs set resolves and that no retired or
forbidden string has crept outside the documents that record it. It is
stdlib-only and finishes in well under a second, against roughly half a minute
for the full gate.

The pre-push hook selects it on its own. Two `git config` keys, set per clone,
tell it how:

```sh
git config ants.gate.docsMode --docs
git config ants.gate.docsGlob 'docs/*.md|*.md|LICENSE'
```

Both are required. Without the glob the hook falls back to deciding by file
extension, which would let a lockfile or a workflow ride along as
"documentation". The glob is narrow on purpose: `data/*.metainfo.xml` is **not**
documentation here, because `appstreamcli` validates it in the packaging job.
Anything the glob does not list takes the full gate — a wrong guess must cost
time, never coverage.

The check is the mechanical half of `/perch-docs-check`. That skill also reads
tense against the roadmap and judges whether a swapped library named in prose
is history or a live claim; both need a reader, so neither is in the gate.

The individual test-job steps, if you want to run them by hand (same order as
CI):

```sh
ruff check .                            # lint
mypy                                    # strict type-check per pyproject.toml
python tools/intent_dispatch_audit.py   # every Intent variant has a real handler
pytest -ra                              # unit tests (conftest defaults QT_QPA_PLATFORM=offscreen)
```

The `tests/test_config_roundtrip.py` fixture exercises the tomlkit comment-preservation contract described in [`docs/02-state-format.md`](02-state-format.md) §Read / write split. A failure there is release-blocking.

## Layout of the tree

| Path | Contents |
|---|---|
| `src/perch/` | Package source. `__main__.py` is the CLI entry; `app.py` is the async `main()` coroutine; `config/` is the config subsystem; `core/` is the backend-agnostic middle of the program. |
| `tests/` | pytest suite; `conftest.py` installs an isolated XDG tree per test. |
| `docs/` | Design docs. Must stay in lockstep with code — see the [no-documentation-debt rule](../CLAUDE.md). |
| `packaging/` | Flathub manifest scaffold and submission notes. |
| `data/` | Icons, desktop/metainfo files (progressively populated from M3 onwards). |
| `.claude/` | Claude Code hooks, skills, settings — see [`CLAUDE.md`](../CLAUDE.md). |

## House rules

Summarised from [`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`CLAUDE.md`](../CLAUDE.md):

1. **Docs-first + no-doc-debt.** Every behaviour change updates `docs/` in the same PR.
2. **No debt of any kind** — no `TODO`/`FIXME` without a linked issue, no stubs-that-pretend, no silent workarounds, no suppressed type or lint warnings without an inline reason.
3. **Milestones are discrete.** Exit criteria are defined in [`docs/11-roadmap.md`](11-roadmap.md); a milestone is done only when they all pass in CI.
4. **Python floor is 3.12.** No `requires-python = ">=3.11"` strays, and no `from __future__` import that 3.12 no longer needs — with the deliberate exception of `from __future__ import annotations`, which is still opt-in and is the one Perch modules do use (see [`coding-standards.md`](coding-standards.md)).
5. Forbidden imports (invariants locked in Phase 2 / 2.5 — see [`docs/11-roadmap.md`](11-roadmap.md)): `dbus_next`, `ewmh`, `asyncqt`, `tomli_w`, `PySide6.QtAsyncio`. `asyncio.get_event_loop()` and `asyncio.ensure_future()` from a Qt slot are also forbidden; use `get_running_loop()` or `@qasync.asyncSlot` instead.
