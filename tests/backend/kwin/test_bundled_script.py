"""Static checks on the bundled KWin script tree.

These are pure-Python unit tests: we do not run the script (that needs a
live KWin, tested under ``@pytest.mark.kwin``). Here we only verify that
the files are present, parse, and declare the metadata the Python half
pins against.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from perch.backend.kwin import (
    BUNDLED_SCRIPT_DIR,
    BUNDLED_SCRIPT_VERSION,
    INTERFACE_NAME,
    OBJECT_PATH,
    PLUGIN_ID,
    SERVICE_NAME,
)


def test_bundled_script_dir_exists_inside_package() -> None:
    assert BUNDLED_SCRIPT_DIR.is_dir(), BUNDLED_SCRIPT_DIR
    assert (BUNDLED_SCRIPT_DIR / "metadata.json").is_file()
    assert (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").is_file()


def test_metadata_declares_expected_plugin_id_and_version() -> None:
    meta = json.loads((BUNDLED_SCRIPT_DIR / "metadata.json").read_text())
    assert meta["KPackageStructure"] == "KWin/Script"
    kplugin = meta["KPlugin"]
    assert kplugin["Id"] == PLUGIN_ID
    assert kplugin["Version"] == BUNDLED_SCRIPT_VERSION
    assert kplugin["License"] == "GPL-3.0-or-later"
    # EnabledByDefault must be false — Perch loads the script imperatively
    # via Scripting.loadScript; auto-loading would give us two copies.
    assert kplugin["EnabledByDefault"] is False
    # Main script path must resolve under contents/ — KPackage convention.
    main_rel = meta["X-Plasma-MainScript"]
    assert (BUNDLED_SCRIPT_DIR / "contents" / main_rel).is_file()


def test_service_and_interface_names_are_consistent_across_package() -> None:
    # These names appear in three places: the Python package constants, the
    # JS script, and the docs. If any drifts the others must drift too.
    assert SERVICE_NAME == "io.github.milnet01.Perch"
    assert OBJECT_PATH == "/KWin"
    assert INTERFACE_NAME == "io.github.milnet01.Perch.KWin1"

    main_js = (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").read_text()
    assert f'"{SERVICE_NAME}"' in main_js
    assert f'"{OBJECT_PATH}"' in main_js
    assert f'"{INTERFACE_NAME}"' in main_js


def test_main_js_declares_expected_outbound_methods() -> None:
    """Script must call every method Perch's service declares — otherwise
    the Python side will silently miss events.
    """
    main_js = (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").read_text()
    for method in (
        "WindowAdded",
        "WindowRemoved",
        "WindowGeometryChanged",
        "WindowPropertiesChanged",
        "OutputsChanged",
        "PollCommand",
        "CommandDone",
        "ScriptReady",
    ):
        assert f'"{method}"' in main_js, f"script is missing outbound method: {method}"


def test_main_js_handles_every_inbound_op() -> None:
    """Dispatcher in runOne must have a case for every op Perch sends."""
    main_js = (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").read_text()
    for op in (
        "setFrameGeometry",
        "setFullScreen",
        "setMinimized",
        "setMaximizeMode",
        "closeWindow",
        "setDesktop",
        "queryWindows",
        "queryOutputs",
        "queryWindow",
        "queryCurrentDesktop",
        "queryDesktopCount",
    ):
        assert f'"{op}"' in main_js, f"script dispatcher is missing op: {op}"


def test_main_js_parses_with_node_when_available() -> None:
    """Fail loud on accidental syntax breaks in main.js.

    Skipped on machines without ``node``; the packaged CI image has it.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; JS syntax check unavailable")
    main_js = BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js"
    result = subprocess.run(
        [node, "--check", str(main_js)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"node --check failed:\n{result.stderr}"


def test_bundled_script_shipped_in_wheel(tmp_path: Path) -> None:
    """hatch sdist/wheel must include the JS tree.

    Regression guard: if somebody rewrites ``pyproject.toml`` and forgets
    the ``src/perch`` package-data include, the wheel will load the Python
    but break at first script install. Cheap check: the file is reachable
    from the installed ``perch.backend.kwin`` package, which is exactly
    what :data:`BUNDLED_SCRIPT_DIR` does.
    """
    assert (BUNDLED_SCRIPT_DIR / "metadata.json").exists()
    assert (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").exists()
