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
    path.mkdir(parents=True, exist_ok=True)
    return path
