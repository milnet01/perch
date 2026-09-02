"""Config schema (authoritative for ``config.toml``).

Shape mirrors ``docs/02-state-format.md`` §``config.toml``. Validation is
layered — this module handles the top-level skeleton and delegates
per-domain parsing to the owning core module. As of M2.c every section
(``[exclusions]``, ``[snaps]``, ``[[rules]]``, ``[layouts]``, and
``[[profiles]]``) is typed; nothing is carried as an opaque
``dict[str, Any]`` out of this module.

Invariants enforced here:

* refuse a higher-than-known ``schema_version`` (forward-compat guard);
* reject an unknown ``general.theme`` value;
* reject non-boolean general toggles.

Domain errors from the core parsers are re-raised as :class:`SchemaError`
so callers have a single exception class to catch at the config boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from perch.core.exclusions import (
    ExclusionValidationError,
    parse_user_exclusions,
)
from perch.core.layouts import Layout, LayoutValidationError, parse_layouts
from perch.core.matching import MatchPattern
from perch.core.profiles import Profile, ProfileValidationError, parse_profiles
from perch.core.rules import Rule, RuleValidationError, parse_rules
from perch.core.snaps import SnapPreset, SnapValidationError, parse_snaps

CURRENT_SCHEMA_VERSION = 1
VALID_THEMES: tuple[str, ...] = ("auto", "light", "dark")

Theme = Literal["auto", "light", "dark"]


class SchemaError(ValueError):
    """Raised when a config document does not match the schema."""


class SchemaTooNewError(SchemaError):
    """Raised when ``schema_version`` is higher than this build understands.

    Separate from a plain :class:`SchemaError` because the two demand opposite
    responses. ``docs/02-state-format.md`` §Versioning and migration says a
    too-new document is *refused*, and §Schema reference says it surfaces as a
    ``ConfigError`` with a non-zero exit — where a corrupt document falls back
    to ``config.toml.bak``. Falling back here would load an older config and
    then rotate the newer one away on the next save.
    """


@dataclass
class GeneralSettings:
    start_at_login: bool = True
    restore_on_open: bool = True
    notify_on_restore: bool = False
    theme: Theme = "auto"
    # Not user-facing in the config dialog: the first-run wizard sets it on
    # every exit so it never reappears unprompted. The default serves both
    # audiences — a freshly-seeded config gets False, and an upgrading
    # user's config simply lacks the key, which parses as False too.
    onboarding_completed: bool = False


@dataclass
class Config:
    schema_version: int = CURRENT_SCHEMA_VERSION
    general: GeneralSettings = field(default_factory=GeneralSettings)
    exclusions: list[MatchPattern] = field(default_factory=list)
    snaps: dict[str, SnapPreset] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    layouts: dict[str, Layout] = field(default_factory=dict)
    profiles: list[Profile] = field(default_factory=list)


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

    for key in (
        "start_at_login",
        "restore_on_open",
        "notify_on_restore",
        "onboarding_completed",
    ):
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
        "onboarding_completed",
        "theme",
    }
    if unknown:
        raise SchemaError(f"[general] has unknown keys: {sorted(unknown)!r}")
    return out


def _parse_exclusions_raw(raw: Any) -> list[dict[str, Any]]:
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
    unknown = set(raw.keys()) - {"patterns"}
    if unknown:
        raise SchemaError(f"[exclusions] has unknown keys: {sorted(unknown)!r}")
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


KNOWN_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "general",
        "exclusions",
        "snaps",
        "rules",
        "layouts",
        "profiles",
    }
)


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

    unknown_tables = set(document) - KNOWN_TOP_LEVEL_KEYS
    if unknown_tables:
        # docs/07-rules-engine.md §Validation: Perch does not silently drop
        # bad rules. A typo'd ``[[rule]]`` is a whole section of the user's
        # config going unread, and the unknown-key checks inside [general]
        # and [exclusions] would already have caught it one level down.
        raise SchemaError(
            f"unknown top-level keys {sorted(unknown_tables)!r} "
            f"(known: {sorted(KNOWN_TOP_LEVEL_KEYS)})"
        )

    version = document.get("schema_version", CURRENT_SCHEMA_VERSION)
    # ``bool`` is an ``int`` in Python, so the isinstance check alone accepts
    # ``schema_version = true`` and then compares it as 1.
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaError(
            f"schema_version must be an integer (got {type(version).__name__})"
        )
    if version > CURRENT_SCHEMA_VERSION:
        raise SchemaTooNewError(
            f"schema_version {version} is newer than this Perch "
            f"understands ({CURRENT_SCHEMA_VERSION}); upgrade Perch or "
            "roll back the config"
        )
    if version < 1:
        raise SchemaError(f"schema_version must be >= 1 (got {version})")

    raw_exclusions = _parse_exclusions_raw(document.get("exclusions"))
    raw_snaps = _parse_table_of_tables("snaps", document.get("snaps"))
    raw_rules = _parse_array_of_tables("rules", document.get("rules"))
    raw_layouts = _parse_table_of_tables("layouts", document.get("layouts"))
    raw_profiles = _parse_array_of_tables("profiles", document.get("profiles"))

    try:
        exclusions = parse_user_exclusions(raw_exclusions)
    except ExclusionValidationError as exc:
        raise SchemaError(str(exc)) from exc
    try:
        snaps = parse_snaps(raw_snaps)
    except SnapValidationError as exc:
        raise SchemaError(str(exc)) from exc
    try:
        rules = parse_rules(raw_rules)
    except RuleValidationError as exc:
        raise SchemaError(str(exc)) from exc
    try:
        layouts = parse_layouts(raw_layouts)
    except LayoutValidationError as exc:
        raise SchemaError(str(exc)) from exc
    try:
        profiles = parse_profiles(raw_profiles)
    except ProfileValidationError as exc:
        raise SchemaError(str(exc)) from exc

    # Cross-table check: neither parser can see the other's table, and
    # ``docs/09-layouts-profiles.md`` §Activation applies a profile's
    # ``default_layout`` on activation — a name with no layout behind it
    # would otherwise surface only as a log line at topology-change time.
    for profile in profiles:
        if profile.default_layout is not None and profile.default_layout not in layouts:
            raise SchemaError(
                f"[[profiles]] {profile.name!r}: default_layout "
                f"{profile.default_layout!r} is not a declared layout "
                f"(known: {sorted(layouts)})"
            )

    return Config(
        schema_version=version,
        general=_parse_general(document.get("general")),
        exclusions=exclusions,
        snaps=snaps,
        rules=rules,
        layouts=layouts,
        profiles=profiles,
    )
