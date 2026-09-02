"""Config subsystem — read, validate, write.

The authoritative schema lives in :mod:`perch.config.schema`. Reads go through
stdlib :mod:`tomllib` via :mod:`perch.config.loader`; writes go through
``tomlkit`` via :mod:`perch.config.writer` so user-authored comments survive
round-trips — see ``docs/02-state-format.md`` §Read / write split.
"""

from .loader import ConfigError, load_or_create, validate_text
from .schema import CURRENT_SCHEMA_VERSION, Config

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Config",
    "ConfigError",
    "load_or_create",
    "validate_text",
]
