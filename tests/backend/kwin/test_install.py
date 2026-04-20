"""Install / version-pin behaviour for the bundled KWin script."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perch.backend.kwin import BUNDLED_SCRIPT_VERSION, PLUGIN_ID
from perch.backend.kwin.install import (
    ScriptVersionMismatch,
    bundled_source,
    current_installed_version,
    ensure_installed,
    target_dir,
    uninstall,
)


@pytest.fixture
def fake_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "scripts" / PLUGIN_ID
    monkeypatch.setenv("PERCH_KWIN_SCRIPT_TARGET", str(target))
    return target


# ── target resolution ──────────────────────────────────────────────────────


def test_target_dir_uses_env_override_when_set(
    fake_target: Path,
) -> None:
    assert target_dir() == fake_target


def test_target_dir_falls_back_to_xdg_data_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERCH_KWIN_SCRIPT_TARGET", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/fake/xdg")
    assert target_dir() == Path(f"/fake/xdg/kwin/scripts/{PLUGIN_ID}")


def test_target_dir_defaults_to_local_share_when_xdg_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PERCH_KWIN_SCRIPT_TARGET", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert target_dir() == tmp_path / ".local" / "share" / "kwin" / "scripts" / PLUGIN_ID


# ── first-install path ─────────────────────────────────────────────────────


def test_ensure_installed_copies_tree_on_first_run(fake_target: Path) -> None:
    assert not fake_target.exists()
    main_js = ensure_installed()
    assert main_js == (fake_target / "contents" / "code" / "main.js").resolve()
    assert main_js.is_file()
    assert (fake_target / "metadata.json").is_file()
    meta = json.loads((fake_target / "metadata.json").read_text())
    assert meta["KPlugin"]["Version"] == BUNDLED_SCRIPT_VERSION


def test_ensure_installed_is_idempotent_when_version_matches(
    fake_target: Path,
) -> None:
    first = ensure_installed()
    mtime_before = first.stat().st_mtime_ns
    second = ensure_installed()
    assert second == first
    # Second call should not have rewritten the file — same mtime.
    assert first.stat().st_mtime_ns == mtime_before


def test_ensure_installed_replaces_a_stale_install(
    fake_target: Path,
) -> None:
    ensure_installed()
    # Simulate a drift: rewrite metadata to a fake old version.
    meta_path = fake_target / "metadata.json"
    data = json.loads(meta_path.read_text())
    data["KPlugin"]["Version"] = "0.0.1-stale"
    meta_path.write_text(json.dumps(data))
    assert current_installed_version() == "0.0.1-stale"

    ensure_installed()
    assert current_installed_version() == BUNDLED_SCRIPT_VERSION


def test_ensure_installed_heals_a_truncated_install(
    fake_target: Path,
) -> None:
    """Metadata says the right version but main.js is gone — reinstall."""
    ensure_installed()
    main_js = fake_target / "contents" / "code" / "main.js"
    main_js.unlink()
    restored = ensure_installed()
    assert restored.is_file()


# ── version-mismatch fallthrough ───────────────────────────────────────────


def test_mismatched_source_raises_after_install(
    tmp_path: Path, fake_target: Path
) -> None:
    # Build a fake "source" tree with a mis-versioned metadata; ensure
    # we raise after install because the on-disk version doesn't match the
    # pinned bundled version.
    fake_source = tmp_path / "fake-src"
    fake_source.mkdir()
    (fake_source / "contents" / "code").mkdir(parents=True)
    (fake_source / "contents" / "code" / "main.js").write_text("// fake\n")
    (fake_source / "metadata.json").write_text(
        json.dumps({
            "KPackageStructure": "KWin/Script",
            "KPlugin": {"Id": PLUGIN_ID, "Version": "9.9.9-fake"},
        })
    )
    with pytest.raises(ScriptVersionMismatch) as excinfo:
        ensure_installed(source=fake_source)
    assert excinfo.value.expected == BUNDLED_SCRIPT_VERSION
    assert excinfo.value.found == "9.9.9-fake"
    assert excinfo.value.target == fake_target


# ── uninstall ──────────────────────────────────────────────────────────────


def test_uninstall_removes_the_script_directory(fake_target: Path) -> None:
    ensure_installed()
    assert fake_target.exists()
    uninstall()
    assert not fake_target.exists()


def test_uninstall_is_idempotent_when_target_missing(
    fake_target: Path,
) -> None:
    assert not fake_target.exists()
    uninstall()  # Should not raise.
    assert not fake_target.exists()


# ── current_installed_version ──────────────────────────────────────────────


def test_current_installed_version_returns_none_when_unset(
    fake_target: Path,
) -> None:
    assert current_installed_version() is None


def test_current_installed_version_survives_malformed_metadata(
    fake_target: Path,
) -> None:
    ensure_installed()
    (fake_target / "metadata.json").write_text("{{{broken json")
    assert current_installed_version() is None


# ── bundled_source is the package-relative path ────────────────────────────


def test_bundled_source_points_inside_the_package() -> None:
    src = bundled_source()
    assert (src / "metadata.json").is_file()
    assert (src / "contents" / "code" / "main.js").is_file()
