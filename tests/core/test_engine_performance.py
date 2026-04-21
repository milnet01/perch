"""Performance harness for :func:`perch.core.engine.evaluate` (M7.d).

Exercises the 500-rule x 500-window sanity-check called out in
:file:`docs/11-roadmap.md` §M7 — Polish. The evaluator is pure Python,
so the test asserts a generous wall-clock ceiling that catches
quadratic or worse regressions without being brittle against ordinary
CI-runner jitter.

Scale-points:

* 100 rules x 100 windows — smoke test, expected well under 100 ms.
* 500 rules x 500 windows — the roadmap's sanity check, < 2 s budget.
* 1000 rules x 1000 windows — catches accidental O(n²) that 500x500 might
  miss (1000x1000 is 4x the work of 500x500).

The harness deliberately puts the *matching* rule last so every window
walks the full rules list once — worst-case linear match, matching the
cost the reducer incurs when a late-in-file rule is responsible for a
specific window.
"""

from __future__ import annotations

import time

import pytest

from perch.backend.types import Geometry, WindowInfo, WindowState, WindowType
from perch.core.actions import ApplyAction, PercentGeometry
from perch.core.engine import ApplyActionDecision, TriggerEvent, evaluate
from perch.core.matching import MatchPattern
from perch.core.rules import Rule


def _make_window(idx: int) -> WindowInfo:
    app = f"app-{idx}"
    return WindowInfo(
        id=f"w{idx}",
        app_id=app,
        wm_class=app,
        title=f"Window {idx}",
        pid=1000 + idx,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 800, 600),
        monitor="DP-1",
        desktop=0,
    )


def _make_rules(n: int) -> list[Rule]:
    """Build ``n`` rules. Rule ``i`` matches the window with ``app_id=app-i``.

    The last rule matches the first window, the penultimate the second,
    and so on — this forces every window's match to walk most of the
    rules list before landing, which is the stressing case.
    """
    action = ApplyAction(geometry=PercentGeometry(0.0, 0.0, 0.5, 1.0))
    rules: list[Rule] = []
    for i in range(n):
        # Match against the window whose id is (n-1-i), so the first
        # window's matching rule is the last one evaluated.
        target = n - 1 - i
        rules.append(
            Rule(
                name=f"rule-{i}",
                match=MatchPattern(app_id=f"app-{target}"),
                apply=action,
            )
        )
    return rules


def _default_kwargs(rules: list[Rule]) -> dict[str, object]:
    return {
        "rules": rules,
        "user_exclusions": [],
        "active_layout": None,
        "active_profile_name": None,
        "active_layout_name": None,
        "current_desktop": 0,
        "has_last_seen": False,
        "restore_on_open": False,
    }


@pytest.mark.parametrize(
    ("n_windows", "n_rules", "budget_s"),
    [
        (100, 100, 0.5),
        (500, 500, 2.0),
        (1000, 1000, 10.0),
    ],
)
def test_evaluate_scales_under_budget(
    n_windows: int, n_rules: int, budget_s: float
) -> None:
    """The evaluator must finish NxM evaluations inside ``budget_s`` seconds.

    Budgets are deliberately generous — the goal is to catch quadratic
    (or worse) regressions, not to pin a tight latency number that CI
    runners will flake against.
    """
    windows = [_make_window(i) for i in range(n_windows)]
    rules = _make_rules(n_rules)
    kw = _default_kwargs(rules)

    start = time.perf_counter()
    for w in windows:
        decision = evaluate(w, TriggerEvent.OPENED, **kw)  # type: ignore[arg-type]
        # Every window must hit a rule — protects the harness from an
        # accidental miss that would turn the test into a micro-benchmark
        # of "is_builtin_excluded plus fall-through".
        assert isinstance(decision, ApplyActionDecision)
    elapsed = time.perf_counter() - start

    assert elapsed < budget_s, (
        f"evaluate() took {elapsed:.3f}s for {n_windows}x{n_rules} "
        f"(budget {budget_s}s)"
    )


def test_evaluate_short_circuits_on_builtin_exclusion() -> None:
    """Exclusion path is O(1) regardless of rules list size.

    If this regresses to linear we'll see 500-dock-windows take the
    same time as 500-matching-windows, which defeats the whole purpose
    of the builtin exclusion gate.
    """
    rules = _make_rules(500)
    kw = _default_kwargs(rules)

    docks = [
        WindowInfo(
            id=f"dock-{i}",
            app_id="plasmashell",
            wm_class="plasmashell",
            title="",
            pid=42,
            type=WindowType.DOCK,
            state=WindowState.NORMAL,
            geometry=Geometry(0, 0, 1920, 40),
            monitor="DP-1",
            desktop=0,
        )
        for i in range(500)
    ]

    start = time.perf_counter()
    for w in docks:
        evaluate(w, TriggerEvent.OPENED, **kw)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - start

    # Short-circuit budget is tighter than the full-walk budget: if this
    # takes longer than the full-walk 500-rule path, the short-circuit
    # isn't doing its job.
    assert elapsed < 0.5, (
        f"builtin-exclusion short-circuit took {elapsed:.3f}s for "
        "500 dock windows (budget 0.5s)"
    )
