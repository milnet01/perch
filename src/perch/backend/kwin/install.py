"""Install the bundled KWin script into the host's ``kwin/scripts/`` directory.

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

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

from ...paths import is_flatpak
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


def _host_data_home() -> Path:
    """Data directory KWin itself reads, which is not always ours.

    Inside a Flatpak ``XDG_DATA_HOME`` is redirected to
    ``~/.var/app/<id>/data``. KWin runs on the host and cannot read that,
    so honouring the redirect puts the script where it will never be
    loaded. The manifest's ``--filesystem=xdg-data/kwin/scripts:create``
    mounts the *host* directory at its real path, so resolve from
    ``$HOME`` and ignore the redirect.
    """
    if is_flatpak():
        return Path.home() / ".local" / "share"
    raw = os.environ.get("XDG_DATA_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".local" / "share"


def target_dir() -> Path:
    """Location KWin will read the script from.

    Overridable via ``PERCH_KWIN_SCRIPT_TARGET`` for tests and custom
    installs; the override wins everywhere, sandbox included.
    """
    override = os.environ.get("PERCH_KWIN_SCRIPT_TARGET")
    if override:
        return Path(override)
    return _host_data_home() / "kwin" / "scripts" / PLUGIN_ID


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


def _tree_digest(root: Path) -> str:
    """Return a stable SHA-256 digest of ``root``'s file contents.

    Walks the tree deterministically (sorted) and hashes each relative
    path plus its bytes. Used by :func:`ensure_installed` to detect
    when the on-disk script has drifted from the bundled source even
    though ``metadata.json``'s version still matches — the bug that
    made v1.1.0's ``Qt.rect`` fix land on GitHub but never reach the
    user's running KWin session.

    Returns an empty-tree sentinel (``"empty"``) if ``root`` is missing
    or holds no files, so a first-time install reliably mismatches.
    """
    if not root.is_dir():
        return "empty"
    h = hashlib.sha256()
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    if not files:
        return "empty"
    for path in files:
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(path.read_bytes())
        except OSError:
            # Any unreadable file → treat as drift, mirror will retry.
            return "unreadable"
        h.update(b"\0")
    return h.hexdigest()


def ensure_installed(
    *,
    source: Path | None = None,
    target: Path | None = None,
) -> Path:
    """Make sure the bundled script is present and content-matched at the target.

    Returns the absolute path to ``contents/code/main.js`` (which is what
    ``Scripting.loadScript`` wants).

    Installation is idempotent but **content-based**: if the bundled
    tree's SHA-256 digest matches the on-disk tree's digest, we skip
    the copy. Version-only matching is not enough — a bugfix to
    ``main.js`` that didn't bump ``BUNDLED_SCRIPT_VERSION`` would
    otherwise be shadowed by a stale install, and the user would keep
    loading the broken script forever (this exact bug landed in
    v1.1.0 before M9.f.14).
    """
    src = source if source is not None else bundled_source()
    tgt = target if target is not None else target_dir()

    if _read_version(tgt) == BUNDLED_SCRIPT_VERSION:
        main_js = tgt / "contents" / "code" / "main.js"
        if main_js.is_file() and _tree_digest(src) == _tree_digest(tgt):
            log.debug(
                "KWin script already at v%s (content match) at %s",
                BUNDLED_SCRIPT_VERSION, tgt,
            )
            return main_js.resolve()
        if main_js.is_file():
            log.info(
                "KWin script metadata matched at %s but content drifted "
                "from bundled source; reinstalling",
                tgt,
            )
        else:
            log.info(
                "KWin script metadata matched but main.js missing at %s; "
                "reinstalling",
                tgt,
            )

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
