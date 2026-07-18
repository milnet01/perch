#!/usr/bin/env python3
"""Render Perch screenshots under Qt's offscreen platform.

Produces ``docs/screenshots/tray-menu.png`` and
``docs/screenshots/rules-editor.png`` by constructing the widgets,
forcing a layout, and grabbing via ``QWidget.grab()``. Runs headless
(``QT_QPA_PLATFORM=offscreen``) so it works under CI.

Invoke from the repo root::

    python3 scripts/render-screenshots.py

The checked-in screenshots are referenced from
``data/io.github.milnet01.Perch.metainfo.xml`` and
``docs/08-ui.md``; regenerate them when the widgets change.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from perch.core.actions import AbsoluteGeometry, ApplyAction, PresetGeometry  # noqa: E402
from perch.core.matching import MatchPattern  # noqa: E402
from perch.core.rules import Context, Rule  # noqa: E402
from perch.core.snaps import SnapPreset  # noqa: E402
from perch.ui.tray import TrayController, TrayState, build_tray_menu  # noqa: E402

OUT = REPO / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def _save(pixmap: QPixmap, path: Path) -> None:
    if pixmap.isNull():
        raise RuntimeError(f"empty pixmap for {path}")
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"save failed: {path}")
    print(f"wrote {path.relative_to(REPO)} ({pixmap.width()}x{pixmap.height()})")


def render_tray_menu() -> None:
    """Screenshot of the tray menu with a representative TrayState."""
    snap = SnapPreset(
        name="workbench",
        geometry=AbsoluteGeometry(100, 100, 1600, 1000),
        monitor=None,
    )
    state = TrayState(
        active_profile="docked",
        active_layout="coding",
        available_layouts=("coding", "writing", "media"),
        user_snaps=(snap,),
        paused=False,
    )
    controller = TrayController(state)
    menu = build_tray_menu(state, controller, parent=None)
    menu.ensurePolished()
    menu.adjustSize()
    size = menu.sizeHint()
    # Force a reasonable minimum so the screenshot is readable on HiDPI.
    size = QSize(max(size.width(), 280), max(size.height(), 360))
    menu.resize(size)
    menu.show()
    QApplication.processEvents()
    pix = menu.grab()
    _save(pix, OUT / "tray-menu.png")


def render_rules_editor() -> None:
    """Screenshot of the Rules table with a representative set of rules."""
    # The dialog normally loads a tomlkit document. For rendering we
    # hand-build a Config with demo rules and inject a stub document.
    from perch.config.schema import Config, GeneralSettings
    from perch.ui.dialog import SECTION_RULES, ConfigDialog

    rules = [
        Rule(
            name="Firefox on external",
            match=MatchPattern(app_id="firefox"),
            apply=ApplyAction(
                geometry=PresetGeometry("maximize"),
                monitor="HDMI-1",
            ),
        ),
        Rule(
            name="Konsole left-half",
            match=MatchPattern(app_id="konsole"),
            apply=ApplyAction(geometry=PresetGeometry("left-half")),
        ),
        Rule(
            name="Editor on profile:coding",
            match=MatchPattern(app_id="code"),
            apply=ApplyAction(
                geometry=AbsoluteGeometry(0, 0, 1200, 1080),
            ),
            context=Context(profile="docked", layout="coding"),
        ),
    ]
    config = Config(general=GeneralSettings(), rules=rules)

    class _FakeDoc:
        """Stand-in for TOMLDocument (no disk I/O in the screenshot path)."""

    dialog = ConfigDialog(
        config,
        REPO / "docs" / "screenshots" / "_stub_config.toml",
        load_document_callback=lambda _path: _FakeDoc(),
        save_callback=lambda _path, _doc: None,
    )
    dialog.select_section(SECTION_RULES)
    dialog.resize(960, 540)
    dialog.show()
    QApplication.processEvents()
    pix = dialog.grab()
    _save(pix, OUT / "rules-editor.png")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    render_tray_menu()
    render_rules_editor()
    # Force flush and allow Qt to shutdown cleanly.
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
