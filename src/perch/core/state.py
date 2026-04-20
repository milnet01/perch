"""In-memory application state.

M1 scope: holds the loaded config. Backend wiring, managed-windows tracking,
and ``state.json`` persistence land in M2 per ``docs/11-roadmap.md``. Fields
for those arrive with the code that populates them; we don't ship empty
placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.schema import Config


@dataclass
class AppState:
    config: Config
