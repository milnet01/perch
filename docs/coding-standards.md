# Coding standard

How Perch's Python is written. This describes what the code and its tooling
**actually enforce today** — the authoritative lint/type config lives in
[`../pyproject.toml`](../pyproject.toml); this doc summarises intent and the
conventions that tooling can't check. When the two disagree, `pyproject.toml`
wins and this doc is the bug.

## Language version

- **Floor is Python 3.12** (`requires-python = ">=3.12"`). CI runs the full
  3.12 / 3.13 / 3.14 matrix. No `>=3.11` strays.
- Write **current idioms**, not the ones that still compile: `match`/`case`
  over `isinstance` ladders, `X | Y` unions and `X | None` over
  `Optional`/`Union`, builtin generics (`list[int]`, `dict[str, T]`) over the
  `typing` aliases.
- Every module starts with `from __future__ import annotations` so annotations
  stay lazy strings. The only exceptions in-tree are the trivial `__init__.py`
  re-export shims (root, `config/`, `core/`) — add it to any module that
  carries real annotations.

## Lint & format

- **ruff** is the single linter and formatter. Rule families in
  `[tool.ruff.lint]`: `E`, `F`, `I` (import sort), `UP` (pyupgrade — keeps the
  current-idiom rule above honest), `B` (bugbear), `SIM`, `RUF`. Line length
  **100**, target `py312`.
- `ruff check .` runs clean before every push (it's the first step of
  `local_CI.sh`). A PostToolUse hook also runs `ruff check` on each edited
  `.py` so issues surface in-session.

## Typing

- **mypy `strict`** with `warn_unreachable`, over `src/perch` and `tests` (see
  `[tool.mypy]`). Full annotations on every function signature, including
  `-> None`. `mypy` (no args) runs clean before every push.
- Untyped third-party stubs are whitelisted centrally via
  `[[tool.mypy.overrides]]` (`qasync`, `Xlib.*`, `sdbus.*`, `i3ipc`) — don't
  scatter per-call ignores for those.
- Value types are `@dataclass` (widely used across `core/`); Qt-facing
  interfaces are `typing.Protocol`.

## Async model

Perch runs **one event loop** driving both Qt and asyncio via `qasync`. The
loop is bootstrapped in `__main__.py::cli` as
`asyncio.run(app_main(...), loop_factory=QEventLoop)`, with the `QApplication`
constructed *before* the loop (qasync ≥0.28 asserts on it).

- Get the loop with **`asyncio.get_running_loop()`**, never
  `asyncio.get_event_loop()`. Schedule with `loop.create_task(...)` /
  `asyncio.create_task(...)` from inside a coroutine.
- Wire Qt signals to async handlers through **`qasync.asyncSlot(...)`** (see
  `core/reducer.py::bind_signals`), never `asyncio.ensure_future()` from a
  slot. Both `get_event_loop()` and slot-side `ensure_future()` are forbidden
  invariants — see the [house rules](contributing-dev-setup.md#house-rules).

## Forbidden imports

Locked in Phase 2 / 2.5 research; enforced by `/audit` and the house rules.
Never import: **`dbus_next`**, **`ewmh`**, **`asyncqt`**, **`tomli_w`**,
**`PySide6.QtAsyncio`**. Two of these are libraries Perch deliberately swapped:
`dbus-next` → **`sdbus`** (active, C-backed, clean async that attaches to the
running loop) and `python-ewmh` → **`python-xlib`** + a small in-tree EWMH
helper (`python-ewmh` is unmaintained since 2017 and unpackaged on
Fedora/openSUSE). See [`01-architecture.md`](01-architecture.md) §Dependencies.

## Logging

- Module logger: `log = logging.getLogger(__name__)` at module scope. The tree
  roots at `perch`; a few deep modules pin an explicit dotted name
  (e.g. `"perch.backend.kwin.scripting"`) — match that only when a module needs
  a stable name independent of its import path.
- `logging_setup.configure_logging()` owns handler config (rotating file at
  `$XDG_STATE_HOME/perch/perch.log` + stderr); modules just call `log.*`. Use
  `%`-style lazy args (`log.info("x: %s", val)`), not f-strings, in log calls.
- `PERCH_DEBUG=1` (or `--debug`) raises the level to DEBUG. Window titles are
  redacted unless `PERCH_LOG_TITLES=1` — route anything privacy-sensitive
  through `logging_privacy`.

## Error handling

- Domain/validation errors subclass **`ValueError`** with a **pinpoint**
  message naming the offending field/value (`ActionValidationError`,
  `LayoutValidationError`, `SchemaError`, `ResolveError`, `StateLoadError`, …).
- Backends raise the **`BackendError`** hierarchy (`BackendUnavailable`,
  `BackendDisconnected`, `BackendUnsupported`, `UnknownWindow`,
  `UnknownOutput`). A missing transport is `BackendUnavailable`, not a bare
  `ImportError`.
- **No silent workarounds** (house rule 2): no bare `except: pass`, no
  suppressed lint/type warnings without an inline reason. Where a suppression
  is genuinely correct it carries the reason inline — e.g.
  `# type: ignore[empty-body]` on `Protocol` method stubs, `# noqa: B008` on Qt
  `QModelIndex()` default args. Silence without a reason is a defect.

## Ethos

- **Shortest correct implementation.** 50 lines beat 250; no scaffolding for
  hypothetical futures, no error paths for cases that can't reach the call site.
- **Reuse before rewriting.** Call the existing helper, or refactor it to cover
  the new case, before adding a parallel one.
- **Docstrings carry the *why* and the doc anchor.** Module and public-symbol
  docstrings cite the governing design doc (`docs/NN-*.md §Section`) and use
  Sphinx cross-refs (`:class:`, `:meth:`, `:func:`) — the code stays traceable
  back to the contract it implements.
- **Docs-first / no-doc-debt.** Any behaviour change updates the relevant
  `docs/` file in the same change — this is a hard rule, see `../CLAUDE.md`.

## See also

- [`../pyproject.toml`](../pyproject.toml) — authoritative ruff / mypy / pytest config
- [`contributing-dev-setup.md`](contributing-dev-setup.md) — dev env, `local_CI.sh`, house rules
- [`dependency-policy.md`](dependency-policy.md) — version currency & allowed caps
- [`01-architecture.md`](01-architecture.md) — event-loop bootstrap & library choices
- [`filename-standards.md`](filename-standards.md) — file & directory naming
- [`../CLAUDE.md`](../CLAUDE.md) — project hard rules
