"""XDG path resolution for Perch.

Resolution order follows the XDG Base Directory spec: honour the env var if set
and non-empty, otherwise fall back to the spec default under ``$HOME``. Paths are
computed on each call rather than cached at import time so tests can manipulate
``$XDG_*_HOME`` via ``monkeypatch.setenv`` without reloading the module.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "perch"


def is_flatpak() -> bool:
    """Return True when Perch is running inside a Flatpak sandbox.

    ``/.flatpak-info`` is mounted read-only into every Flatpak sandbox and
    never appears on a host. ``FLATPAK_ID`` is a weaker signal (scripts
    unset it); the file is authoritative.

    It lives here because the answer changes how paths resolve: inside the
    sandbox ``XDG_DATA_HOME`` and friends point at ``~/.var/app/<id>/``,
    which host processes such as KWin cannot read.
    """
    return Path("/.flatpak-info").is_file()


def _xdg_dir(env_var: str, fallback_relative: str) -> Path:
    raw = os.environ.get(env_var)
    if raw:
        return Path(raw)
    return Path.home() / fallback_relative


def config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME


def state_dir() -> Path:
    return _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_NAME


def cache_dir() -> Path:
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.toml"


def config_backup_file() -> Path:
    return config_dir() / "config.toml.bak"


def log_file() -> Path:
    return state_dir() / "perch.log"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and parents) and make it owner-only.

    ``0700`` rather than the umask default. Perch's config and state name
    the applications the user runs and where they put their windows; at
    ``0755`` every other account on a shared machine can read that. The
    mode is re-applied to an existing directory too, since an install
    predating this was created with the umask default.
    """
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path
