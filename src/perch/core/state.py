"""In-memory application state.

Holds the loaded config, and only that. Backend wiring lives in
:mod:`perch.app`, live window tracking in :class:`perch.core.reducer.Reducer`
and remembered geometry in :class:`perch.core.state_store.StateStore`; each
owns its own state rather than parking it here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.schema import Config


@dataclass
class AppState:
    config: Config
