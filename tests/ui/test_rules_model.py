"""RulesModel unit tests — drag-reorder contract + delete."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, Qt

from perch.core.actions import ApplyAction, PercentGeometry, PresetGeometry
from perch.core.matching import MatchPattern
from perch.core.rules import Context, Rule
from perch.ui.rules_model import (
    COL_APPLY,
    COL_CONTEXT,
    COL_MATCH,
    COL_NAME,
    COLUMN_COUNT,
    RulesModel,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _rule(
    name: str | None,
    app_id: str | None = None,
    preset: str | None = None,
    profile: str | None = None,
) -> Rule:
    return Rule(
        name=name,
        match=MatchPattern(app_id=app_id),
        apply=ApplyAction(
            geometry=PresetGeometry(preset) if preset else None,
        ),
        context=Context(profile=profile),
    )


def test_row_and_column_counts() -> None:
    rules = [_rule("a", "firefox"), _rule("b", "konsole")]
    model = RulesModel(rules)
    assert model.rowCount() == 2
    assert model.columnCount() == COLUMN_COUNT


def test_display_data_summarises_each_column() -> None:
    rules = [_rule("Firefox maxed", app_id="firefox", preset="maximize")]
    model = RulesModel(rules)
    assert model.data(model.index(0, COL_NAME)) == "Firefox maxed"
    assert "app_id=firefox" in model.data(model.index(0, COL_MATCH))
    assert "preset:maximize" in model.data(model.index(0, COL_APPLY))


def test_unnamed_rule_shows_blank_name_column() -> None:
    model = RulesModel([_rule(None, app_id="foo")])
    assert model.data(model.index(0, COL_NAME)) == ""


def test_context_column_shows_any_when_unconstrained() -> None:
    model = RulesModel([_rule("r", app_id="foo")])
    assert model.data(model.index(0, COL_CONTEXT)) == "any"


def test_context_column_surfaces_profile_gate() -> None:
    model = RulesModel([_rule("r", app_id="foo", profile="docked")])
    assert "profile=docked" in model.data(model.index(0, COL_CONTEXT))


def test_apply_column_summarises_percent_geometry() -> None:
    rule = Rule(
        name="pct",
        match=MatchPattern(app_id="x"),
        apply=ApplyAction(geometry=PercentGeometry(0.0, 0.0, 0.5, 1.0)),
    )
    model = RulesModel([rule])
    assert "50%x100%+0%,0%" in model.data(model.index(0, COL_APPLY))


def test_header_data_uses_canonical_column_names() -> None:
    model = RulesModel([])
    assert (
        model.headerData(COL_NAME, Qt.Orientation.Horizontal)
        == "Name"
    )
    assert (
        model.headerData(COL_APPLY, Qt.Orientation.Horizontal)
        == "Apply"
    )
    # Vertical headers are 1-based row numbers.
    assert (
        model.headerData(0, Qt.Orientation.Vertical) == "1"
    )


# ── moveRows ────────────────────────────────────────────────────────────


def test_move_row_down_reorders_working_copy(qtbot: QtBot) -> None:
    a, b, c = _rule("a"), _rule("b"), _rule("c")
    model = RulesModel([a, b, c])

    # Move row 0 to position 2 (after b). Qt's drop-between semantics
    # says destination_row = 2 drops the payload at final index 1
    # because the row is removed from its current slot first.
    with qtbot.waitSignal(model.rowsMoved, timeout=500):
        assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 2)
    assert model.rules() == (b, a, c)


def test_move_row_up_reorders_working_copy(qtbot: QtBot) -> None:
    a, b, c = _rule("a"), _rule("b"), _rule("c")
    model = RulesModel([a, b, c])

    with qtbot.waitSignal(model.rowsMoved, timeout=500):
        assert model.moveRows(QModelIndex(), 2, 1, QModelIndex(), 0)
    assert model.rules() == (c, a, b)


def test_move_rejects_out_of_range_source() -> None:
    model = RulesModel([_rule("a"), _rule("b")])
    assert model.moveRows(QModelIndex(), 5, 1, QModelIndex(), 0) is False


def test_move_rejects_zero_count() -> None:
    model = RulesModel([_rule("a"), _rule("b")])
    assert model.moveRows(QModelIndex(), 0, 0, QModelIndex(), 1) is False


def test_move_rejects_drop_inside_moved_range() -> None:
    model = RulesModel([_rule("a"), _rule("b")])
    assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 0) is False
    assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 1) is False


# ── flags / drag config ─────────────────────────────────────────────────


def test_valid_index_is_drag_and_drop_enabled() -> None:
    model = RulesModel([_rule("a")])
    flags = model.flags(model.index(0, 0))
    assert bool(flags & Qt.ItemFlag.ItemIsDragEnabled)
    assert bool(flags & Qt.ItemFlag.ItemIsDropEnabled)


def test_invalid_index_is_drop_enabled_for_inter_row_targets() -> None:
    model = RulesModel([_rule("a")])
    flags = model.flags(QModelIndex())
    # Drop-between-rows targets an invalid parent; must still accept drops.
    assert bool(flags & Qt.ItemFlag.ItemIsDropEnabled)
    assert not bool(flags & Qt.ItemFlag.ItemIsDragEnabled)


def test_supports_move_as_only_drop_action() -> None:
    model = RulesModel([_rule("a")])
    assert model.supportedDropActions() == Qt.DropAction.MoveAction


# ── remove_rule ─────────────────────────────────────────────────────────


def test_remove_rule_drops_row(qtbot: QtBot) -> None:
    a, b, c = _rule("a"), _rule("b"), _rule("c")
    model = RulesModel([a, b, c])
    with qtbot.waitSignal(model.rowsRemoved, timeout=500):
        model.remove_rule(1)
    assert model.rules() == (a, c)


# ── permutation helper ──────────────────────────────────────────────────


def test_permutation_after_move(qtbot: QtBot) -> None:
    a, b, c = _rule("a"), _rule("b"), _rule("c")
    originals = [a, b, c]
    model = RulesModel(originals)
    model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 2)
    # Working copy is now [b, a, c]; permutation is the original indices
    # in that order: [1, 0, 2].
    assert model.permutation(originals) == [1, 0, 2]


def test_permutation_on_untouched_model_is_identity() -> None:
    originals = [_rule("a"), _rule("b")]
    model = RulesModel(originals)
    assert model.permutation(originals) == [0, 1]
