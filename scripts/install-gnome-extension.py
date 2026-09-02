#!/usr/bin/env python3
"""Install Perch's bundled GNOME Shell extension for the current user.

The dev path of the three documented in ``docs/06-backend-stubs.md``
§"Flatpak Perch cannot install the extension". The recommended paths are a
distro package or Extension Manager; this one exists so a developer running
Perch from a checkout does not have to copy files by hand.

Copies :data:`perch.backend.mutter.BUNDLED_EXTENSION_DIR` into
``$XDG_DATA_HOME/gnome-shell/extensions/<uuid>/`` and prints the two steps
that have to happen outside a script: enabling the extension, and restarting
the Shell.

Invoke from anywhere::

    python3 scripts/install-gnome-extension.py
    python3 scripts/install-gnome-extension.py --force   # replace an install

It deliberately does not run ``gnome-extensions enable`` for you. Enabling
an extension is a change to the user's session, and a script that both
installs and enables gives a failed enable no separate diagnosis.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from perch.backend.mutter import (
    BUNDLED_EXTENSION_DIR,
    EXTENSION_UUID,
)


def extensions_dir() -> Path:
    """The per-user extension directory GNOME Shell reads."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "gnome-shell" / "extensions"


def install(*, force: bool) -> int:
    if not BUNDLED_EXTENSION_DIR.is_dir():
        print(
            f"error: bundled extension not found at {BUNDLED_EXTENSION_DIR}",
            file=sys.stderr,
        )
        return 1

    target = extensions_dir() / EXTENSION_UUID
    if target.exists() and not force:
        print(
            f"error: {target} already exists. Pass --force to replace it.",
            file=sys.stderr,
        )
        return 1

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BUNDLED_EXTENSION_DIR, target)

    print(f"installed {EXTENSION_UUID} to {target}")
    print()
    print("Two steps remain, and neither is a script's to take:")
    print(f"  1. gnome-extensions enable {EXTENSION_UUID}")
    print("  2. Log out and back in (Wayland cannot reload the Shell).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing install of the same UUID",
    )
    args = parser.parse_args(argv)
    return install(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
