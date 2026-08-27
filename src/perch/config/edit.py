"""Config-mutation helpers for the settings dialog.

The dialog reads a typed :class:`~perch.config.schema.Config`, edits a
working copy in-memory, and writes changes back by **mutating the user's
``tomlkit`` document** rather than regenerating one from scratch. The
regenerate-from-scratch path would lose every comment, blank line, and
formatting choice the user made by hand — the round-trip fixture in
``tests/test_config_roundtrip.py`` guards against that.

Mutators cover every section the dialog can edit:

* ``apply_general(...)`` — the ``[general]`` toggles / combo.
* ``reorder_rules(...)`` / ``delete_rule(...)`` — rules reorder + delete.
* ``delete_exclusion(...)`` / ``reorder_exclusions(...)`` — exclusions.
* ``add_layout(...)`` / ``rename_layout(...)`` / ``delete_layout(...)``
  and the per-layout entry mutators — full Layouts editing.
* ``apply_snap_hotkey(...)`` — bind a hotkey to a named snap preset.

Everything here edits the existing tomlkit AST in place — no structural
rebuild. When a table must be created (first-ever layout, first-ever
snap hotkey) tomlkit's ``table()`` constructor is used; comments adjacent
to existing content survive the edit.
"""

from __future__ import annotations

from typing import Any

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import AoT, Table

from perch.core.actions import (
    AbsoluteGeometry,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.layouts import LayoutEntry
from perch.core.matching import MatchPattern

from .schema import VALID_THEMES


class ConfigEditError(ValueError):
    """Raised when a dialog-driven mutation is rejected."""


# ── General section ─────────────────────────────────────────────────────

_GENERAL_BOOL_KEYS = ("start_at_login", "restore_on_open", "notify_on_restore")


def apply_general(
    document: TOMLDocument,
    *,
    start_at_login: bool,
    restore_on_open: bool,
    notify_on_restore: bool,
    theme: str,
    onboarding_completed: bool,
) -> None:
    """Mutate ``document`` so ``[general]`` reflects the toggles.

    Creates the ``[general]`` table if absent.

    ``onboarding_completed`` is required rather than defaulted on purpose:
    it is not user-facing, so a caller with no checkbox for it must pass
    the current value through explicitly. A default would let any caller
    silently clobber the flag and re-trigger the first-run wizard.
    """
    if theme not in VALID_THEMES:
        raise ConfigEditError(
            f"[general].theme must be one of {VALID_THEMES!r} (got {theme!r})"
        )
    general = document.get("general")
    if general is None:
        general = tomlkit.table()
        document["general"] = general

    general["start_at_login"] = start_at_login
    general["restore_on_open"] = restore_on_open
    general["notify_on_restore"] = notify_on_restore
    general["onboarding_completed"] = onboarding_completed
    general["theme"] = theme


# ── Rules section ───────────────────────────────────────────────────────


def _rules_aot(document: TOMLDocument) -> Any:
    """Return the ``[[rules]]`` array-of-tables, or ``None`` if absent."""
    return document.get("rules")


def reorder_rules(document: TOMLDocument, new_order: list[int]) -> None:
    """Rewrite ``[[rules]]`` so its order matches ``new_order``.

    ``new_order`` is a permutation of ``range(len(rules))``; violating
    that raises :class:`ConfigEditError` rather than silently dropping or
    duplicating rules.

    Mutates the existing AoT node in place so tomlkit preserves leading /
    trailing / inter-entry comments — rebuilding the AoT from scratch
    dropped trivia that sat between entries and the next top-level block.
    """
    aot = _rules_aot(document)
    n = 0 if aot is None else len(aot)
    if sorted(new_order) != list(range(n)):
        raise ConfigEditError(
            f"reorder_rules: invalid permutation of {n} rules: {new_order!r}"
        )
    if aot is None or n < 2:
        return
    # Snapshot the existing entries, then re-seat them in the new order.
    snapshots = [aot[i] for i in range(n)]
    reordered = [snapshots[i] for i in new_order]
    for _ in range(n):
        del aot[0]
    for entry in reordered:
        aot.append(entry)


def delete_rule(document: TOMLDocument, index: int) -> None:
    """Drop the rule at ``index`` from ``[[rules]]`` in place."""
    aot = _rules_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(
            f"delete_rule: index {index} out of range "
            f"(0..{(len(aot) - 1) if aot is not None else -1})"
        )
    del aot[index]


# ── Exclusions section ──────────────────────────────────────────────────


def _exclusion_array(document: TOMLDocument) -> Any:
    """Return the ``[exclusions].patterns`` array, or ``None`` if absent."""
    exclusions = document.get("exclusions")
    if exclusions is None:
        return None
    return exclusions.get("patterns")


def reorder_exclusions(document: TOMLDocument, new_order: list[int]) -> None:
    """Rewrite ``[exclusions].patterns`` so its order matches ``new_order``.

    Mutates the existing array in place to preserve formatting; see
    :func:`reorder_rules` for the rationale.
    """
    arr = _exclusion_array(document)
    n = 0 if arr is None else len(arr)
    if sorted(new_order) != list(range(n)):
        raise ConfigEditError(
            f"reorder_exclusions: invalid permutation of {n} patterns: {new_order!r}"
        )
    if arr is None or n < 2:
        return
    snapshots = [arr[i] for i in range(n)]
    reordered = [snapshots[i] for i in new_order]
    for _ in range(n):
        del arr[0]
    for entry in reordered:
        arr.append(entry)


def delete_exclusion(document: TOMLDocument, index: int) -> None:
    """Drop the exclusion pattern at ``index`` in place."""
    arr = _exclusion_array(document)
    if arr is None or not 0 <= index < len(arr):
        raise ConfigEditError(
            f"delete_exclusion: index {index} out of range "
            f"(0..{(len(arr) - 1) if arr is not None else -1})"
        )
    del arr[index]


# ── Layouts section ─────────────────────────────────────────────────────

def _layouts_table(document: TOMLDocument, *, create: bool = False) -> Any:
    """Return the ``[layouts]`` table. Create it when ``create`` is True.

    Layouts live as ``[layouts.<name>]`` sub-tables; the top-level
    ``layouts`` key is the parent table holding them.
    """
    layouts = document.get("layouts")
    if layouts is None:
        if not create:
            return None
        layouts = tomlkit.table()
        document["layouts"] = layouts
    return layouts


def _layout_table(
    document: TOMLDocument, name: str, *, create: bool = False
) -> Any:
    layouts = _layouts_table(document, create=create)
    if layouts is None:
        return None
    entry = layouts.get(name)
    if entry is None and create:
        entry = tomlkit.table()
        entry["description"] = ""
        windows: AoT = tomlkit.aot()
        entry["windows"] = windows
        layouts[name] = entry
    return entry


def add_layout(
    document: TOMLDocument, name: str, *, description: str = ""
) -> None:
    """Create a new ``[layouts.<name>]`` table.

    Raises :class:`ConfigEditError` if ``name`` is empty or already
    exists.
    """
    if not name.strip():
        raise ConfigEditError("add_layout: layout name must not be empty")
    layouts = _layouts_table(document, create=True)
    if name in layouts:
        raise ConfigEditError(f"add_layout: layout {name!r} already exists")
    table = tomlkit.table()
    table["description"] = description
    windows: AoT = tomlkit.aot()
    table["windows"] = windows
    layouts[name] = table


def rename_layout(
    document: TOMLDocument, old_name: str, new_name: str
) -> None:
    """Rename an existing layout in place.

    Uses an ordered remap: Python 3.7+ dict iteration order is the
    tomlkit document order, so rebuilding ``[layouts]`` in the same
    order with the new key preserves surrounding trivia.
    """
    if not new_name.strip():
        raise ConfigEditError("rename_layout: new name must not be empty")
    layouts = _layouts_table(document)
    if layouts is None or old_name not in layouts:
        raise ConfigEditError(f"rename_layout: layout {old_name!r} not found")
    if new_name == old_name:
        return
    if new_name in layouts:
        raise ConfigEditError(
            f"rename_layout: layout {new_name!r} already exists"
        )
    # tomlkit tables preserve insertion order; rebuild by popping + re-adding
    # in original order, swapping the key at the right moment.
    snapshot = list(layouts.items())
    for key, _ in snapshot:
        del layouts[key]
    for key, value in snapshot:
        layouts[new_name if key == old_name else key] = value


def delete_layout(document: TOMLDocument, name: str) -> None:
    """Drop ``[layouts.<name>]`` from the document."""
    layouts = _layouts_table(document)
    if layouts is None or name not in layouts:
        raise ConfigEditError(f"delete_layout: layout {name!r} not found")
    del layouts[name]


def set_layout_description(
    document: TOMLDocument, name: str, description: str
) -> None:
    """Rewrite ``[layouts.<name>].description``."""
    table = _layout_table(document, name)
    if table is None:
        raise ConfigEditError(
            f"set_layout_description: layout {name!r} not found"
        )
    table["description"] = description


def _entry_to_toml_table(entry: LayoutEntry) -> Table:
    """Serialise a :class:`LayoutEntry` into a tomlkit inline-friendly table.

    The shape matches :func:`perch.core.layouts._parse_window`'s
    expectations: ``match`` table + any of
    ``geometry``/``snap``/``monitor``/``desktop``/``maximized``.
    """
    table: Table = tomlkit.table()
    table["match"] = _match_to_toml(entry.match)
    action = entry.apply
    if action.geometry is not None:
        table["geometry"] = _geometry_to_toml(action.geometry)
    if action.snap is not None:
        table["snap"] = action.snap
    if action.monitor is not None:
        # ``monitor`` can be a str or int (MonitorSpec); tomlkit handles
        # both scalar types natively.
        table["monitor"] = action.monitor
    if action.desktop is not None:
        table["desktop"] = action.desktop
    if action.maximized is not None:
        table["maximized"] = action.maximized
    return table


def _match_to_toml(match: MatchPattern) -> Any:
    """Serialise a :class:`MatchPattern` into a tomlkit inline table.

    Fields whose in-memory value is ``None`` are skipped so the TOML
    stays tight. ``title`` round-trips as the regex source pattern.
    """
    inline = tomlkit.inline_table()
    if match.app_id is not None:
        inline["app_id"] = match.app_id
    if match.wm_class is not None:
        inline["wm_class"] = match.wm_class
    if match.title is not None:
        inline["title"] = match.title.pattern
    if match.pid is not None:
        inline["pid"] = match.pid
    if match.types:
        inline["type"] = [t.value for t in match.types]
    if match.catch_all:
        inline["catch_all"] = True
    return inline


def _geometry_to_toml(geom: Any) -> Any:
    """Serialise a :class:`GeometryExpr` into tomlkit."""
    if isinstance(geom, PresetGeometry):
        return geom.name
    if isinstance(geom, AbsoluteGeometry):
        inline = tomlkit.inline_table()
        inline["x"] = geom.x
        inline["y"] = geom.y
        inline["w"] = geom.w
        inline["h"] = geom.h
        return inline
    if isinstance(geom, PercentGeometry):
        inline = tomlkit.inline_table()
        inline["x"] = f"{geom.x_pct * 100:.0f}%"
        inline["y"] = f"{geom.y_pct * 100:.0f}%"
        inline["w"] = f"{geom.w_pct * 100:.0f}%"
        inline["h"] = f"{geom.h_pct * 100:.0f}%"
        return inline
    raise ConfigEditError(f"unknown geometry type: {type(geom).__name__}")


def _layout_windows(document: TOMLDocument, name: str) -> AoT:
    table = _layout_table(document, name)
    if table is None:
        raise ConfigEditError(f"layout {name!r} not found")
    windows = table.get("windows")
    if windows is None:
        new_windows: AoT = tomlkit.aot()
        table["windows"] = new_windows
        return new_windows
    # tomlkit's ``get`` returns ``Any``; every ``[[layouts.*.windows]]``
    # path constructs an ``AoT`` above so this cast is safe at runtime.
    assert isinstance(windows, AoT), (
        f"[layouts.{name}.windows] is {type(windows).__name__}, expected AoT"
    )
    return windows


def add_layout_entry(
    document: TOMLDocument, layout_name: str, entry: LayoutEntry
) -> None:
    """Append ``entry`` to ``[layouts.<layout_name>].windows``."""
    windows = _layout_windows(document, layout_name)
    windows.append(_entry_to_toml_table(entry))


def update_layout_entry(
    document: TOMLDocument,
    layout_name: str,
    index: int,
    entry: LayoutEntry,
) -> None:
    """Replace the entry at ``index`` with ``entry``."""
    windows = _layout_windows(document, layout_name)
    if not 0 <= index < len(windows):
        raise ConfigEditError(
            f"update_layout_entry: index {index} out of range "
            f"(0..{len(windows) - 1})"
        )
    windows[index] = _entry_to_toml_table(entry)


def delete_layout_entry(
    document: TOMLDocument, layout_name: str, index: int
) -> None:
    """Drop the entry at ``index`` from the layout's windows array."""
    windows = _layout_windows(document, layout_name)
    if not 0 <= index < len(windows):
        raise ConfigEditError(
            f"delete_layout_entry: index {index} out of range "
            f"(0..{len(windows) - 1})"
        )
    del windows[index]


def reorder_layout_entries(
    document: TOMLDocument, layout_name: str, new_order: list[int]
) -> None:
    """Rewrite the layout's windows array to ``new_order``."""
    windows = _layout_windows(document, layout_name)
    n = len(windows)
    if sorted(new_order) != list(range(n)):
        raise ConfigEditError(
            f"reorder_layout_entries: invalid permutation of {n} entries: "
            f"{new_order!r}"
        )
    if n < 2:
        return
    snapshots = [windows[i] for i in range(n)]
    reordered = [snapshots[i] for i in new_order]
    for _ in range(n):
        del windows[0]
    for entry in reordered:
        windows.append(entry)


# ── Profiles section ────────────────────────────────────────────────────


def _profiles_aot(document: TOMLDocument, *, create: bool = False) -> Any:
    aot = document.get("profiles")
    if aot is None and create:
        aot = tomlkit.aot()
        document["profiles"] = aot
    return aot


def add_profile(
    document: TOMLDocument,
    *,
    name: str,
    topology: str,
    default_layout: str | None = None,
) -> None:
    """Append a new ``[[profiles]]`` table to the document.

    Rejects empty ``name`` and empty ``topology``; the loader's schema
    validation enforces both on read, so writing an empty value would
    silently corrupt the config until the next restart.
    """
    if not name.strip():
        raise ConfigEditError("add_profile: profile name must not be empty")
    if not topology.strip():
        raise ConfigEditError(
            f"add_profile: topology must not be empty for profile {name!r}"
        )
    aot = _profiles_aot(document, create=True)
    for existing in aot:
        if existing.get("name") == name:
            raise ConfigEditError(
                f"add_profile: profile {name!r} already exists"
            )
        if existing.get("topology") == topology:
            other = existing.get("name") or "<unnamed>"
            raise ConfigEditError(
                f"add_profile: topology already used by profile {other!r}"
            )
    entry = tomlkit.table()
    entry["name"] = name
    entry["topology"] = topology
    if default_layout is not None:
        entry["default_layout"] = default_layout
    aot.append(entry)


def rename_profile(
    document: TOMLDocument, index: int, new_name: str
) -> None:
    if not new_name.strip():
        raise ConfigEditError("rename_profile: new name must not be empty")
    aot = _profiles_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(
            f"rename_profile: index {index} out of range"
        )
    for i, existing in enumerate(aot):
        if i != index and existing.get("name") == new_name:
            raise ConfigEditError(
                f"rename_profile: profile {new_name!r} already exists"
            )
    aot[index]["name"] = new_name


def delete_profile(document: TOMLDocument, index: int) -> None:
    aot = _profiles_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(f"delete_profile: index {index} out of range")
    del aot[index]


def set_profile_field(
    document: TOMLDocument, index: int, key: str, value: Any
) -> None:
    """Rewrite a scalar profile field (``name`` / ``topology`` /
    ``default_layout``).

    Passing ``value=None`` on ``default_layout`` removes the key so the
    serialised TOML stays lean (matches the parser's
    "default_layout is optional" expectation).

    ``name`` and ``topology`` reject empty strings — the loader's schema
    validation enforces both on read and a silently-written empty value
    would invalidate the config on the next start.
    """
    if key not in ("topology", "default_layout", "name"):
        raise ConfigEditError(f"set_profile_field: unknown key {key!r}")
    aot = _profiles_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(
            f"set_profile_field: index {index} out of range"
        )
    entry = aot[index]
    if value is None:
        if key in entry:
            del entry[key]
        return
    if key in ("name", "topology") and isinstance(value, str) and not value.strip():
        raise ConfigEditError(
            f"set_profile_field: {key!r} must not be empty"
        )
    entry[key] = value


def set_profile_overrides(
    document: TOMLDocument,
    index: int,
    overrides: list[tuple[str, list[LayoutEntry]]],
) -> None:
    """Replace the profile's ``[[profiles.override]]`` array wholesale.

    ``overrides`` is ``(layout_name, entries)`` pairs. The entries are
    the typed :class:`LayoutEntry`; this helper serialises them via the
    same ``_entry_to_toml_table`` used by the Layouts editor. Existing
    override tables are cleared before the new ones are appended.
    """
    aot = _profiles_aot(document)
    if aot is None or not 0 <= index < len(aot):
        raise ConfigEditError(
            f"set_profile_overrides: index {index} out of range"
        )
    entry = aot[index]
    # Drop the existing override AoT (if any) and re-create it from
    # scratch. The override-level TOML is fully dialog-authored so
    # losing inter-override comments is acceptable.
    if "override" in entry:
        del entry["override"]
    if not overrides:
        return
    override_aot: AoT = tomlkit.aot()
    for layout_name, entries in overrides:
        ov = tomlkit.table()
        ov["layout"] = layout_name
        if entries:
            windows: AoT = tomlkit.aot()
            for e in entries:
                windows.append(_entry_to_toml_table(e))
            ov["windows"] = windows
        override_aot.append(ov)
    entry["override"] = override_aot


# ── Hotkeys section ─────────────────────────────────────────────────────


def apply_snap_hotkey(
    document: TOMLDocument, snap_name: str, accel: str | None
) -> None:
    """Set ``[snaps.<snap_name>].hotkey`` to ``accel`` (or clear it).

    Passing ``accel=None`` or an empty string removes the ``hotkey`` key
    entirely so the saved TOML doesn't carry an empty placeholder.
    Raises :class:`ConfigEditError` when the snap preset is not
    declared — snap definitions are user-authored, the dialog only
    binds / unbinds keys to them.
    """
    snaps = document.get("snaps")
    if snaps is None:
        raise ConfigEditError(
            f"apply_snap_hotkey: no [snaps] table (preset {snap_name!r} missing)"
        )
    preset = snaps.get(snap_name)
    if preset is None:
        raise ConfigEditError(
            f"apply_snap_hotkey: snap preset {snap_name!r} not found"
        )
    if not isinstance(preset, (dict, Table)):
        raise ConfigEditError(
            f"apply_snap_hotkey: [snaps.{snap_name}] must be a table"
        )
    if accel:
        preset["hotkey"] = accel
    else:
        if "hotkey" in preset:
            del preset["hotkey"]
