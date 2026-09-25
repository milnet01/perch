"""Static checks on the bundled KWin script tree.

These are pure-Python unit tests: we do not run the script (that needs a
live KWin, tested under ``@pytest.mark.kwin``). Here we only verify that
the files are present, parse, and declare the metadata the Python half
pins against.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
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
        # A call to it, not the name anywhere (a comment would pass).
        assert re.search(rf'callDBus\(SVC, OBJ, IF, "{method}"', main_js), (
            f"script is missing outbound method: {method}"
        )


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
        "queryActiveWindow",
        "queryCurrentDesktop",
        "queryDesktopCount",
    ):
        # A case label, not the string anywhere (a comment would pass).
        assert re.search(rf'case\s+"{op}"\s*:', main_js), (
            f"script dispatcher is missing op: {op}"
        )


def test_main_js_does_not_use_Qt_namespace() -> None:
    """KWin's JS sandbox does not expose ``Qt.rect`` / ``Qt.size`` / ``Qt.point``.

    Using them fails at runtime with ``Qt is not defined`` — we caught this
    during v1.0.0 smoke testing when ``set_geometry`` never actually moved a
    window on live KWin. Regression guard: grep for any ``Qt.<thing>(...)``
    call in the script.
    """
    import re

    main_js = (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").read_text()
    bad = re.findall(r"\bQt\.[A-Za-z_]+\s*\(", main_js)
    assert not bad, (
        f"main.js uses Qt.* calls that aren't available in KWin's JS "
        f"sandbox: {bad!r}. Use plain {{x, y, width, height}} objects "
        f"for QRect assignment; QTimer is the only Qt global that is "
        f"reliably exposed."
    )


def test_main_js_script_version_matches_python_constant() -> None:
    """The ``ScriptReady`` signal carries ``SCRIPT_VERSION`` — it must match
    :data:`BUNDLED_SCRIPT_VERSION`, else the Python side logs the wrong
    version and the user chases a phantom "I bumped it but the log says
    old" mystery (caught by smoke-testing v1.1.0).
    """
    import re

    main_js = (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").read_text()
    match = re.search(r'SCRIPT_VERSION\s*=\s*"([^"]+)"', main_js)
    assert match is not None, (
        "main.js must define SCRIPT_VERSION as a const string"
    )
    assert match.group(1) == BUNDLED_SCRIPT_VERSION, (
        f"main.js SCRIPT_VERSION={match.group(1)!r} differs from "
        f"BUNDLED_SCRIPT_VERSION={BUNDLED_SCRIPT_VERSION!r}"
    )


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


def test_wheel_config_ships_the_script_tree() -> None:
    """The wheel must carry the JS tree, not only the Python.

    Regression guard for a ``pyproject.toml`` rewrite. The tests run from
    an editable install, so ``BUNDLED_SCRIPT_DIR`` resolving proves nothing
    about the wheel; this reads the wheel target's config instead. Hatch
    ships every file under a listed package, so the script is in the wheel
    as long as its package is listed whole and nothing excludes it.
    """
    project = Path(__file__).resolve().parents[3]
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    script = BUNDLED_SCRIPT_DIR.resolve().relative_to(project).as_posix()
    assert any(script.startswith(pkg + "/") for pkg in wheel["packages"]), script
    for key in ("exclude", "only-include"):
        assert key not in wheel, f"wheel target sets {key!r}; recheck {script}"
    assert (BUNDLED_SCRIPT_DIR / "metadata.json").exists()
    assert (BUNDLED_SCRIPT_DIR / "contents" / "code" / "main.js").exists()
