# Testing standard

How Perch's test suite is structured, how it runs headless in CI, and the rules
every new test follows. Config values (dependency pins, marker text, xvfb dims)
are authoritative in [`pyproject.toml`](../pyproject.toml) `[tool.pytest.ini_options]`
and the dev extras — this doc references them rather than restating numbers that
drift.

## Stack

- **pytest** as the runner; `testpaths = ["tests"]`.
- **pytest-qt** — supplies the `qapp` / `qtbot` fixtures; `qt_api = "pyside6"`
  pins the Qt binding so tests never import a different wrapper.
- **pytest-asyncio** with `asyncio_mode = "auto"` — every `async def test_*`
  runs on the loop with no per-test `@pytest.mark.asyncio` decorator. Backend
  methods are all awaitables (see [03-backend-interface.md](03-backend-interface.md)),
  so most backend/core tests are `async`.
- **pytest-xvfb** — provides a virtual framebuffer (`xvfb_width`/`xvfb_height`
  in the ini block) for the rare test that needs a real X server.

The dev toolchain installs via `pip install -e ".[dev]"` (the `dev` extra in
`pyproject.toml`). See [contributing-dev-setup.md](contributing-dev-setup.md).

## Headless Qt (offscreen QPA)

`tests/conftest.py` calls `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`
at collection time, before any `QApplication` is constructed. This keeps UI
tests from compositing a real top-level window onto the host desktop. It uses
`setdefault`, so a CI override (`QT_QPA_PLATFORM=minimal`) still wins. CI and
`local_CI.sh` both export `QT_QPA_PLATFORM=offscreen` explicitly as belt-and-braces.

## Per-test XDG isolation

The `xdg_env` fixture in `tests/conftest.py` points `$XDG_CONFIG_HOME`,
`$XDG_STATE_HOME`, and `$XDG_CACHE_HOME` at a fresh `tmp_path` tree and deletes
`PERCH_DEBUG` / `PERCH_LOG_TITLES` from the environment. A test that touches
config, state, or logs **must** take `xdg_env` so the real user's
`~/.config/perch` is never read or written.

## Layout

```
tests/
  conftest.py            offscreen QPA + xdg_env fixture
  test_*.py              CLI, config loader/roundtrip/schema, logging, paths, autostart
  core/                  backend-agnostic engine: rules, snaps, layouts, profiles, reducer, resolver…
  ui/                    Qt dialog/tray/pane tests (need qtbot + offscreen QPA)
  backend/
    conftest.py          parametrises the compliance suite over every available backend
    test_compliance.py   the backend compliance suite (see below)
    test_mock.py         MockBackend driver
    kwin/ x11/ …         per-backend unit + live-integration tests
```

## Backend compliance suite

`tests/backend/test_compliance.py` is the contract test every `WindowBackend`
must pass. `tests/backend/conftest.py` builds `BACKEND_CLASSES` by lazily
importing each backend and filtering to those whose `is_available()` env-probe
returns `True` on the current host — `mock` is always in; `kwin` / `x11` /
`sway` / `hyprland` / `mutter` join only when their transport is detectable. The
`backend` fixture parametrises across that set, so one suite exercises the whole
matrix. Tests that need a synthetically seeded window (`_spawn_window`) guard
with `isinstance(backend, MockBackend)` and skip against live backends — those
assert the mock's driver, not the contract. Adding a backend means making it
pass this suite unchanged; see [03-backend-interface.md](03-backend-interface.md)
§Mock backend and §Capability negotiation.

## Live integration tests (`x11` / `kwin` markers)

Two markers gate tests that spawn a **real** compositor:

- `@pytest.mark.x11` — launches `Xvfb` + `openbox` (fixture in
  `tests/backend/x11/conftest.py`); self-skips when those binaries are absent.
- `@pytest.mark.kwin` — spawns a private D-Bus + `kwin_wayland --virtual`
  session (`tests/backend/kwin/conftest.py`).

They are **opt-in**: run with `pytest -m x11` (or `-m kwin`). They are excluded
by default in `local_CI.sh` (`pytest -m "not x11 and not kwin"`) because a dev
box may have `openbox` installed and would run them live and flaky. **CI does
not exclude them** — it runs plain `pytest -ra`, but installs no compositor, so
the fixtures self-skip and the effect is the same. Live tests therefore give
coverage only on a machine with the compositor present, never a false green.

## Regression tests: reproduce-before-fix

Per [../CLAUDE.md](../CLAUDE.md), a reported bug is fixed **failing-test-first**:
write a test that reproduces the symptom, confirm it fails, then fix and watch it
pass — the test stays as a regression lock. Scaffold these with the
`/feature-test` skill (feature-test-writer subagent), which produces a
`tests/features/<name>/spec.md` (the behaviour contract) plus its test file. Skip
the ceremony only for mechanical one-liners where reproduction is pure overhead.

## The matrix and the push gate

CI (`.github/workflows/ci.yml`) runs the test job across **Python 3.12 / 3.13 /
3.14**; `requires-python` floors at 3.12. `local_CI.sh` runs on whatever
interpreter is on `PATH`, so a version-specific failure can still slip a green
local run — run it under each interpreter for full parity. **Hard rule: get
`safe to push` from `./local_CI.sh` before every push** (see [../CLAUDE.md](../CLAUDE.md)
and [contributing-dev-setup.md](contributing-dev-setup.md)). `local_CI.sh` and
`ci.yml` must stay in lockstep — edit both in the same commit.

## What not to do

- **No network in unit tests.** Nothing under `tests/` should open a socket or
  make an HTTP request; the whole suite runs offline (CI validates with
  `--no-net`). Compositor transports are exercised via `MockBackend` or the
  gated live markers, never a real remote.
- **No reliance on a real display outside the `x11` / `kwin` markers.** Default
  tests run under offscreen QPA with no X server or compositor. If a test needs
  one, it carries the appropriate marker and its skip guard — it never assumes
  `$DISPLAY`.
- **No touching the real user environment.** Take `xdg_env` for anything that
  reads or writes config/state/cache.
- **No `@pytest.mark.asyncio`** — `asyncio_mode = "auto"` handles it.

## See also

- [03-backend-interface.md](03-backend-interface.md)
- [contributing-dev-setup.md](contributing-dev-setup.md)
- [../CLAUDE.md](../CLAUDE.md)
