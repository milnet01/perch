"""User rules — ``[[rules]]`` entries with optional context gating.

Spec in ``docs/07-rules-engine.md`` §Matching, §Context, §Validation.
A rule binds a :class:`MatchPattern` to an :class:`ApplyAction`, with an
optional :class:`Context` that further constrains activation to the
current profile / layout / desktop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import (
    ActionValidationError,
    ApplyAction,
    parse_action,
)
from .matching import MatchPattern, MatchValidationError, parse_match


class RuleValidationError(ValueError):
    """Raised when a ``[[rules]]`` entry is malformed."""


@dataclass(frozen=True, slots=True)
class Context:
    """Optional gating on the current session state.

    All specified fields must match the caller-supplied context for the
    rule to fire (AND semantics). ``desktop`` is the current virtual
    desktop index.
    """

    profile: str | None = None
    layout: str | None = None
    desktop: int | None = None

    def matches(
        self,
        active_profile: str | None,
        active_layout: str | None,
        current_desktop: int,
    ) -> bool:
        if self.profile is not None and self.profile != active_profile:
            return False
        if self.layout is not None and self.layout != active_layout:
            return False
        return not (
            self.desktop is not None and self.desktop != current_desktop
        )

    def is_any(self) -> bool:
        """True when no field is specified — the rule is not context-gated."""
        return (
            self.profile is None and self.layout is None and self.desktop is None
        )


@dataclass(frozen=True, slots=True)
class Rule:
    name: str | None
    match: MatchPattern
    apply: ApplyAction
    context: Context = Context()


def parse_rules(raw: list[dict[str, Any]]) -> list[Rule]:
    """Validate and convert ``[[rules]]`` tables into :class:`Rule` objects."""
    out: list[Rule] = []
    for i, entry in enumerate(raw):
        prefix = f"[[rules]][{i}]"
        if not isinstance(entry, dict):
            raise RuleValidationError(f"{prefix} must be a table")

        known = {"name", "match", "apply", "context"}
        unknown = set(entry.keys()) - known
        if unknown:
            raise RuleValidationError(
                f"{prefix}: unknown keys {sorted(unknown)!r}"
            )

        name = entry.get("name")
        if name is not None and not isinstance(name, str):
            raise RuleValidationError(
                f"{prefix}.name must be a string "
                f"(got {type(name).__name__})"
            )

        if "match" not in entry:
            raise RuleValidationError(f"{prefix}: missing 'match'")
        try:
            pattern = parse_match(entry["match"], f"{prefix}.match")
        except MatchValidationError as exc:
            raise RuleValidationError(str(exc)) from exc
        if pattern.is_empty() and not pattern.catch_all:
            raise RuleValidationError(
                f"{prefix}.match: empty match blocks are rejected — set "
                "catch_all = true if you really want to match every window "
                "(see docs/07-rules-engine.md §Validation)"
            )

        if "apply" not in entry:
            raise RuleValidationError(f"{prefix}: missing 'apply'")
        try:
            action = parse_action(entry["apply"], f"{prefix}.apply")
        except ActionValidationError as exc:
            raise RuleValidationError(str(exc)) from exc

        context = _parse_context(entry.get("context"), f"{prefix}.context")

        out.append(
            Rule(name=name, match=pattern, apply=action, context=context)
        )
    return out


def _parse_context(raw: Any, prefix: str) -> Context:
    if raw is None:
        return Context()
    if not isinstance(raw, dict):
        raise RuleValidationError(f"{prefix} must be a table")

    known = {"profile", "layout", "desktop"}
    unknown = set(raw.keys()) - known
    if unknown:
        raise RuleValidationError(
            f"{prefix}: unknown keys {sorted(unknown)!r}"
        )

    profile = raw.get("profile")
    if profile is not None and not isinstance(profile, str):
        raise RuleValidationError(
            f"{prefix}.profile must be a string "
            f"(got {type(profile).__name__})"
        )
    layout = raw.get("layout")
    if layout is not None and not isinstance(layout, str):
        raise RuleValidationError(
            f"{prefix}.layout must be a string "
            f"(got {type(layout).__name__})"
        )
    desktop = raw.get("desktop")
    if desktop is not None:
        if isinstance(desktop, bool) or not isinstance(desktop, int):
            raise RuleValidationError(
                f"{prefix}.desktop must be an integer "
                f"(got {type(desktop).__name__})"
            )
        if desktop < 0:
            raise RuleValidationError(
                f"{prefix}.desktop index must be non-negative (got {desktop})"
            )

    return Context(profile=profile, layout=layout, desktop=desktop)
