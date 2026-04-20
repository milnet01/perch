"""Config-mutation helpers for the settings dialog.

The dialog reads a typed :class:`~perch.config.schema.Config`, edits a
working copy in-memory, and writes changes back by **mutating the user's
``tomlkit`` document** rather than regenerating one from scratch. The
regenerate-from-scratch path would lose every comment, blank line, and
formatting choice the user made by hand — the round-trip fixture in
``tests/test_config_roundtrip.py`` guards against that.

M3.b covers the operations the settings dialog needs:

* ``apply_general(...)`` — flip the four ``[general]`` toggles / combo.
* ``reorder_rules(...)`` / ``delete_rule(...)`` — the Rules section needs
  reorder-and-delete; full rule editing lands in M3.c alongside the match
  and geometry editors.
* ``delete_exclusion(...)`` / ``reorder_exclusions(...)`` — mirror for
  the Exclusions section.

Deeper rule editing is deliberately deferred to M3.c. Everything here
edits the existing tomlkit AST in place — no structural rebuild.
"""

from __future__ import annotations

from typing import Any

import tomlkit
from tomlkit import TOMLDocument

from .schema import VALID_THEMES


class ConfigEditError(ValueError):
    """Raised when a dialog-driven mutation is rejected."""


# ── General section ─────────────────────────────────────────────────────

_GENERAL_BOOL_KEYS = ("start_at_login", "restore_on_open", "notify_on_restore")


def apply_general(
    document: TOMLDocument,
    *,
    start_at_login: bool,
    restore_on_open: bool,
    notify_on_restore: bool,
    theme: str,
) -> None:
    """Mutate ``document`` so ``[general]`` reflects the four toggles.

    Creates the ``[general]`` table if absent.
    """
    if theme not in VALID_THEMES:
        raise ConfigEditError(
            f"[general].theme must be one of {VALID_THEMES!r} (got {theme!r})"
        )
    general = document.get("general")
    if general is None:
        general = tomlkit.table()
        document["general"] = general

    general["start_at_login"] = start_at_login
    general["restore_on_open"] = restore_on_open
    general["notify_on_restore"] = notify_on_restore
    general["theme"] = theme


# ── Rules section ───────────────────────────────────────────────────────


def _rules_aot(document: TOMLDocument) -> Any:
    """Return the ``[[rules]]`` array-of-tables, or ``None`` if absent."""
    return document.get("rules")


def reorder_rules(document: TOMLDocument, new_order: list[int]) -> None:
    """Rewrite ``[[rules]]`` so its order matches ``new_order``.

    ``new_order`` is a permutation of ``range(len(rules))``; violating
    that raises :class:`ConfigEditError` rather than silently dropping or
    duplicating rules.

    Mutates the existing AoT node in place so tomlkit preserves leading /
    trailing / inter-entry comments — rebuilding the AoT from scratch
    dropped trivia that sat between entries and the next top-level block.
    """
    aot = _rules_aot(document)
    n = 0 if aot is None else len(aot)
    if sorted(new_order) != list(range(n)):
        raise ConfigEditError(
            f"reorder_rules: invalid permutation of {n} rules: {new_order!r}"
        )
    if aot is None or n < 2:
        return
    # Snapshot the existing entries, then re-seat them in the new order.
    snapshots = [aot[i] for i in range(n)]
    reordered = [snapshots[i] for i in new_order]
    for _ in range(n):
        del aot[0]
    for entry in reordered:
        aot.append(entry)


def delete_rule(document: TOMLDocument, index: int) -> None:
    """Drop the rule at ``index`` from ``[[rules]]`` in place."""
    aot = _rules_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(
            f"delete_rule: index {index} out of range "
            f"(0..{(len(aot) - 1) if aot is not None else -1})"
        )
    del aot[index]


# ── Exclusions section ──────────────────────────────────────────────────


def _exclusion_array(document: TOMLDocument) -> Any:
    """Return the ``[exclusions].patterns`` array, or ``None`` if absent."""
    exclusions = document.get("exclusions")
    if exclusions is None:
        return None
    return exclusions.get("patterns")


def reorder_exclusions(document: TOMLDocument, new_order: list[int]) -> None:
    """Rewrite ``[exclusions].patterns`` so its order matches ``new_order``.

    Mutates the existing array in place to preserve formatting; see
    :func:`reorder_rules` for the rationale.
    """
    arr = _exclusion_array(document)
    n = 0 if arr is None else len(arr)
    if sorted(new_order) != list(range(n)):
        raise ConfigEditError(
            f"reorder_exclusions: invalid permutation of {n} patterns: {new_order!r}"
        )
    if arr is None or n < 2:
        return
    snapshots = [arr[i] for i in range(n)]
    reordered = [snapshots[i] for i in new_order]
    for _ in range(n):
        del arr[0]
    for entry in reordered:
        arr.append(entry)


def delete_exclusion(document: TOMLDocument, index: int) -> None:
    """Drop the exclusion pattern at ``index`` in place."""
    arr = _exclusion_array(document)
    if arr is None or not 0 <= index < len(arr):
        raise ConfigEditError(
            f"delete_exclusion: index {index} out of range "
            f"(0..{(len(arr) - 1) if arr is not None else -1})"
        )
    del arr[index]
