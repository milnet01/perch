"""Tests for the tray menu + controller.

Per the pytest-qt + qasync research (see docs/11-roadmap.md §Phase 2.5
research log), these tests never instantiate a real ``QSystemTrayIcon``.
The tray is a thin shell; the menu is a pure function of state, and the
controller's intent emission is the testable contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMenu

from perch.core.actions import AbsoluteGeometry
from perch.core.snaps import SnapPreset
from perch.ui.intents import (
    ActivateLayout,
    OpenConfigDialog,
    OpenConfigFolder,
    Quit,
    ReapplyRules,
    ShowAbout,
    SnapFocused,
    TogglePause,
)
from perch.ui.tray import (
    BUILTIN_SNAP_MENU_ITEMS,
    TrayController,
    TrayState,
    build_tray_menu,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _empty_state() -> TrayState:
    return TrayState(
        active_profile=None,
        active_layout=None,
        available_layouts=(),
    )


def _populated_state() -> TrayState:
    user_snap = SnapPreset(
        name="my-center",
        geometry=AbsoluteGeometry(100, 100, 800, 600),
        monitor=None,
    )
    return TrayState(
        active_profile="docked",
        active_layout="coding",
        available_layouts=("coding", "writing", "media"),
        user_snaps=(user_snap,),
        paused=True,
    )


def _action_texts(menu: QMenu) -> list[str]:
    """Return visible top-level action labels (skip separators)."""
    return [a.text() for a in menu.actions() if not a.isSeparator()]


# ── Menu structure ──────────────────────────────────────────────────────


def test_build_menu_has_documented_top_level_entries(qtbot: QtBot) -> None:
    """docs/08-ui.md §Menu structure pins the top-level ordering."""
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    texts = _action_texts(menu)
    assert texts == [
        "Perch — idle / no layout",
        "Layouts",
        "Snap focused window",
        "Pause Perch",
        "Reapply rules now",
        "Configure Perch…",
        "Open config folder",
        "About Perch",
        "Quit Perch",
    ]


def test_header_reflects_active_profile_and_layout(qtbot: QtBot) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    header = next(a for a in menu.actions() if not a.isSeparator())
    assert header.text() == "Perch — docked / coding"
    assert not header.isEnabled()


def _submenu(menu: QMenu, parent_text: str) -> QMenu:
    """Return the submenu attached to the action with ``parent_text``.

    The returned Python wrapper is held in the caller's local; to keep
    the shiboken wrapper alive we access the QMenu through the parent
    menu's internal child-menu list (PySide6 sometimes releases the
    wrapper returned by ``QAction.menu()`` between lookups under qtbot's
    cleanup).
    """
    submenu = None
    for child in menu.findChildren(QMenu):
        if child.title() == parent_text:
            submenu = child
            break
    assert submenu is not None, f"no submenu titled {parent_text!r}"
    return submenu


def test_layouts_submenu_lists_available_layouts_with_active_checked(
    qtbot: QtBot,
) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    layouts = _submenu(menu, "Layouts")
    sub_texts = [a.text() for a in layouts.actions()]
    assert sub_texts == ["(none)", "coding", "writing", "media"]

    active = next(a for a in layouts.actions() if a.text() == "coding")
    assert active.isCheckable()
    assert active.isChecked()

    none_entry = next(a for a in layouts.actions() if a.text() == "(none)")
    assert not none_entry.isChecked()


def test_snap_submenu_contains_all_builtins_in_order(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    snap = _submenu(menu, "Snap focused window")
    labels = [a.text() for a in snap.actions()]
    assert labels == [lbl for _, lbl in BUILTIN_SNAP_MENU_ITEMS]


def test_snap_submenu_appends_user_snaps_after_separator(
    qtbot: QtBot,
) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    snap = _submenu(menu, "Snap focused window")
    actions = snap.actions()

    # First N builtins, separator, one user preset.
    builtin_count = len(BUILTIN_SNAP_MENU_ITEMS)
    assert [a.text() for a in actions[:builtin_count]] == [
        lbl for _, lbl in BUILTIN_SNAP_MENU_ITEMS
    ]
    assert actions[builtin_count].isSeparator()
    assert actions[builtin_count + 1].text() == "my-center"


def test_pause_action_reflects_state(qtbot: QtBot) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    pause = next(a for a in menu.actions() if a.text() == "Pause Perch")
    assert pause.isCheckable()
    assert pause.isChecked()


# ── Intent emission ─────────────────────────────────────────────────────


def _trigger(menu: QMenu, text: str) -> None:
    """Trigger the top-level action with that text."""
    action = next(a for a in menu.actions() if a.text() == text)
    action.trigger()


def _trigger_sub(menu: QMenu, parent_text: str, child_text: str) -> None:
    submenu = _submenu(menu, parent_text)
    child = next(a for a in submenu.actions() if a.text() == child_text)
    child.trigger()


def test_quit_action_emits_quit_intent(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "Quit Perch")
    assert isinstance(blocker.args[0], Quit)


def test_reapply_rules_action_emits_reapply_intent(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "Reapply rules now")
    assert isinstance(blocker.args[0], ReapplyRules)


def test_pause_action_emits_toggle_intent(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "Pause Perch")
    assert isinstance(blocker.args[0], TogglePause)


def test_configure_action_emits_open_config_dialog(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "Configure Perch…")
    assert isinstance(blocker.args[0], OpenConfigDialog)


def test_open_config_folder_action_emits_open_folder(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "Open config folder")
    assert isinstance(blocker.args[0], OpenConfigFolder)


def test_about_action_emits_show_about(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger(menu, "About Perch")
    assert isinstance(blocker.args[0], ShowAbout)


def test_layout_selection_emits_activate_layout_intent(qtbot: QtBot) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger_sub(menu, "Layouts", "writing")
    intent = blocker.args[0]
    assert isinstance(intent, ActivateLayout)
    assert intent.name == "writing"


def test_layout_none_deactivates(qtbot: QtBot) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger_sub(menu, "Layouts", "(none)")
    intent = blocker.args[0]
    assert isinstance(intent, ActivateLayout)
    assert intent.name is None


def test_snap_selection_emits_snap_focused_intent(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger_sub(menu, "Snap focused window", "Left half")
    intent = blocker.args[0]
    assert isinstance(intent, SnapFocused)
    assert intent.preset == "left-half"


def test_user_snap_selection_emits_by_name(qtbot: QtBot) -> None:
    controller = TrayController(_populated_state())
    menu = build_tray_menu(controller.state, controller)
    qtbot.addWidget(menu)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        _trigger_sub(menu, "Snap focused window", "my-center")
    intent = blocker.args[0]
    assert isinstance(intent, SnapFocused)
    assert intent.preset == "my-center"


# ── Controller state management ──────────────────────────────────────────


def test_set_state_noop_when_unchanged(qtbot: QtBot) -> None:
    state = _empty_state()
    controller = TrayController(state)
    # Signal should not fire when identical state is pushed.
    # qtbot.assertNotEmitted is the idiomatic negative check but only
    # exists in pytest-qt 4.2+, which is satisfied here.
    with qtbot.assertNotEmitted(controller.state_changed, wait=100):
        controller.set_state(state)


def test_set_state_emits_state_changed(qtbot: QtBot) -> None:
    controller = TrayController(_empty_state())

    with qtbot.waitSignal(controller.state_changed, timeout=500):
        controller.set_state(_populated_state())

    assert controller.state.active_layout == "coding"


# ── TrayIcon integration (no real tray host) ─────────────────────────────


def test_tray_icon_rebuilds_menu_on_state_change(qtbot: QtBot) -> None:
    # Import locally — TrayIcon constructs a QSystemTrayIcon which is
    # fine under offscreen but not worth loading when most tests don't
    # need it.
    from perch.ui.tray import TrayIcon

    controller = TrayController(_empty_state())
    tray = TrayIcon(controller)
    # QSystemTrayIcon is a QObject not a QWidget; pytest-qt's addWidget
    # works regardless but skipping it here — Qt owns the lifetime via
    # parent=None and the test-local ref keeps it alive.

    first_menu = tray.contextMenu()
    assert first_menu is not None
    assert "idle" in first_menu.actions()[0].text()

    controller.set_state(_populated_state())

    new_menu = tray.contextMenu()
    assert new_menu is not first_menu
    assert "docked" in new_menu.actions()[0].text()

    # Explicit hide avoids a "QSystemTrayIcon::setVisible" warning at
    # teardown on offscreen platforms where show() is a silent no-op.
    tray.hide()


def test_tray_middle_click_toggles_pause(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QSystemTrayIcon

    from perch.ui.tray import TrayIcon

    controller = TrayController(_empty_state())
    tray = TrayIcon(controller)

    with qtbot.waitSignal(controller.intent, timeout=500) as blocker:
        tray._on_activated(QSystemTrayIcon.ActivationReason.MiddleClick)

    assert isinstance(blocker.args[0], TogglePause)
    tray.hide()
