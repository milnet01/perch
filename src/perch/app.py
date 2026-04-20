"""Top-level ``main()`` coroutine.

Implements the canonical event-loop bootstrap from
``docs/01-architecture.md`` §Event loop bootstrap — ``QApplication`` inside
``main()``, ``aboutToQuit → asyncio.Event`` handshake, ``await close_event``
as the idle point. M1 has no backend and no tray: the coroutine loads config,
logs, and returns so the CLI can exit cleanly.
"""

from __future__ import annotations

import logging

from .config import Config, load_or_create
from .core.state import AppState

log = logging.getLogger(__name__)


async def main() -> int:
    """Run Perch. Returns the process exit code.

    M1 scope: load config, log, exit cleanly. The canonical bootstrap shape
    (``async`` main driven by ``asyncio.run(..., loop_factory=QEventLoop)``
    with the ``QApplication`` constructed by the CLI before the loop factory
    runs — see ``docs/01-architecture.md`` §Event loop bootstrap) is fixed
    from M1 so the backend and tray land in M2/M3 without restructuring the
    entry point.
    """
    config: Config = load_or_create()
    state = AppState(config=config)
    log.info(
        "perch started: schema_version=%s, %d rules, %d layouts, %d profiles",
        state.config.schema_version,
        len(state.config.rules),
        len(state.config.layouts),
        len(state.config.profiles),
    )
    return 0
