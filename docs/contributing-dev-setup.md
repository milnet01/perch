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

Always run these before pushing:

```sh
ruff check .          # lint
mypy                  # strict type-check per pyproject.toml
pytest -ra            # unit tests (pytest-xvfb handles the display)
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
4. **Python floor is 3.12.** No `requires-python = ">=3.11"` strays, no `from __future__` that 3.12 no longer needs.
5. Forbidden imports (invariants locked in Phase 2 / 2.5 — see [`docs/11-roadmap.md`](11-roadmap.md)): `dbus_next`, `ewmh`, `asyncqt`, `tomli_w`, `PySide6.QtAsyncio`. `asyncio.get_event_loop()` and `asyncio.ensure_future()` from a Qt slot are also forbidden; use `get_running_loop()` or `@qasync.asyncSlot` instead.
