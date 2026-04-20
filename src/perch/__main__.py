"""CLI entry point.

``perch --version`` prints the version and exits. Otherwise we configure
logging, install the Qt→Python log bridge, and drive :func:`perch.app.main`
via the canonical ``asyncio.run(main(), loop_factory=QEventLoop)`` pattern
(see ``docs/01-architecture.md`` §Event loop bootstrap).

Structural / user-visible config errors produce a non-zero exit and a
pinpoint message in both the log file and stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from . import __version__
from .app import main as app_main
from .config import ConfigError
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
    return parser


def cli(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``[project.scripts]``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.debug:
        os.environ["PERCH_DEBUG"] = "1"

    configure_logging()
    install_qt_bridge()

    # qasync >=0.28 requires a QApplication to exist *before* QEventLoop is
    # instantiated (the factory asserts on it). Holding the reference keeps
    # the C++ object alive for the duration of the run.
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    try:
        return asyncio.run(app_main(), loop_factory=QEventLoop)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        print(f"perch: config error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli())
