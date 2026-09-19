"""One Perch per user session.

See ``docs/01-architecture.md`` §Why one process. A second copy would write
the same ``state.json`` and claim the same KWin bus name as the first, so it
refuses to start instead. The guard is a :class:`QLockFile`: Qt checks
whether the process holding a lock still exists, so a lock left behind by a
crash is recovered on the next start.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QLockFile

from . import paths


def lock_path() -> Path:
    """``$XDG_RUNTIME_DIR/perch.lock``, else the state directory's.

    The runtime directory is per-session and cleared at logout, which is
    the lifetime the lock describes.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and Path(runtime).is_absolute():
        return Path(runtime) / "perch.lock"
    return paths.state_dir() / "perch.lock"


def acquire_instance_lock() -> QLockFile | None:
    """Take the lock, or return ``None`` when another Perch holds it.

    The caller keeps the returned object for the life of the process;
    releasing it (or exiting) frees the lock.
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path))
    # Never treat a live holder's lock as stale by age: Perch runs for the
    # whole session. A dead holder is still detected by process check.
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock
    return None
