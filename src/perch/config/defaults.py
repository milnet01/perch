"""Default config emitted on first run.

Must parse cleanly under :mod:`perch.config.schema.validate` and must preserve
the explanatory comments below when round-tripped through ``tomlkit`` — see
the round-trip fixture test in ``tests/test_config_roundtrip.py``.
"""

from __future__ import annotations

from .schema import CURRENT_SCHEMA_VERSION

DEFAULT_CONFIG_TOML = f"""\
# Perch config. Hand-editable; Perch preserves your comments when it writes.
# Full reference: https://github.com/milnet01/perch/blob/main/docs/02-state-format.md

schema_version = {CURRENT_SCHEMA_VERSION}

[general]
start_at_login    = true
restore_on_open   = true   # apply remembered geometry when a window reappears
notify_on_restore = false
theme             = "auto" # "auto" | "light" | "dark"

[exclusions]
# Windows matching any of these patterns are never managed by Perch.
patterns = []

# ─── Snap presets ─────────────────────────────────────────────────────────
# Built-in snaps (maximize, center, left-half, top-right-quarter, …) are
# always available. Add custom ones here.
[snaps]

# ─── Rules ────────────────────────────────────────────────────────────────
# Evaluated top-to-bottom; first match wins. See docs/07-rules-engine.md.
# Example:
#   [[rules]]
#   name  = "Firefox on external"
#   match = {{ app_id = "firefox" }}
#   apply = {{ geometry = "maximize", monitor = "HDMI-1" }}

# ─── Layouts ──────────────────────────────────────────────────────────────
# A named set of (match, target) pairs. See docs/09-layouts-profiles.md.

# ─── Profiles ─────────────────────────────────────────────────────────────
# A profile activates automatically when the monitor topology matches.
"""
