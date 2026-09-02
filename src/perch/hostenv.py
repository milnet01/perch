"""Environment for host programs Perch spawns.

The AppImage entry point (``packaging/appimage/entrypoint.sh``) puts the
bundled AlmaLinux 8 libraries on ``LD_LIBRARY_PATH`` so the Qt ``xcb`` platform
plugin can be dlopened. That variable is inherited by every child process, so a
*host* program Perch launches -- a browser, a file manager, a compositor CLI --
would resolve its own libraries against the bundle's older copies. The classic
symptom is that opening a link crashes the browser.

The entry point records the host's original value in
``PERCH_HOST_LD_LIBRARY_PATH`` before overwriting it; the helpers here put it
back. Outside an AppImage that variable is unset, nothing was overwritten, and
both helpers are no-ops.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

#: Set by the AppImage entry point to the LD_LIBRARY_PATH Perch inherited.
HOST_PATH_VAR = "PERCH_HOST_LD_LIBRARY_PATH"


def host_env() -> dict[str, str] | None:
    """The environment to spawn a host program with, or ``None`` to inherit.

    ``None`` means there is nothing to undo -- pass it straight to ``env=`` and
    the child inherits ours, which is the correct behaviour outside an AppImage.
    """
    if HOST_PATH_VAR not in os.environ:
        return None
    env = dict(os.environ)
    original = env.pop(HOST_PATH_VAR)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


@contextmanager
def host_environment() -> Iterator[None]:
    """Apply :func:`host_env` to ``os.environ`` for the duration of the block.

    For spawns whose environment we cannot set directly -- Qt's
    ``QDesktopServices.openUrl`` shells out itself. Qt reads the process
    environment at spawn time, so restoring it around the call is what reaches
    the child. Everything already loaded stays loaded; only a *new* process
    sees the difference.
    """
    env = host_env()
    if env is None:
        yield
        return
    saved = os.environ.get("LD_LIBRARY_PATH")
    if "LD_LIBRARY_PATH" in env:
        os.environ["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH"]
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = saved
