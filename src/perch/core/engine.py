"""Rules engine — the evaluator that turns a window event into one decision.

Authoritative spec: ``docs/07-rules-engine.md`` §Inputs and outputs,
§Evaluation order. This module is deliberately pure: it consumes typed
config plus a window snapshot and returns a :class:`Decision`. Execution
(geometry resolution against live output info, issuing backend commands)
happens in the reducer (M2.d).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from perch.backend.types import WindowInfo

from .actions import ApplyAction
from .exclusions import is_builtin_excluded, is_user_excluded
from .layouts import Layout
from .matching import MatchPattern, match_window
from .rules import Rule


class TriggerEvent(StrEnum):
    """Why the engine was asked to evaluate this window."""

    OPENED = "opened"
    CHANGED = "changed"
    USER_TRIGGER = "user_trigger"


# ── Decisions ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Ignore:
    """Do nothing. ``source`` names the reason for logging + the Rules trace."""

    source: str


@dataclass(frozen=True, slots=True)
class RestoreLastSeen:
    """Apply the remembered geometry for this window's identity."""


@dataclass(frozen=True, slots=True)
class ApplyActionDecision:
    """Apply the named rule's / layout's action to this window."""

    action: ApplyAction
    source: str  # "rule:<name>" | "rule:<index>" | "layout:<name>"


Decision = Ignore | RestoreLastSeen | ApplyActionDecision


# ── Evaluator ──────────────────────────────────────────────────────────────
def evaluate(
    window: WindowInfo,
    trigger: TriggerEvent,
    *,
    rules: list[Rule],
    user_exclusions: list[MatchPattern],
    active_layout: Layout | None,
    active_profile_name: str | None,
    active_layout_name: str | None,
    current_desktop: int,
    has_last_seen: bool,
    restore_on_open: bool,
) -> Decision:
    """Return one decision per ``docs/07-rules-engine.md`` §Evaluation order.

    Order:

    1. Built-in exclusion (``WindowType`` in ``DESKTOP`` / ``DOCK``) → ``Ignore``.
    2. User exclusions (``[exclusions].patterns``) → ``Ignore``.
    3. First matching ``[[rules]]`` entry whose ``context`` fits → ``ApplyAction``.
    4. Active layout entry matching this window → ``ApplyAction``.
    5. Last-seen geometry (only on ``OPENED`` / ``USER_TRIGGER``, and only when
       ``general.restore_on_open = true``) → ``RestoreLastSeen``.
    6. Otherwise → ``Ignore("no-match")``.
    """
    if is_builtin_excluded(window):
        return Ignore(source="builtin-exclusion")
    if is_user_excluded(window, user_exclusions):
        return Ignore(source="user-exclusion")

    for i, rule in enumerate(rules):
        if not rule.context.matches(
            active_profile_name, active_layout_name, current_desktop
        ):
            continue
        if match_window(rule.match, window):
            return ApplyActionDecision(
                action=rule.apply, source=_rule_source(rule, i)
            )

    if active_layout is not None:
        for entry in active_layout.windows:
            if match_window(entry.match, window):
                return ApplyActionDecision(
                    action=entry.apply,
                    source=f"layout:{active_layout.name}",
                )

    if (
        trigger in (TriggerEvent.OPENED, TriggerEvent.USER_TRIGGER)
        and restore_on_open
        and has_last_seen
    ):
        return RestoreLastSeen()

    return Ignore(source="no-match")


def _rule_source(rule: Rule, index: int) -> str:
    return f"rule:{rule.name}" if rule.name else f"rule:[{index}]"
