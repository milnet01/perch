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

import os
from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument


def load_document(path: Path) -> TOMLDocument:
    """Parse ``path`` with tomlkit, preserving comments and layout."""
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    """Atomically replace ``path`` with ``text``.

    Writes ``path.tmp``, fsyncs it, rotates the old file to ``path.bak``, then
    renames the tmp file into place. Directory fsync guards the rename against
    power-loss reordering on ext4 with ``data=ordered``.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    bak = path.with_suffix(path.suffix + ".bak")

    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    if path.exists():
        os.replace(path, bak)
    os.replace(tmp, path)

    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def write_document(path: Path, document: TOMLDocument) -> None:
    """Serialise ``document`` with tomlkit and atomically write to ``path``."""
    atomic_write(path, tomlkit.dumps(document))
