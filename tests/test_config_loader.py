"""Loader behaviour: seeding, fallback to backup, migration dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from perch.config import ConfigError, load_or_create
from perch.config import migrations as migrations_mod


def test_seeds_default_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    config = load_or_create(config_path=target)
    assert target.exists()
    assert config.schema_version >= 1
    assert config.general.theme == "auto"


def test_malformed_primary_falls_back_to_backup(tmp_path: Path) -> None:
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_text("not = valid [ toml", encoding="utf-8")
    backup.write_text('schema_version = 1\n[general]\ntheme = "light"\n', encoding="utf-8")

    config = load_or_create(config_path=primary, backup_path=backup)
    assert config.general.theme == "light"


def test_no_backup_raises_config_error(tmp_path: Path) -> None:
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_text("not = valid [ toml", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_or_create(config_path=primary, backup_path=backup)


def test_corrupt_primary_and_corrupt_backup_raises(tmp_path: Path) -> None:
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_text("not = valid [ toml", encoding="utf-8")
    backup.write_text("also not = [ valid", encoding="utf-8")

    with pytest.raises(ConfigError, match="both"):
        load_or_create(config_path=primary, backup_path=backup)


def test_schema_error_falls_back_to_backup(tmp_path: Path) -> None:
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_text('schema_version = 1\n[general]\ntheme = "sepia"\n', encoding="utf-8")
    backup.write_text('schema_version = 1\n[general]\ntheme = "auto"\n', encoding="utf-8")

    config = load_or_create(config_path=primary, backup_path=backup)
    assert config.general.theme == "auto"


def test_missing_migration_raises_keyerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """The migration registry is empty in M1; dispatching a bogus range explodes loudly."""
    monkeypatch.setattr(migrations_mod, "MIGRATIONS", {})
    with pytest.raises(KeyError):
        migrations_mod.migrate({}, from_version=1, to_version=2)


def test_migration_registry_empty_at_current_version() -> None:
    """Guard: when we bump CURRENT_SCHEMA_VERSION, the migration list must grow too."""
    from perch.config.schema import CURRENT_SCHEMA_VERSION

    expected_migrations = CURRENT_SCHEMA_VERSION - 1
    assert len(migrations_mod.MIGRATIONS) == expected_migrations, (
        f"schema is at v{CURRENT_SCHEMA_VERSION}, so {expected_migrations} migrations "
        f"must be registered; found {len(migrations_mod.MIGRATIONS)}"
    )


def test_missing_primary_recovers_from_backup(tmp_path: Path) -> None:
    """A missing primary beside an intact backup is recovered, not reseeded.

    The atomic recipe's own crash window leaves exactly this state — the old
    config already rotated to .bak, the tmp file not yet renamed into place.
    Seeding defaults there discards the user's whole config, and the next save
    rotates the surviving backup away.
    """
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    backup.write_text(
        'schema_version = 1\n[general]\ntheme = "light"\n', encoding="utf-8"
    )

    config = load_or_create(config_path=primary, backup_path=backup)
    assert config.general.theme == "light"


def test_future_schema_refused_without_backup_fallback(tmp_path: Path) -> None:
    """A too-new config raises ConfigError instead of loading the backup.

    docs/02-state-format.md §Schema reference: it "surfaces as a ConfigError
    that produces a non-zero exit". Falling back would load an older config
    and then rotate the newer one away on the next save.
    """
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_text("schema_version = 99\n", encoding="utf-8")
    backup.write_text(
        'schema_version = 1\n[general]\ntheme = "light"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="newer than this Perch"):
        load_or_create(config_path=primary, backup_path=backup)


def test_non_utf8_primary_falls_back_to_backup(tmp_path: Path) -> None:
    """A non-UTF-8 byte is a parse failure, not an uncaught traceback.

    TOML v1.0.0 requires a UTF-8 document; tomllib surfaces the breach as
    UnicodeDecodeError, which was outside the caught set.
    """
    primary = tmp_path / "config.toml"
    backup = tmp_path / "config.toml.bak"
    primary.write_bytes(b'schema_version = 1\n[general]\ntheme = "\xff\xfe"\n')
    backup.write_text(
        'schema_version = 1\n[general]\ntheme = "light"\n', encoding="utf-8"
    )

    config = load_or_create(config_path=primary, backup_path=backup)
    assert config.general.theme == "light"
