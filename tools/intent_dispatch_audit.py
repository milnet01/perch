#!/usr/bin/env python3
"""Intent dispatch audit — catch "shipped stub" handlers.

Reads :file:`src/perch/ui/intents.py` and :file:`src/perch/app.py`; for
every variant of the ``Intent`` union, verifies that the ``match``
statement inside ``_handle_intent`` has a case *and* that the handler
body does non-trivial work (i.e. is not just a ``log.*`` call).

Why this exists
---------------

Perch's v1.0.0 smoke test found four shipped stubs where a tray
intent was wired to nothing but a log line (``SnapFocused`` → "routed
in M4", ``ShowAbout`` → "stub — lands in a follow-up milestone",
``TogglePause`` → "stub — reducer flag in M4", placeholder
panes in the config dialog). Those slipped past every static-analysis
pass because the regex audit only matches literal strings — it can't
tell "this handler does real work" from "this handler logs and
returns". This script adds the missing semantic check.

Design
------

- **Intent variants** are enumerated from the ``Intent`` union type
  alias in :file:`intents.py`. Every name in the union must be a
  top-level ``@dataclass`` in the same file.
- **Handlers** are enumerated from the ``match intent:`` block inside
  ``_handle_intent`` in :file:`app.py`. Each ``case`` pattern's class
  name maps to the intent variant.
- **Triviality check**: a handler body is *trivial* if every
  statement is either:

    * a docstring or bare constant,
    * a ``_ = quit_app``-style assignment to an underscore (these are
      "retained-for-api" markers, not real work),
    * a ``log.*`` / ``logger.*`` / ``logging.*`` call,
    * a simple comment-only line (``ast`` drops comments, so this
      falls out naturally).

  A handler with *any* non-trivial statement — a function call, an
  ``await``, a ``_spawn(...)``, a ``close_event.set()``, etc. — is
  considered real.

- **Excluded-from-trivial**: if the body is "just close_event.set()",
  Quit() — that's legitimate. We special-case statements that mutate
  shared state via ``.set()`` / ``.clear()`` on identifier targets
  as non-trivial.

Exit code is the number of problems found, so CI can gate on it.

Usage
-----

::

    python3 tools/intent_dispatch_audit.py

From the repo root. No arguments; paths are fixed to Perch's layout.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTENTS_FILE = REPO_ROOT / "src" / "perch" / "ui" / "intents.py"
DISPATCHER_FILE = REPO_ROOT / "src" / "perch" / "app.py"
DISPATCHER_FUNCTION = "_handle_intent"
UNION_NAME = "Intent"

LOG_CALL_TARGETS = frozenset({"log", "logger", "logging"})


@dataclass(frozen=True)
class Finding:
    severity: str
    variant: str
    message: str
    location: str = ""


def _intent_variants(path: Path) -> set[str]:
    """Return the set of dataclass names that form the Intent union.

    Reads the ``Intent = A | B | C`` alias assignment and collects the
    BitOr operands by name. Raises if the alias is missing.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id == UNION_NAME:
                return _collect_union_operands(node.value)
    raise RuntimeError(
        f"{path}: no top-level assignment to {UNION_NAME!r}"
    )


def _collect_union_operands(node: ast.AST | None) -> set[str]:
    """Walk ``A | B | C`` and return every ``Name`` leaf."""
    if node is None:
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _collect_union_operands(node.left) | _collect_union_operands(
            node.right
        )
    # Anything else (a parenthesised expr, a Tuple) — walk children.
    out: set[str] = set()
    for child in ast.iter_child_nodes(node):
        out |= _collect_union_operands(child)
    return out


def _find_dispatcher(path: Path, function_name: str) -> ast.FunctionDef:
    """Locate ``function_name`` in ``path`` and return its AST node."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == function_name
            and isinstance(node, ast.FunctionDef)
        ):
            return node
    raise RuntimeError(f"{path}: no function named {function_name!r}")


def _dispatched_cases(
    func: ast.FunctionDef,
) -> dict[str, ast.match_case]:
    """Return ``{variant_name: case_node}`` from the match statement."""
    out: dict[str, ast.match_case] = {}
    for node in ast.walk(func):
        if not isinstance(node, ast.Match):
            continue
        for case in node.cases:
            name = _case_variant_name(case.pattern)
            if name is not None:
                out[name] = case
    return out


def _case_variant_name(pattern: ast.pattern) -> str | None:
    """Extract the class name from a ``case ClassName(...)`` pattern."""
    if isinstance(pattern, ast.MatchClass):
        cls = pattern.cls
        if isinstance(cls, ast.Name):
            return cls.id
        if isinstance(cls, ast.Attribute):
            return cls.attr
    return None


def _is_trivial_statement(stmt: ast.stmt) -> bool:
    """``True`` when the statement doesn't do real work.

    "Real work" = any function call, await, assignment to something
    other than an underscore, a ``.set()`` / ``.clear()`` side effect,
    a control-flow with a non-trivial branch, etc.
    """
    # Docstrings / bare literal expressions.
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return True
    # ``_ = foo`` placeholder assignments used to silence "unused" lints.
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        if isinstance(target, ast.Name) and target.id == "_":
            return True
    # ``log.something(...)`` — the stub pattern we're looking for.
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        func = call.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in LOG_CALL_TARGETS
        ):
            return True
    return False


def _has_effectful_call(node: ast.expr | None) -> bool:
    """``True`` when an expression calls anything other than a log target.

    A guard's own condition can be the side effect -- ``if not
    QDesktopServices.openUrl(url):`` does the work in the test, not the body.
    """
    if node is None:
        return False
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in LOG_CALL_TARGETS
        ):
            continue
        return True
    return False


def _real_statements(statements: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield the statements that could carry a side effect.

    Descends into compound statements: a guard or loop whose own condition does
    nothing is only as real as its body, so ``if cond: log.debug(...)`` is still
    a stub. Classifying only the top level counted the ``if`` itself as real
    work -- a shape already present in the dispatcher.
    """
    for stmt in statements:
        if isinstance(stmt, ast.If | ast.While):
            if _has_effectful_call(stmt.test):
                yield stmt
                continue
            yield from _real_statements(stmt.body)
            yield from _real_statements(stmt.orelse)
        elif isinstance(stmt, ast.For | ast.AsyncFor):
            if _has_effectful_call(stmt.iter):
                yield stmt
                continue
            yield from _real_statements(stmt.body)
            yield from _real_statements(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            yield from _real_statements(stmt.body)
            for handler in stmt.handlers:
                yield from _real_statements(handler.body)
            yield from _real_statements(stmt.orelse)
            yield from _real_statements(stmt.finalbody)
        elif isinstance(stmt, ast.Match):
            if _has_effectful_call(stmt.subject):
                yield stmt
                continue
            for case in stmt.cases:
                yield from _real_statements(case.body)
        else:
            # ``with`` included: entering a context manager IS a side effect.
            yield stmt


def _audit_case_body(statements: list[ast.stmt]) -> str | None:
    """Return ``None`` when the body does real work, else a diagnostic.

    A body is a stub when every statement -- at any nesting depth -- is a
    docstring, a placeholder underscore assignment or a log call.
    """
    for stmt in _real_statements(statements):
        if not _is_trivial_statement(stmt):
            return None
    return "handler body is empty or consists only of log calls"


def run() -> int:
    findings: list[Finding] = []

    variants = _intent_variants(INTENTS_FILE)
    dispatcher = _find_dispatcher(DISPATCHER_FILE, DISPATCHER_FUNCTION)
    cases = _dispatched_cases(dispatcher)

    missing = variants - set(cases.keys())
    for name in sorted(missing):
        findings.append(
            Finding(
                severity="error",
                variant=name,
                message=(
                    "intent variant has no case in "
                    f"{DISPATCHER_FUNCTION}()"
                ),
                location=str(DISPATCHER_FILE),
            )
        )

    extra = set(cases.keys()) - variants
    for name in sorted(extra):
        findings.append(
            Finding(
                severity="warning",
                variant=name,
                message=(
                    "case matches a class that is not in the "
                    f"{UNION_NAME} union — stale handler?"
                ),
                location=f"{DISPATCHER_FILE}:{cases[name].pattern.lineno}",
            )
        )

    for name, case in sorted(cases.items()):
        if name not in variants:
            continue
        problem = _audit_case_body(case.body)
        if problem is not None:
            findings.append(
                Finding(
                    severity="error",
                    variant=name,
                    message=problem,
                    location=f"{DISPATCHER_FILE}:{case.pattern.lineno}",
                )
            )

    # Report.
    if not findings:
        print(
            f"OK — every {UNION_NAME} variant has a real handler "
            f"({len(variants)} checked)."
        )
        return 0

    print(f"Intent dispatch audit — {len(findings)} finding(s):")
    print()
    for f in findings:
        loc = f" [{f.location}]" if f.location else ""
        print(f"  {f.severity:8} {f.variant}: {f.message}{loc}")

    return len(findings)


if __name__ == "__main__":
    sys.exit(1 if run() else 0)  # a count > 255 would wrap to 0 = success
