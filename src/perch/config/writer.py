"""Write ``config.toml`` with the atomic recipe from ``docs/02-state-format.md``.

Recipe:
1. write new content to ``path.tmp`` in the same directory;
2. fsync the tmp file;
3. rename ``path`` → ``path.bak`` (if present);
4. rename ``path.tmp`` → ``path``;
5. fsync the directory.

``tomlkit`` is used on the write side so user-authored comments, table
ordering, and formatting survive.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument


def load_document(path: Path) -> TOMLDocument:
    """Parse ``path`` with tomlkit, preserving comments and layout."""
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def document_digest(path: Path) -> str | None:
    """SHA-256 of ``path``'s bytes, or ``None`` when it does not exist.

    ``docs/02-state-format.md`` offers hand-editing ``config.toml`` as a
    supported workflow, and every writer here replaces the document whole.
    A writer that parsed the file earlier compares this before replacing it,
    so an edit made in between is reported rather than discarded. Content
    rather than mtime, so a hand edit that was reverted is not a conflict.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def atomic_write(path: Path, text: str) -> None:
    """Atomically replace ``path`` with ``text``.

    Writes ``path.tmp``, fsyncs it, rotates the old file to ``path.bak``, then
    renames the tmp file into place. Directory fsync guards the rename against
    power-loss reordering on ext4 with ``data=ordered``.

    A symlinked ``path`` is resolved first. ``rename(2)`` acts on the *link*,
    so rotating it would move the symlink itself to ``.bak`` and drop a regular
    file in its place — silently detaching a ``config.toml`` the user symlinked
    into a dotfiles repo, which ``docs/02-state-format.md`` offers as a
    supported workflow.
    """
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    bak = target.with_suffix(target.suffix + ".bak")

    try:
        # O_NOFOLLOW: the tmp name is predictable and sits in a directory
        # the user's other processes can reach, so without it a symlink
        # planted at that path redirects the write (CWE-59). The target
        # itself is resolved above, deliberately — that one is a supported
        # dotfiles workflow; this one never is.
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.write(fd, text.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

        if target.exists():
            os.replace(target, bak)
        os.replace(tmp, target)
    except OSError:
        # A half-written .tmp left on disk is picked up by nothing and
        # confuses the next reader of the directory. Clear it on the way out.
        tmp.unlink(missing_ok=True)
        raise

    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def write_document(path: Path, document: TOMLDocument) -> None:
    """Serialise ``document`` with tomlkit and atomically write to ``path``."""
    atomic_write(path, tomlkit.dumps(document))
