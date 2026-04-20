"""Load ``config.toml`` from disk (or seed defaults).

Read path: stdlib :mod:`tomllib`, then :func:`schema.validate`, then — if the
document's schema version is older than current — the migration registry. The
migrated document is never written back automatically (see
``docs/02-state-format.md`` §Versioning and migration).

If the primary config is corrupt, we fall back to ``config.toml.bak`` (the
last known-good) and log loudly; we never overwrite the corrupt file until the
user has an intact config loaded.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from .. import paths
from . import migrations
from .defaults import DEFAULT_CONFIG_TOML
from .schema import CURRENT_SCHEMA_VERSION, Config, SchemaError, validate

log = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when the config cannot be loaded and no fallback succeeds."""


def _parse(path: Path) -> dict[str, object]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _load_and_validate(path: Path) -> Config:
    document = _parse(path)
    version = document.get("schema_version", CURRENT_SCHEMA_VERSION)
    if isinstance(version, int) and 1 <= version < CURRENT_SCHEMA_VERSION:
        document = migrations.migrate(document, version, CURRENT_SCHEMA_VERSION)
        document["schema_version"] = CURRENT_SCHEMA_VERSION
    return validate(document)


def _seed_defaults(path: Path) -> Config:
    paths.ensure_dir(path.parent)
    path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    log.info("wrote default config to %s", path)
    return validate(_parse(path))


def load_or_create(
    config_path: Path | None = None,
    backup_path: Path | None = None,
) -> Config:
    """Load the config at ``config_path``; seed defaults if absent.

    Falls back to ``backup_path`` if the primary file fails to parse or
    validate. Raises :class:`ConfigError` if neither succeeds.
    """
    primary = config_path if config_path is not None else paths.config_file()
    backup = backup_path if backup_path is not None else paths.config_backup_file()

    if not primary.exists():
        return _seed_defaults(primary)

    try:
        return _load_and_validate(primary)
    except (tomllib.TOMLDecodeError, SchemaError) as exc:
        log.error("config %s failed to load: %s", primary, exc)
        if backup.exists():
            log.warning("falling back to backup %s", backup)
            try:
                return _load_and_validate(backup)
            except (tomllib.TOMLDecodeError, SchemaError) as backup_exc:
                raise ConfigError(
                    f"both {primary} and {backup} failed to load: "
                    f"primary={exc}; backup={backup_exc}"
                ) from backup_exc
        raise ConfigError(f"{primary} failed to load and no backup exists: {exc}") from exc
