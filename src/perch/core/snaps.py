"""Snap presets — named geometries with optional global hotkeys.

Spec in ``docs/02-state-format.md`` §``[snaps]``. Built-in presets live in
:data:`perch.core.actions.BUILTIN_PRESETS`; user-defined presets parsed
here extend (and can shadow) those names at apply time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import (
    ActionValidationError,
    GeometryExpr,
    MonitorSpec,
    parse_geometry_dict,
    parse_monitor,
)


class SnapValidationError(ValueError):
    """Raised when a ``[snaps."<name>"]`` table is malformed."""


@dataclass(frozen=True, slots=True)
class SnapPreset:
    name: str
    geometry: GeometryExpr
    monitor: MonitorSpec | None = None
    hotkey: str | None = None


def parse_snaps(raw: dict[str, dict[str, Any]]) -> dict[str, SnapPreset]:
    """Convert the raw ``[snaps]`` table-of-tables into typed presets."""
    out: dict[str, SnapPreset] = {}
    for name, entry in raw.items():
        prefix = f"[snaps.{name!r}]"
        if not isinstance(entry, dict):
            raise SnapValidationError(f"{prefix} must be a table")
        if not name:
            raise SnapValidationError("[snaps.<name>] key must not be empty")

        known = {"geometry", "hotkey"}
        unknown = set(entry.keys()) - known
        if unknown:
            raise SnapValidationError(
                f"{prefix}: unknown keys {sorted(unknown)!r}"
            )
        if "geometry" not in entry:
            raise SnapValidationError(f"{prefix}: missing 'geometry'")

        geom_raw = entry["geometry"]
        if not isinstance(geom_raw, dict):
            raise SnapValidationError(
                f"{prefix}.geometry must be a table "
                "(a snap preset is a concrete geometry, not a preset reference)"
            )
        # Peel monitor off the geometry table; snap presets keep it as a
        # first-class attribute so the UI can display "preset X targets
        # monitor Y".
        geom_dict = dict(geom_raw)
        monitor = geom_dict.pop("monitor", None)
        try:
            monitor_spec = parse_monitor(monitor, f"{prefix}.geometry.monitor")
            geometry = parse_geometry_dict(geom_dict, f"{prefix}.geometry")
        except ActionValidationError as exc:
            raise SnapValidationError(str(exc)) from exc

        hotkey = entry.get("hotkey")
        if hotkey is not None and not isinstance(hotkey, str):
            raise SnapValidationError(
                f"{prefix}.hotkey must be a string "
                f"(got {type(hotkey).__name__})"
            )
        if hotkey == "":
            raise SnapValidationError(f"{prefix}.hotkey must not be empty")

        out[name] = SnapPreset(
            name=name,
            geometry=geometry,
            monitor=monitor_spec,
            hotkey=hotkey,
        )
    return out
