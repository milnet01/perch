"""Window matching — the field-by-field AND-predicate used by rules,
layouts, and exclusions.

Spec in ``docs/02-state-format.md`` §Match patterns and
``docs/07-rules-engine.md`` §Matching. Unspecified fields are wildcards;
``app_id`` / ``wm_class`` are globs; ``title`` is a Python ``re.search``
regex; ``pid`` is exact; ``type`` is "exact, comma-list" (any-of).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from perch.backend.types import WindowInfo, WindowType


class MatchValidationError(ValueError):
    """Raised when a raw ``match = { ... }`` block is malformed."""


@dataclass(frozen=True, slots=True)
class MatchPattern:
    app_id: str | None = None
    wm_class: str | None = None
    title: re.Pattern[str] | None = None
    pid: int | None = None
    types: tuple[WindowType, ...] = ()
    catch_all: bool = False

    def is_empty(self) -> bool:
        """True when no field is specified.

        Used by validation: an empty match block is usually a mistake (it
        would match every window) and requires an explicit ``catch_all =
        true`` flag to be accepted. See ``docs/07-rules-engine.md``
        §Validation.
        """
        return (
            self.app_id is None
            and self.wm_class is None
            and self.title is None
            and self.pid is None
            and not self.types
        )


def parse_match(raw: Any, prefix: str) -> MatchPattern:
    """Turn a raw TOML ``match = { ... }`` table into a :class:`MatchPattern`."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MatchValidationError(f"{prefix} must be a table")

    known = {"app_id", "wm_class", "title", "pid", "type", "catch_all"}
    unknown = set(raw.keys()) - known
    if unknown:
        raise MatchValidationError(
            f"{prefix}: unknown keys {sorted(unknown)!r}"
        )

    app_id = _opt_str(raw, "app_id", prefix)
    wm_class = _opt_str(raw, "wm_class", prefix)
    title = _parse_title(raw.get("title"), prefix)
    pid = _opt_int(raw, "pid", prefix)
    types = _parse_types(raw.get("type"), prefix)
    catch_all = bool(raw.get("catch_all", False))
    if not isinstance(raw.get("catch_all", False), bool):
        raise MatchValidationError(
            f"{prefix}.catch_all must be a boolean "
            f"(got {type(raw['catch_all']).__name__})"
        )

    return MatchPattern(
        app_id=app_id,
        wm_class=wm_class,
        title=title,
        pid=pid,
        types=types,
        catch_all=catch_all,
    )


def match_signature(pattern: MatchPattern) -> tuple[object, ...]:
    """Hashable summary of the pattern's source shape.

    Used when comparing patterns across independent ``parse_match`` calls —
    most notably for layout override replacement, where the user expresses
    equality by writing the same match block twice and expects the
    override to replace the base entry. The compiled :class:`re.Pattern`
    objects themselves compare by identity, so this signature reduces
    ``title`` to its original regex string for that comparison.
    """
    return (
        pattern.app_id,
        pattern.wm_class,
        pattern.title.pattern if pattern.title is not None else None,
        pattern.pid,
        pattern.types,
        pattern.catch_all,
    )


def match_window(pattern: MatchPattern, window: WindowInfo) -> bool:
    """Return True if ``window`` satisfies every specified field in ``pattern``."""
    if pattern.catch_all:
        return True

    if pattern.app_id is not None and not fnmatchcase(
        window.app_id, pattern.app_id
    ):
        return False
    if pattern.wm_class is not None and not fnmatchcase(
        window.wm_class, pattern.wm_class
    ):
        return False
    if pattern.title is not None and pattern.title.search(window.title) is None:
        return False
    if pattern.pid is not None and window.pid != pattern.pid:
        return False
    return not (pattern.types and window.type not in pattern.types)


# ── helpers ────────────────────────────────────────────────────────────────
def _opt_str(raw: dict[str, Any], key: str, prefix: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, str):
        raise MatchValidationError(
            f"{prefix}.{key} must be a string "
            f"(got {type(value).__name__})"
        )
    return value


def _opt_int(raw: dict[str, Any], key: str, prefix: str) -> int | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise MatchValidationError(
            f"{prefix}.{key} must be an integer "
            f"(got {type(value).__name__})"
        )
    return int(value)


def _parse_title(raw: Any, prefix: str) -> re.Pattern[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise MatchValidationError(
            f"{prefix}.title must be a regex string "
            f"(got {type(raw).__name__})"
        )
    try:
        return re.compile(raw)
    except re.error as exc:
        raise MatchValidationError(
            f"{prefix}.title is not a valid regex: {exc}"
        ) from exc


_VALID_TYPES: frozenset[str] = frozenset(t.value for t in WindowType)


def _parse_types(raw: Any, prefix: str) -> tuple[WindowType, ...]:
    """``type`` accepts a single string or a comma-joined list of types."""
    if raw is None:
        return ()
    if not isinstance(raw, str):
        raise MatchValidationError(
            f"{prefix}.type must be a string (comma-separated for multiple); "
            f"got {type(raw).__name__}"
        )
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise MatchValidationError(f"{prefix}.type must not be empty")
    out: list[WindowType] = []
    for name in names:
        if name not in _VALID_TYPES:
            raise MatchValidationError(
                f"{prefix}.type: {name!r} is not a known window type "
                f"(known: {sorted(_VALID_TYPES)})"
            )
        out.append(WindowType(name))
    return tuple(out)


