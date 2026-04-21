"""CLI entry point.

``perch --version`` prints the version and exits. ``perch --check-config``
loads the config (creating defaults on a fresh XDG dir) and exits before
touching Qt — used for packaging self-tests and CI smoke.

Otherwise we configure logging, install the Qt→Python log bridge, construct
the ``QApplication`` in this sync wrapper (qasync 0.28 asserts on
``QApplication.instance() is not None`` before the coroutine runs — see
``docs/01-architecture.md`` §Event loop bootstrap), and drive
:func:`perch.app.main` via ``asyncio.run(..., loop_factory=QEventLoop)``.

Structural / user-visible config errors produce a non-zero exit and a
pinpoint message in both the log file and stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from . import __version__
from .config import ConfigError, load_or_create
from .logging_setup import configure_logging, install_qt_bridge

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="perch",
        description="Persistent, compositor-aware window geometry manager.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"perch {__version__}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging (equivalent to PERCH_DEBUG=1).",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help=(
            "Load config (creating defaults on a fresh XDG dir) then exit. "
            "Used by packaging self-tests and CI smoke."
        ),
    )
    return parser


def cli(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``[project.scripts]``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.debug:
        os.environ["PERCH_DEBUG"] = "1"

    configure_logging()

    if args.check_config:
        try:
            load_or_create()
        except ConfigError as exc:
            log.error("config error: %s", exc)
            print(f"perch: config error: {exc}", file=sys.stderr)
            return 1
        log.info("check-config: ok")
        return 0

    install_qt_bridge()

    # Qt / qasync imports are deferred so --version and --check-config
    # work on systems without PySide6 at import time (doc-only or
    # config-inspection use-cases) and so the offscreen bootstrap can
    # be applied before anything tries to open a display.
    from PySide6.QtWidgets import QApplication
    from qasync import QEventLoop

    from .app import allow_headless_bootstrap
    from .app import main as app_main
    from .ui.sni_probe import is_gnome_wayland, sni_host_available

    allow_headless_bootstrap()

    # qasync >=0.28 requires a QApplication to exist *before* QEventLoop is
    # instantiated (the factory asserts on it). Holding the reference keeps
    # the C++ object alive for the duration of the run.
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    # The SNI probe uses sdbus's sync API and must run *before* the
    # asyncio loop starts — sdbus refuses to run sync reads with an
    # asyncio loop attached ("Used sync __get__ method in async
    # environment"). Pass the result into ``main()`` so the async body
    # only sees a pure bool.
    have_host = sni_host_available()
    gnome_wayland = is_gnome_wayland()

    try:
        return asyncio.run(
            app_main(have_sni_host=have_host, gnome_wayland=gnome_wayland),
            loop_factory=QEventLoop,
        )
    except ConfigError as exc:
        log.error("config error: %s", exc)
        print(f"perch: config error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli())
