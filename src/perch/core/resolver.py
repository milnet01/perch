"""Turn an :class:`ApplyAction` (plus live world state) into concrete
backend arguments.

The rules engine emits an :class:`ApplyAction` without looking at the
current outputs; the reducer, at apply time, calls :func:`resolve_action`
to convert percent geometries to pixels, preset names to rectangles, and
monitor keywords (``primary`` / ``current`` / index) to output names.

Separated from the engine so the engine stays pure and testable without
a live compositor. Spec: ``docs/07-rules-engine.md`` §Geometry resolution.
"""

from __future__ import annotations

from dataclasses import dataclass

from perch.backend.types import (
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowInfo,
)

from .actions import (
    BUILTIN_PRESETS,
    AbsoluteGeometry,
    ApplyAction,
    GeometryExpr,
    MonitorSpec,
    PercentGeometry,
    PresetGeometry,
)
from .snaps import SnapPreset


class ResolveError(ValueError):
    """Raised when an :class:`ApplyAction` cannot be resolved against the
    current world state (unknown snap, unknown monitor, missing output).
    """


@dataclass(frozen=True, slots=True)
class ResolvedPlacement:
    """The concrete values passed to the backend.

    Any field may be ``None`` — the reducer only issues backend calls for
    fields that are set, so a plain ``maximized = true`` action leaves
    ``geometry`` / ``monitor`` / ``desktop`` unset and the reducer only
    calls ``set_state``.
    """

    geometry: Geometry | None = None
    monitor: OutputName | None = None
    desktop: DesktopIndex | None = None
    maximized: bool | None = None
    unmaximize_first: bool = False


def resolve_action(
    action: ApplyAction,
    window: WindowInfo,
    outputs: list[OutputInfo],
    snaps: dict[str, SnapPreset],
    profile_outputs: list[OutputName] | None = None,
) -> ResolvedPlacement:
    """Resolve ``action`` against the current outputs + snap table.

    ``profile_outputs`` is the ordered output list of the active profile,
    used to resolve integer monitor indices. When the active profile has
    not been computed yet (no matching topology) the argument may be
    omitted; integer indices then raise :class:`ResolveError`.
    """
    target_monitor: OutputName | None = None
    geometry: Geometry | None = None

    snap_preset = _resolve_snap(action.snap, snaps)
    effective_geometry: GeometryExpr | None
    effective_monitor = action.monitor
    if action.geometry is not None:
        effective_geometry = action.geometry
    elif snap_preset is not None:
        effective_geometry = snap_preset.geometry
        # A snap preset can carry its own monitor — treat it as the apply-level
        # monitor when the user didn't specify one directly on the rule.
        if effective_monitor is None:
            effective_monitor = snap_preset.monitor
    else:
        effective_geometry = None

    if effective_geometry is not None or effective_monitor is not None:
        target_monitor = _resolve_monitor(
            effective_monitor, window, outputs, profile_outputs
        )

    if effective_geometry is not None:
        expr = _resolve_preset_reference(effective_geometry, snaps)
        if target_monitor is None:
            target_monitor = window.monitor
        output = _find_output(target_monitor, outputs)
        geometry = _resolve_geometry(expr, output.work_area)

    desktop = _resolve_desktop(action.desktop, window)

    # ``maximized`` in the resolved placement is the *post-geometry* state to
    # set. ``unmaximize_first`` flags the *pre-geometry* unmaximize that
    # docs/07 §Apply order step 1 requires so subsequent geometry writes
    # stick on backends that ignore them on maximized windows.
    has_placement = geometry is not None
    unmaximize_first = action.maximized is False and has_placement
    if unmaximize_first:
        maximized: bool | None = None
    else:
        maximized = action.maximized

    return ResolvedPlacement(
        geometry=geometry,
        monitor=target_monitor,
        desktop=desktop,
        maximized=maximized,
        unmaximize_first=unmaximize_first,
    )


# ── monitor resolution ─────────────────────────────────────────────────────
def _resolve_monitor(
    spec: MonitorSpec | None,
    window: WindowInfo,
    outputs: list[OutputInfo],
    profile_outputs: list[OutputName] | None,
) -> OutputName:
    if spec is None:
        return window.monitor
    if isinstance(spec, int):
        if profile_outputs is None:
            raise ResolveError(
                f"integer monitor index {spec} used but no active profile; "
                "name the profile or use an output name / 'primary' / 'current'"
            )
        if spec >= len(profile_outputs):
            raise ResolveError(
                f"monitor index {spec} exceeds active profile's "
                f"output count ({len(profile_outputs)})"
            )
        return profile_outputs[spec]
    if spec == "current":
        return window.monitor
    if spec == "primary":
        for o in outputs:
            if o.is_primary and o.is_connected:
                return o.name
        raise ResolveError("no primary output is connected")
    if spec == "all":
        # "all" is only meaningful for layouts (multi-window), not a single
        # apply; the reducer should never reach here with "all". Surface
        # it plainly.
        raise ResolveError(
            "monitor='all' is a layout-fanout directive and cannot resolve "
            "to a single output"
        )
    # Otherwise: a concrete output name.
    if not any(o.name == spec and o.is_connected for o in outputs):
        raise ResolveError(f"output {spec!r} is not currently connected")
    return spec


def _find_output(name: OutputName, outputs: list[OutputInfo]) -> OutputInfo:
    for o in outputs:
        if o.name == name:
            return o
    raise ResolveError(f"output {name!r} disappeared between probes")


# ── geometry resolution ────────────────────────────────────────────────────
def _resolve_preset_reference(
    expr: GeometryExpr, snaps: dict[str, SnapPreset]
) -> GeometryExpr:
    """Follow a single level of preset indirection.

    Built-in names expand to :class:`PercentGeometry`; user snap names
    expand to the snap's stored geometry (which has already been parsed
    as absolute or percent). One level is enough — snap geometries are
    not themselves preset references (enforced by the snaps parser).
    """
    if not isinstance(expr, PresetGeometry):
        return expr
    name = expr.name
    builtin = BUILTIN_PRESETS.get(name)
    if builtin is not None:
        return builtin
    user = snaps.get(name)
    if user is not None:
        return user.geometry
    raise ResolveError(
        f"unknown geometry preset {name!r}; not a built-in "
        f"and not in [snaps]"
    )


def _resolve_geometry(
    expr: GeometryExpr, work_area: Geometry
) -> Geometry:
    if isinstance(expr, AbsoluteGeometry):
        # Clamp into the work area — a rule cannot push a window off-screen.
        return _clamp(Geometry(expr.x, expr.y, expr.w, expr.h), work_area)
    if isinstance(expr, PercentGeometry):
        # Round half-to-even to keep outputs stable across repeat evals.
        return Geometry(
            x=work_area.x + _round(expr.x_pct * work_area.w),
            y=work_area.y + _round(expr.y_pct * work_area.h),
            w=max(1, _round(expr.w_pct * work_area.w)),
            h=max(1, _round(expr.h_pct * work_area.h)),
        )
    # PresetGeometry — already expanded by the caller.
    raise ResolveError(
        f"unexpanded preset {expr!r} reached geometry resolver; this is a bug"
    )


def _round(x: float) -> int:
    # Python's ``round`` uses banker's rounding (half to even) out of the box.
    return round(x)


def _clamp(geom: Geometry, work_area: Geometry) -> Geometry:
    """Ensure ``geom`` fits inside ``work_area``.

    Preserves the requested size if possible; shrinks only when the rule
    is genuinely too big for the target monitor.
    """
    w = min(geom.w, work_area.w)
    h = min(geom.h, work_area.h)
    x = max(work_area.x, min(geom.x, work_area.x + work_area.w - w))
    y = max(work_area.y, min(geom.y, work_area.y + work_area.h - h))
    return Geometry(x, y, w, h)


# ── desktop + snap resolution ──────────────────────────────────────────────
def _resolve_desktop(
    spec: int | str | None, window: WindowInfo
) -> DesktopIndex | None:
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    if spec == "current":
        return window.desktop
    if spec == "all":
        # Encoded as the sticky sentinel per WindowInfo.desktop docs (-1 means
        # "all desktops").
        return -1
    raise ResolveError(f"unknown desktop spec {spec!r}")


def _resolve_snap(
    snap_name: str | None, snaps: dict[str, SnapPreset]
) -> SnapPreset | None:
    if snap_name is None:
        return None
    # Built-in snap names are geometry-only; if the user says snap =
    # "left-half" it expands inline via BUILTIN_PRESETS. Check the user
    # table first so they can shadow a built-in.
    user = snaps.get(snap_name)
    if user is not None:
        return user
    if snap_name in BUILTIN_PRESETS:
        # Construct an ad-hoc SnapPreset wrapping the built-in so callers
        # don't need to branch on "built-in vs user".
        return SnapPreset(
            name=snap_name, geometry=BUILTIN_PRESETS[snap_name], monitor=None
        )
    raise ResolveError(
        f"unknown snap {snap_name!r}; not a built-in and not in [snaps]"
    )
