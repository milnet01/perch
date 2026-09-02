"""Apply actions — the "what to do once we match" vocabulary.

Spec in ``docs/02-state-format.md`` §Apply actions. An :class:`ApplyAction`
carries any combination of ``geometry``, ``snap``, ``monitor``, ``desktop``,
and ``maximized``; the reducer (M2.d) executes them in the fixed order
documented in ``docs/07-rules-engine.md`` §Apply order.

This module only parses and validates. Geometry resolution to pixels needs
live :class:`OutputInfo` data and therefore lives in the reducer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .matching import opt_str


class ActionValidationError(ValueError):
    """Raised when an ``apply = { ... }`` block is malformed or contradictory."""


# ── Geometry expressions ───────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class AbsoluteGeometry:
    """Pixel coordinates, clamped to the target monitor's work area."""

    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True, slots=True)
class PercentGeometry:
    """Percentages (0.0 to 1.0) of the target monitor's work area."""

    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float


@dataclass(frozen=True, slots=True)
class PresetGeometry:
    """Reference to a built-in or user-defined preset by name."""

    name: str


@dataclass(frozen=True, slots=True)
class CenterKeepSize:
    """Centering that preserves the window's current width and height.

    Unlike :class:`PercentGeometry` — which ignores the window's
    current dimensions — this expression centres the window inside
    the target monitor's work area without resizing it. The resolver
    reads ``window.geometry`` for ``w`` and ``h`` at apply time.
    """


GeometryExpr = AbsoluteGeometry | PercentGeometry | PresetGeometry | CenterKeepSize

# Built-in geometry presets. Most expand to :class:`PercentGeometry` against
# the target monitor's work area so they scale cleanly to any resolution.
# ``center-in-place`` expands to :class:`CenterKeepSize` which preserves the
# window's current dimensions.
#
# Aliases without the ``-quarter`` suffix (``top-left`` → ``top-left-quarter``)
# exist because the tray menu uses the short forms and rejecting them in the
# resolver would silently break the "Snap focused window" submenu. Duplicate
# entries (same value, different key) are fine — the resolver looks up by name.
BUILTIN_PRESETS: dict[str, GeometryExpr] = {
    "maximize": PercentGeometry(0.0, 0.0, 1.0, 1.0),
    "center": PercentGeometry(0.25, 0.25, 0.5, 0.5),
    "center-60": PercentGeometry(0.2, 0.2, 0.6, 0.6),
    "center-in-place": CenterKeepSize(),
    "left-half": PercentGeometry(0.0, 0.0, 0.5, 1.0),
    "right-half": PercentGeometry(0.5, 0.0, 0.5, 1.0),
    "top-half": PercentGeometry(0.0, 0.0, 1.0, 0.5),
    "bottom-half": PercentGeometry(0.0, 0.5, 1.0, 0.5),
    "top-left-quarter": PercentGeometry(0.0, 0.0, 0.5, 0.5),
    "top-right-quarter": PercentGeometry(0.5, 0.0, 0.5, 0.5),
    "bottom-left-quarter": PercentGeometry(0.0, 0.5, 0.5, 0.5),
    "bottom-right-quarter": PercentGeometry(0.5, 0.5, 0.5, 0.5),
    # Short aliases — the tray menu uses these.
    "top-left": PercentGeometry(0.0, 0.0, 0.5, 0.5),
    "top-right": PercentGeometry(0.5, 0.0, 0.5, 0.5),
    "bottom-left": PercentGeometry(0.0, 0.5, 0.5, 0.5),
    "bottom-right": PercentGeometry(0.5, 0.5, 0.5, 0.5),
}


# ── MonitorSpec ────────────────────────────────────────────────────────────
# ``monitor`` accepts, per ``docs/07-rules-engine.md`` §Geometry resolution:
#   * an output name as reported by the compositor ("DP-1")
#   * the strings "primary", "current"
#   * an integer profile-relative index (0, 1, …)
MonitorSpec = str | int

# Surfaced for UI / docs consumers. The parser otherwise accepts any non-empty
# string as a potential output name; resolving a keyword against live output
# info is the resolver's job.
MONITOR_KEYWORDS: frozenset[str] = frozenset({"primary", "current"})


# ── ApplyAction ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ApplyAction:
    geometry: GeometryExpr | None = None
    snap: str | None = None
    monitor: MonitorSpec | None = None
    desktop: int | str | None = None  # int index, "current", or "all"
    maximized: bool | None = None


# ── Parser ─────────────────────────────────────────────────────────────────
def parse_action(raw: Any, prefix: str) -> ApplyAction:
    """Validate and convert an ``apply = { ... }`` table.

    Rejections (mirroring ``docs/07-rules-engine.md`` §Validation):

    * ``apply`` block with no effect (none of geometry/snap/maximized/desktop
      set) — the rule would do nothing.
    * ``maximized = true`` combined with an explicit ``geometry`` or ``snap``
      (semantic contradiction; the two mechanisms fight for control of the
      window state).
    * ``monitor`` specified both inside a ``geometry`` dict and at the apply
      level, when the two disagree.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ActionValidationError(f"{prefix} must be a table")

    known = {"geometry", "snap", "monitor", "desktop", "maximized"}
    unknown = set(raw.keys()) - known
    if unknown:
        raise ActionValidationError(
            f"{prefix}: unknown keys {sorted(unknown)!r}"
        )

    apply_monitor = parse_monitor(raw.get("monitor"), f"{prefix}.monitor")
    geometry, geom_monitor = _parse_geometry(raw.get("geometry"), f"{prefix}.geometry")
    monitor = _resolve_monitor(apply_monitor, geom_monitor, prefix)

    snap = opt_str(raw, "snap", prefix, error=ActionValidationError)
    desktop = _parse_desktop(raw.get("desktop"), f"{prefix}.desktop")
    maximized = _opt_bool(raw, "maximized", prefix)

    if geometry is None and snap is None and maximized is None and desktop is None:
        raise ActionValidationError(
            f"{prefix} has no effect — set at least one of "
            f"'geometry', 'snap', 'maximized', 'desktop'"
        )
    if maximized is True and (geometry is not None or snap is not None):
        raise ActionValidationError(
            f"{prefix}: maximized=true together with explicit geometry/snap "
            f"is a contradiction (see docs/02-state-format.md §Apply actions)"
        )
    if geometry is not None and snap is not None:
        raise ActionValidationError(
            f"{prefix}: 'geometry' and 'snap' are mutually exclusive"
        )

    return ApplyAction(
        geometry=geometry,
        snap=snap,
        monitor=monitor,
        desktop=desktop,
        maximized=maximized,
    )


# ── Geometry parser ────────────────────────────────────────────────────────
_PERCENT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*%\s*$")


def parse_geometry_dict(raw: dict[str, Any], prefix: str) -> GeometryExpr:
    """Public helper: parse a geometry *table* (not a bare preset string).

    Used by snap presets and layout entries, which always express geometry
    as a table; apply actions go through :func:`parse_action` which calls
    the private ``_parse_geometry`` to also accept string preset names.
    """
    expr, _ = _parse_geometry_table(raw, prefix)
    return expr


def _parse_geometry(
    raw: Any, prefix: str
) -> tuple[GeometryExpr | None, MonitorSpec | None]:
    if raw is None:
        return None, None
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            raise ActionValidationError(f"{prefix} preset name must not be empty")
        return PresetGeometry(name=name), None
    if isinstance(raw, dict):
        return _parse_geometry_table(raw, prefix)
    raise ActionValidationError(
        f"{prefix} must be a preset name (string) or a table "
        f"(got {type(raw).__name__})"
    )


def _parse_geometry_table(
    raw: dict[str, Any], prefix: str
) -> tuple[GeometryExpr, MonitorSpec | None]:
    known = {"x", "y", "w", "h", "monitor"}
    unknown = set(raw.keys()) - known
    if unknown:
        raise ActionValidationError(
            f"{prefix}: unknown keys {sorted(unknown)!r}"
        )
    for key in ("x", "y", "w", "h"):
        if key not in raw:
            raise ActionValidationError(f"{prefix}: missing {key!r}")

    # Two valid shapes: all four values are ints (absolute) OR all four are
    # ``"N%"`` strings (percent). Mixing is an error — easier to reason
    # about downstream.
    values = {k: raw[k] for k in ("x", "y", "w", "h")}
    shape = _classify_geometry_values(values, prefix)

    if shape == "absolute":
        geom: GeometryExpr = AbsoluteGeometry(
            x=int(values["x"]),
            y=int(values["y"]),
            w=int(values["w"]),
            h=int(values["h"]),
        )
    else:
        geom = PercentGeometry(
            x_pct=_percent_to_float(values["x"], f"{prefix}.x"),
            y_pct=_percent_to_float(values["y"], f"{prefix}.y"),
            w_pct=_percent_to_float(values["w"], f"{prefix}.w"),
            h_pct=_percent_to_float(values["h"], f"{prefix}.h"),
        )

    monitor = parse_monitor(raw.get("monitor"), f"{prefix}.monitor")
    return geom, monitor


def _classify_geometry_values(values: dict[str, Any], prefix: str) -> str:
    all_int = all(
        isinstance(v, int) and not isinstance(v, bool) for v in values.values()
    )
    all_pct = all(isinstance(v, str) and _PERCENT_RE.match(v) for v in values.values())
    if all_int:
        return "absolute"
    if all_pct:
        return "percent"
    raise ActionValidationError(
        f"{prefix}: x/y/w/h must be either all integers (absolute pixels) or "
        "all percent strings like '20%' (mixing is not allowed)"
    )


def _percent_to_float(raw: str, prefix: str) -> float:
    # Caller (``_classify_geometry_values``) has already verified that ``raw``
    # is a string matching ``_PERCENT_RE``; no further checks needed here.
    match = _PERCENT_RE.match(raw)
    assert match is not None, f"{prefix}: caller failed to pre-validate"
    return float(match.group(1)) / 100.0


def parse_monitor(raw: Any, prefix: str) -> MonitorSpec | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ActionValidationError(
            f"{prefix} must be an output name, 'primary' / 'current', "
            "or an integer index"
        )
    if isinstance(raw, int):
        if raw < 0:
            raise ActionValidationError(
                f"{prefix} index must be non-negative (got {raw})"
            )
        return raw
    if isinstance(raw, str):
        if not raw:
            raise ActionValidationError(f"{prefix} must not be empty")
        if raw == "all":
            # Rejected at parse time rather than at apply time: nothing
            # resolves a single action onto every output, so a config
            # carrying it would fail on every window it matched.
            raise ActionValidationError(
                f"{prefix}: 'all' is not a monitor — use an output name, "
                "'primary', 'current', or an integer index"
            )
        return raw
    raise ActionValidationError(
        f"{prefix} must be a string or integer (got {type(raw).__name__})"
    )


def _resolve_monitor(
    apply_monitor: MonitorSpec | None,
    geom_monitor: MonitorSpec | None,
    prefix: str,
) -> MonitorSpec | None:
    if apply_monitor is not None and geom_monitor is not None:
        if apply_monitor != geom_monitor:
            raise ActionValidationError(
                f"{prefix}: monitor specified both at apply level "
                f"({apply_monitor!r}) and inside geometry ({geom_monitor!r}); "
                "pick one"
            )
        return apply_monitor
    return apply_monitor if apply_monitor is not None else geom_monitor


def _parse_desktop(raw: Any, prefix: str) -> int | str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ActionValidationError(
            f"{prefix} must be an integer index, 'current', or 'all'"
        )
    if isinstance(raw, int):
        if raw < 0:
            raise ActionValidationError(
                f"{prefix} index must be non-negative (got {raw})"
            )
        return raw
    if isinstance(raw, str):
        if raw not in ("current", "all"):
            raise ActionValidationError(
                f"{prefix}: string form must be 'current' or 'all' (got {raw!r})"
            )
        return raw
    raise ActionValidationError(
        f"{prefix} must be a string or integer (got {type(raw).__name__})"
    )



def _opt_bool(raw: dict[str, Any], key: str, prefix: str) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, bool):
        raise ActionValidationError(
            f"{prefix}.{key} must be a boolean (got {type(value).__name__})"
        )
    return value


__all__ = [
    "BUILTIN_PRESETS",
    "MONITOR_KEYWORDS",
    "AbsoluteGeometry",
    "ActionValidationError",
    "ApplyAction",
    "GeometryExpr",
    "MonitorSpec",
    "PercentGeometry",
    "PresetGeometry",
    "parse_action",
    "parse_geometry_dict",
    "parse_monitor",
]
