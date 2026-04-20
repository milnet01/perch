"""Install the bundled KWin script into ``$XDG_DATA_HOME/kwin/scripts/…``.

KWin on Wayland runs on the host and can only load scripts from its standard
search path (``~/.local/share/kwin/scripts/`` and the system-wide equivalents
under ``/usr/share/kwin/scripts/``). Our wheel / Flatpak / dev-install ships
the script *inside* the ``perch`` package, which KWin cannot see from there —
so the first time Perch starts against KWin, this module mirrors the bundle
into the user-level search path.

The target directory name is the KPackage plugin id (:data:`PLUGIN_ID`), which
is also the handle passed to ``Scripting.loadScript(path, plugin_id)`` so
``unloadScript(plugin_id)`` works later.

Version pinning: the Python half bundles a specific
:data:`BUNDLED_SCRIPT_VERSION`; if the on-disk copy disagrees we replace it.
If after replacement the on-disk copy *still* disagrees (broken shipped
package, filesystem failure) we raise :class:`ScriptVersionMismatch` rather
than quietly load a mismatched pair.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from . import BUNDLED_SCRIPT_DIR, BUNDLED_SCRIPT_VERSION, PLUGIN_ID

log = logging.getLogger("perch.backend.kwin.install")


class ScriptVersionMismatch(RuntimeError):
    """The on-disk script version doesn't match the bundled one."""

    def __init__(self, *, expected: str, found: str | None, target: Path) -> None:
        super().__init__(
            f"KWin script at {target} has version {found!r}, expected {expected!r}"
        )
        self.expected = expected
        self.found = found
        self.target = target


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "share"


def target_dir() -> Path:
    """Location KWin will read the script from.

    Overridable via ``PERCH_KWIN_SCRIPT_TARGET`` for tests / Flatpak /
    custom installs. The override is intended for tests — Flatpak uses
    the unchanged XDG path with ``--filesystem=xdg-data/kwin/scripts:create``.
    """
    override = os.environ.get("PERCH_KWIN_SCRIPT_TARGET")
    if override:
        return Path(override)
    return _xdg_data_home() / "kwin" / "scripts" / PLUGIN_ID


def bundled_source() -> Path:
    """Source of truth: the script shipped inside the ``perch`` package."""
    return BUNDLED_SCRIPT_DIR


def _read_version(target: Path) -> str | None:
    """Read ``KPlugin.Version`` from an installed script, or ``None``.

    Returns ``None`` if the file is missing / unreadable / malformed.
    """
    metadata = target / "metadata.json"
    if not metadata.is_file():
        return None
    try:
        data = json.loads(metadata.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("unreadable metadata at %s: %s", metadata, exc)
        return None
    if not isinstance(data, dict):
        return None
    kplugin = data.get("KPlugin")
    if not isinstance(kplugin, dict):
        return None
    version = kplugin.get("Version")
    if isinstance(version, str):
        return version
    return None


def current_installed_version(target: Path | None = None) -> str | None:
    """Public read-only view of the on-disk version, for diagnostics."""
    return _read_version(target if target is not None else target_dir())


def _mirror_tree(source: Path, target: Path) -> None:
    """Copy ``source`` → ``target``, wiping a stale ``target`` first.

    ``shutil.copytree(dirs_exist_ok=True)`` could leave orphan files from a
    previous install; we want the target to end up as an exact copy.
    """
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for root, dirs, files in os.walk(source):
        rel = Path(root).relative_to(source)
        dest_root = target / rel
        dest_root.mkdir(parents=True, exist_ok=True)
        for d in dirs:
            (dest_root / d).mkdir(exist_ok=True)
        for f in files:
            shutil.copy2(Path(root) / f, dest_root / f)


def ensure_installed(
    *,
    source: Path | None = None,
    target: Path | None = None,
) -> Path:
    """Make sure the bundled script is present at the expected target.

    Returns the absolute path to ``contents/code/main.js`` (which is what
    ``Scripting.loadScript`` wants). Idempotent: if the on-disk version
    already matches :data:`BUNDLED_SCRIPT_VERSION` and the main script file
    exists, returns immediately without re-copying.
    """
    src = source if source is not None else bundled_source()
    tgt = target if target is not None else target_dir()

    if _read_version(tgt) == BUNDLED_SCRIPT_VERSION:
        main_js = tgt / "contents" / "code" / "main.js"
        if main_js.is_file():
            log.debug("KWin script already at v%s at %s", BUNDLED_SCRIPT_VERSION, tgt)
            return main_js.resolve()
        log.info("KWin script metadata matched but main.js missing at %s; reinstalling", tgt)

    log.info("installing KWin script v%s to %s", BUNDLED_SCRIPT_VERSION, tgt)
    _mirror_tree(src, tgt)

    installed = _read_version(tgt)
    if installed != BUNDLED_SCRIPT_VERSION:
        raise ScriptVersionMismatch(
            expected=BUNDLED_SCRIPT_VERSION, found=installed, target=tgt
        )
    return (tgt / "contents" / "code" / "main.js").resolve()


def uninstall(target: Path | None = None) -> None:
    """Remove the script directory. Idempotent."""
    tgt = target if target is not None else target_dir()
    if tgt.exists():
        shutil.rmtree(tgt)
        log.info("removed KWin script at %s", tgt)


__all__ = [
    "ScriptVersionMismatch",
    "bundled_source",
    "current_installed_version",
    "ensure_installed",
    "target_dir",
    "uninstall",
]
