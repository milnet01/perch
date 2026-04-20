"""Schema-migration registry.

Each migration is a pure ``dict -> dict`` transforming schema version ``N`` to
``N + 1``. The registry is wired but empty in M1 (current schema is version 1).
Future migrations land as ``v1_to_v2.py`` etc. and are registered below.

Applied only in memory; the migrated document is **not written back** to disk
until the user edits something (keeps dotfile repos stable across upgrades —
see ``docs/02-state-format.md`` §Versioning and migration).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Migration = Callable[[dict[str, Any]], dict[str, Any]]

MIGRATIONS: dict[int, Migration] = {}


def migrate(document: dict[str, Any], from_version: int, to_version: int) -> dict[str, Any]:
    """Apply the registered migrations in order, returning the upgraded doc."""
    current = document
    for v in range(from_version, to_version):
        step = MIGRATIONS.get(v)
        if step is None:
            raise KeyError(f"no migration registered for schema v{v} -> v{v + 1}")
        current = step(current)
    return current
