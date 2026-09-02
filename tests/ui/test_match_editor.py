"""MatchEditor widget tests."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from perch.backend.types import WindowType
from perch.core.matching import MatchPattern
from perch.ui.widgets.match_editor import MatchEditor

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_default_value_is_empty_pattern(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    value = editor.value()
    assert value == MatchPattern()


def test_set_pattern_populates_every_field(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    pattern = MatchPattern(
        app_id="firefox",
        wm_class="Firefox*",
        title=re.compile(r"Mozilla.*"),
        pid=1234,
        types=(WindowType.NORMAL, WindowType.DIALOG),
        catch_all=False,
    )
    editor.set_pattern(pattern)
    got = editor.value()
    assert got.app_id == "firefox"
    assert got.wm_class == "Firefox*"
    assert got.title is not None and got.title.pattern == r"Mozilla.*"
    assert got.pid == 1234
    assert set(got.types) == {WindowType.NORMAL, WindowType.DIALOG}
    assert got.catch_all is False


def test_catch_all_round_trips(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.set_pattern(MatchPattern(catch_all=True))
    assert editor.value().catch_all is True


def test_value_changed_fires_on_app_id_edit(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    with qtbot.waitSignal(editor.valueChanged, timeout=500):
        editor.app_id_edit.setText("chromium")
    assert editor.value().app_id == "chromium"


def test_invalid_regex_marks_editor_invalid(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    with qtbot.waitSignal(editor.validityChanged, timeout=500) as sig:
        editor.title_edit.setText("(")  # unterminated group
    assert sig.args == [False]
    assert not editor.is_valid()
    assert editor.title_edit.toolTip()  # error tooltip set


def test_fixing_invalid_regex_restores_validity(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.title_edit.setText("(")
    assert not editor.is_valid()

    with qtbot.waitSignal(editor.validityChanged, timeout=500) as sig:
        editor.title_edit.setText("ok")
    assert sig.args == [True]
    assert editor.is_valid()


def test_invalid_pid_text_marks_invalid(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.pid_edit.setText("not-a-number")
    assert not editor.is_valid()


def test_negative_pid_rejected(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.pid_edit.setText("-1")
    assert not editor.is_valid()


def test_type_checkboxes_translate_to_tuple(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.type_checkboxes[WindowType.NORMAL].setChecked(True)
    editor.type_checkboxes[WindowType.DIALOG].setChecked(True)
    assert set(editor.value().types) == {WindowType.NORMAL, WindowType.DIALOG}


def test_empty_fields_return_none_not_empty_string(qtbot: QtBot) -> None:
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.app_id_edit.setText("")
    editor.wm_class_edit.setText("")
    editor.title_edit.setText("")
    editor.pid_edit.setText("")
    got = editor.value()
    assert got.app_id is None
    assert got.wm_class is None
    assert got.title is None
    assert got.pid is None


def test_catch_all_with_another_field_is_refused(qtbot: QtBot) -> None:
    """The widget builds the dataclass directly, bypassing ``parse_match``.

    Without this guard the dialog would happily write a config the loader
    then refuses, leaving the user with a Perch that will not start.
    """
    editor = MatchEditor()
    qtbot.addWidget(editor)
    editor.catch_all_checkbox.setChecked(True)
    editor.app_id_edit.setText("firefox")
    with pytest.raises(ValueError, match="catch-all"):
        editor.value()
