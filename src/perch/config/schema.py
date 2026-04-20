"""Config schema (authoritative for ``config.toml``).

Shape mirrors ``docs/02-state-format.md`` §``config.toml``. M1 validates the
top-level skeleton (``schema_version``, ``[general]``, ``[exclusions]``) and
accepts ``rules`` / ``layouts`` / ``profiles`` / ``snaps`` as opaque tables —
the rules engine lands in M2 and will tighten validation then. The important
M1 invariants are here:

* refuse a higher-than-known ``schema_version`` (forward-compat guard);
* reject an unknown ``general.theme`` value;
* reject non-boolean general toggles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

CURRENT_SCHEMA_VERSION = 1
VALID_THEMES: tuple[str, ...] = ("auto", "light", "dark")

Theme = Literal["auto", "light", "dark"]


class SchemaError(ValueError):
    """Raised when a config document does not match the schema."""


@dataclass
class GeneralSettings:
    start_at_login: bool = True
    restore_on_open: bool = True
    notify_on_restore: bool = False
    theme: Theme = "auto"


@dataclass
class Config:
    schema_version: int = CURRENT_SCHEMA_VERSION
    general: GeneralSettings = field(default_factory=GeneralSettings)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    snaps: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    layouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    profiles: list[dict[str, Any]] = field(default_factory=list)


def _require_bool(section: str, key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise SchemaError(f"[{section}].{key} must be a boolean (got {type(value).__name__})")
    return value


def _parse_general(raw: Any) -> GeneralSettings:
    if raw is None:
        return GeneralSettings()
    if not isinstance(raw, dict):
        raise SchemaError("[general] must be a table")

    defaults = GeneralSettings()
    out = GeneralSettings()

    for key in ("start_at_login", "restore_on_open", "notify_on_restore"):
        if key in raw:
            setattr(out, key, _require_bool("general", key, raw[key]))
        else:
            setattr(out, key, getattr(defaults, key))

    theme = raw.get("theme", defaults.theme)
    if theme not in VALID_THEMES:
        raise SchemaError(
            f"[general].theme must be one of {VALID_THEMES!r} (got {theme!r})"
        )
    out.theme = cast(Theme, theme)

    unknown = set(raw.keys()) - {
        "start_at_login",
        "restore_on_open",
        "notify_on_restore",
        "theme",
    }
    if unknown:
        raise SchemaError(f"[general] has unknown keys: {sorted(unknown)!r}")
    return out


def _parse_exclusions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise SchemaError("[exclusions] must be a table")
    patterns = raw.get("patterns", [])
    if not isinstance(patterns, list):
        raise SchemaError("[exclusions].patterns must be an array of tables")
    for i, entry in enumerate(patterns):
        if not isinstance(entry, dict):
            raise SchemaError(f"[exclusions].patterns[{i}] must be a table")
    return [dict(entry) for entry in patterns]


def _parse_table_of_tables(name: str, raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SchemaError(f"[{name}] must be a table of tables")
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            raise SchemaError(f"[{name}.{key}] must be a table")
        out[key] = dict(value)
    return out


def _parse_array_of_tables(name: str, raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SchemaError(f"[[{name}]] must be an array of tables")
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SchemaError(f"[[{name}]][{i}] must be a table")
    return [dict(entry) for entry in raw]


def validate(document: dict[str, Any]) -> Config:
    """Validate a parsed TOML document and return a :class:`Config`.

    Raises :class:`SchemaError` with a pinpoint message on any violation.
    """
    if not isinstance(document, dict):
        raise SchemaError("top-level config must be a table")

    version = document.get("schema_version", CURRENT_SCHEMA_VERSION)
    if not isinstance(version, int):
        raise SchemaError(
            f"schema_version must be an integer (got {type(version).__name__})"
        )
    if version > CURRENT_SCHEMA_VERSION:
        raise SchemaError(
            f"schema_version {version} is newer than this Perch "
            f"understands ({CURRENT_SCHEMA_VERSION}); upgrade Perch or "
            "roll back the config"
        )
    if version < 1:
        raise SchemaError(f"schema_version must be >= 1 (got {version})")

    return Config(
        schema_version=version,
        general=_parse_general(document.get("general")),
        exclusions=_parse_exclusions(document.get("exclusions")),
        snaps=_parse_table_of_tables("snaps", document.get("snaps")),
        rules=_parse_array_of_tables("rules", document.get("rules")),
        layouts=_parse_table_of_tables("layouts", document.get("layouts")),
        profiles=_parse_array_of_tables("profiles", document.get("profiles")),
    )
