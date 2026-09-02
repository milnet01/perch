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
from .schema import (
    CURRENT_SCHEMA_VERSION,
    Config,
    SchemaError,
    SchemaTooNewError,
    validate,
)
from .writer import atomic_write

log = logging.getLogger(__name__)

# Everything that means "this file is unusable" rather than "this file is from
# the future". tomllib decodes the bytes itself and catches only AttributeError
# doing it, so a single non-UTF-8 byte arrives as UnicodeDecodeError; TOML v1.0.0
# requires a UTF-8 document, which makes that a parse failure like any other.
_UNUSABLE = (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError, SchemaError)


class ConfigError(Exception):
    """Raised when the config cannot be loaded and no fallback succeeds."""


def _parse(path: Path) -> dict[str, object]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _migrate_and_validate(document: dict[str, object], source: str) -> Config:
    # Absent means v1, never "whatever this build is": schema_version is not a
    # required key, so defaulting to current would make every unversioned file
    # skip its migrations the day CURRENT_SCHEMA_VERSION moves past 1.
    version = document.get("schema_version", 1)
    if (
        isinstance(version, int)
        and not isinstance(version, bool)
        and 1 <= version < CURRENT_SCHEMA_VERSION
    ):
        try:
            document = migrations.migrate(
                document, version, CURRENT_SCHEMA_VERSION
            )
        except migrations.MigrationError as exc:
            # docs/02-state-format.md §Schema reference: a failing migration
            # surfaces as a ConfigError with a pinpoint line, not a traceback.
            raise ConfigError(f"{source}: {exc}") from exc
        document["schema_version"] = CURRENT_SCHEMA_VERSION
    return validate(document)


def _load_and_validate(path: Path) -> Config:
    return _migrate_and_validate(_parse(path), str(path))


def validate_text(text: str, source: str) -> Config:
    """Validate a config document already held in memory.

    For a caller that has the exact bytes it intends to write — the
    dialog's import path — and must validate *those*. Validating the file
    instead reads it a second time, so a file that changed between the
    two reads is written without ever having been checked, against
    ``docs/security-standards.md``'s claim that every loaded document is
    validated. ``source`` only names the document in error messages.
    """
    return _migrate_and_validate(tomllib.loads(text), source)


def _seed_defaults(path: Path) -> Config:
    paths.ensure_dir(path.parent)
    # docs/02-state-format.md §Atomic writes: "Every disk write follows the same
    # recipe". An interrupted plain write_text leaves a truncated config.toml
    # with no .bak beside it, which is the one state nothing can recover from.
    atomic_write(path, DEFAULT_CONFIG_TOML)
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
    # Derive the backup from the primary whenever the caller named one.
    # Defaulting to paths.config_backup_file() independently pairs an explicit
    # primary with the REAL user's ~/.config/perch/config.toml.bak, so a caller
    # pointing at some other directory could read a backup belonging to a
    # different config entirely.
    if backup_path is not None:
        backup = backup_path
    elif config_path is not None:
        backup = primary.with_suffix(primary.suffix + ".bak")
    else:
        backup = paths.config_backup_file()

    if not primary.exists():
        if backup.exists():
            # The atomic recipe's own crash window puts the filesystem in
            # exactly this state: config.toml already rotated to .bak, tmp not
            # yet renamed into place. Seeding defaults here would then rotate
            # the user's whole config away on the next save.
            log.warning(
                "config %s is missing but %s exists; recovering from backup",
                primary,
                backup,
            )
            try:
                return _load_and_validate(backup)
            except _UNUSABLE as backup_exc:
                raise ConfigError(
                    f"{primary} is missing and {backup} failed to load: {backup_exc}"
                ) from backup_exc
        return _seed_defaults(primary)

    try:
        return _load_and_validate(primary)
    except SchemaTooNewError as exc:
        # Refused, not guessed at. Must precede the _UNUSABLE arm below, which
        # catches its base class and would send us to an older backup.
        log.error("config %s is from a newer Perch: %s", primary, exc)
        raise ConfigError(f"{primary}: {exc}") from exc
    except _UNUSABLE as exc:
        log.error("config %s failed to load: %s", primary, exc)
        if backup.exists():
            log.warning("falling back to backup %s", backup)
            try:
                return _load_and_validate(backup)
            except _UNUSABLE as backup_exc:
                raise ConfigError(
                    f"both {primary} and {backup} failed to load: "
                    f"primary={exc}; backup={backup_exc}"
                ) from backup_exc
        raise ConfigError(f"{primary} failed to load and no backup exists: {exc}") from exc
