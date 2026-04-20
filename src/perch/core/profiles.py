"""Profiles: per-topology activation of layouts and rule scoping.

Owns the :class:`Profile` dataclass, the canonical topology-key format
(``<output>:<w>x<h>@<x>,<y>`` segments sorted alphabetically and joined by
``;``), the TOML parser that turns raw ``[[profiles]]`` tables into typed
:class:`Profile` objects, and the first-match-wins activation rule.

Authoritative reference: ``docs/09-layouts-profiles.md``. What the key does
*not* include — refresh rate, scale, output serial — is documented there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from perch.backend.types import OutputInfo

TOPOLOGY_SEPARATOR = ";"

# Segment shape: ``<output-name>:<w>x<h>@<x>,<y>``. Output names follow
# compositor conventions (``DP-1``, ``eDP-1``, ``XWAYLAND0``, ``HDMI-2-1``).
_SEGMENT_RE = re.compile(r"^([A-Za-z0-9_\-]+):(\d+)x(\d+)@(-?\d+),(-?\d+)$")


class ProfileValidationError(ValueError):
    """Raised when a raw ``[[profiles]]`` table does not satisfy the schema."""


@dataclass(frozen=True, slots=True)
class ProfileOverride:
    """Per-profile tweak to a named layout.

    The ``windows`` list stays as raw TOML tables at M2.b — layout-window
    entries are typed in M2.c when the layout engine lands. Keeping it as
    ``list[dict]`` here avoids a forward reference and doesn't cost anything
    at runtime.
    """

    layout: str
    windows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class Profile:
    """A named topology → default-layout binding."""

    name: str
    topology: str
    default_layout: str | None = None
    overrides: tuple[ProfileOverride, ...] = field(default=())


def compute_topology_key(outputs: list[OutputInfo]) -> str:
    """Canonical topology key for a connected output set.

    Drops disconnected outputs, sorts surviving segments by output name, and
    joins with ``;``. Returns ``""`` for an empty topology (no outputs at
    all — a rare but legitimate state during KWin reconfigure races).
    """
    segments = sorted(
        f"{o.name}:{o.geometry.w}x{o.geometry.h}@{o.geometry.x},{o.geometry.y}"
        for o in outputs
        if o.is_connected
    )
    return TOPOLOGY_SEPARATOR.join(segments)


def select_profile(
    profiles: list[Profile], topology_key: str
) -> Profile | None:
    """Return the first profile matching ``topology_key``, or ``None``.

    Duplicate-topology collisions are rejected at :func:`parse_profiles`
    time, so at runtime this scan is unambiguous.
    """
    if not topology_key:
        return None
    for p in profiles:
        if p.topology == topology_key:
            return p
    return None


def parse_profiles(raw: list[dict[str, Any]]) -> list[Profile]:
    """Validate and convert ``[[profiles]]`` tables into :class:`Profile`."""
    out: list[Profile] = []
    seen_names: set[str] = set()
    seen_topologies: dict[str, str] = {}

    for i, entry in enumerate(raw):
        prefix = f"[[profiles]][{i}]"

        name = _require_str(entry, "name", prefix)
        if name in seen_names:
            raise ProfileValidationError(
                f"{prefix}: duplicate profile name {name!r}"
            )
        seen_names.add(name)

        topology = _require_str(entry, "topology", prefix)
        _validate_topology_key(f"{prefix}.topology", topology)
        if topology in seen_topologies:
            raise ProfileValidationError(
                f"{prefix}.topology {topology!r} already used by "
                f"profile {seen_topologies[topology]!r}"
            )
        seen_topologies[topology] = name

        default_layout = entry.get("default_layout")
        if default_layout is not None and not isinstance(default_layout, str):
            raise ProfileValidationError(
                f"{prefix}.default_layout must be a string "
                f"(got {type(default_layout).__name__})"
            )

        overrides_raw = entry.get("override", [])
        if not isinstance(overrides_raw, list):
            raise ProfileValidationError(
                f"{prefix}.override must be an array of tables"
            )
        overrides = tuple(
            _parse_override(f"{prefix}.override[{j}]", o)
            for j, o in enumerate(overrides_raw)
        )

        known = {"name", "topology", "default_layout", "override"}
        unknown = set(entry.keys()) - known
        if unknown:
            raise ProfileValidationError(
                f"{prefix}: unknown keys {sorted(unknown)!r}"
            )

        out.append(
            Profile(
                name=name,
                topology=topology,
                default_layout=default_layout,
                overrides=overrides,
            )
        )

    return out


def _parse_override(prefix: str, raw: Any) -> ProfileOverride:
    if not isinstance(raw, dict):
        raise ProfileValidationError(f"{prefix} must be a table")
    layout = _require_str(raw, "layout", prefix)
    windows = raw.get("windows", [])
    if not isinstance(windows, list):
        raise ProfileValidationError(
            f"{prefix}.windows must be an array of tables"
        )
    for j, w in enumerate(windows):
        if not isinstance(w, dict):
            raise ProfileValidationError(
                f"{prefix}.windows[{j}] must be a table"
            )
    return ProfileOverride(layout=layout, windows=tuple(dict(w) for w in windows))


def _require_str(entry: dict[str, Any], key: str, prefix: str) -> str:
    if key not in entry:
        raise ProfileValidationError(f"{prefix}: missing {key!r}")
    value = entry[key]
    if not isinstance(value, str):
        raise ProfileValidationError(
            f"{prefix}.{key} must be a string (got {type(value).__name__})"
        )
    if not value:
        raise ProfileValidationError(f"{prefix}.{key} must not be empty")
    return value


def _validate_topology_key(prefix: str, key: str) -> None:
    segments = key.split(TOPOLOGY_SEPARATOR)
    if len(segments) != len(set(segments)):
        raise ProfileValidationError(
            f"{prefix} has duplicate segments: {key!r}"
        )
    expected = sorted(segments)
    if segments != expected:
        raise ProfileValidationError(
            f"{prefix} segments must be sorted alphabetically; "
            f"expected {TOPOLOGY_SEPARATOR.join(expected)!r}, got {key!r}"
        )
    for seg in segments:
        if not _SEGMENT_RE.match(seg):
            raise ProfileValidationError(
                f"{prefix} segment {seg!r} is malformed; "
                f"expected 'name:WxH@X,Y'"
            )
