"""Tests for ``scripts/install-gnome-extension.py``.

The script is the dev path ``docs/06-backend-stubs.md`` §"Flatpak Perch
cannot install the extension" documents, and it is the only consumer of
``BUNDLED_EXTENSION_DIR`` and ``EXTENSION_UUID``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from perch.backend.mutter import EXTENSION_UUID

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "install-gnome-extension.py"
)


def _load() -> object:
    spec = importlib.util.spec_from_file_location("_install_ext", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_copies_the_bundled_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    module = _load()

    assert module.install(force=False) == 0  # type: ignore[attr-defined]

    target = tmp_path / "gnome-shell" / "extensions" / EXTENSION_UUID
    assert (target / "metadata.json").is_file()
    assert (target / "extension.js").is_file()


def test_install_refuses_to_clobber_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing install may be a distro package's or the user's own."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    module = _load()
    assert module.install(force=False) == 0  # type: ignore[attr-defined]

    assert module.install(force=False) == 1  # type: ignore[attr-defined]
    assert module.install(force=True) == 0  # type: ignore[attr-defined]


def test_extensions_dir_honours_xdg_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    module = _load()
    assert module.extensions_dir() == (  # type: ignore[attr-defined]
        tmp_path / "share" / "gnome-shell" / "extensions"
    )
