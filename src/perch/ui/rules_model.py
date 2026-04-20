"""Qt model for the Rules table in the config dialog.

Implements the design pinned in ``docs/08-ui.md`` §Rules — a
``QAbstractTableModel`` backed by a deep-copy of ``list[Rule]``, with
``moveRows`` wired to ``QAbstractItemView.InternalMove`` so rows drag-
reorder into a valid permutation. The working copy is owned here and
returned on OK; the caller's original list is untouched on Cancel, per
the deep-copy-on-open / replace-on-OK pattern.

Per-cell editing (match fields, apply fields, context fields) lands in
M3.c with the reusable widgets; M3.b's model is read-only at the cell
level and exposes reorder + delete.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from perch.core.actions import (
    AbsoluteGeometry,
    ApplyAction,
    PercentGeometry,
    PresetGeometry,
)
from perch.core.matching import MatchPattern
from perch.core.rules import Rule

_Index = QModelIndex | QPersistentModelIndex

COL_NAME: Final[int] = 0
COL_MATCH: Final[int] = 1
COL_APPLY: Final[int] = 2
COL_CONTEXT: Final[int] = 3
COLUMN_COUNT: Final[int] = 4

_COLUMN_HEADERS: tuple[str, ...] = ("Name", "Match", "Apply", "Context")


def _summarise_match(pattern: MatchPattern) -> str:
    """One-line summary of a ``MatchPattern`` for the Match column."""
    parts: list[str] = []
    if pattern.catch_all:
        parts.append("catch_all")
    if pattern.app_id is not None:
        parts.append(f"app_id={pattern.app_id}")
    if pattern.wm_class is not None:
        parts.append(f"wm_class={pattern.wm_class}")
    if pattern.title is not None:
        parts.append(f"title=~{pattern.title.pattern}")
    if pattern.pid is not None:
        parts.append(f"pid={pattern.pid}")
    if pattern.types:
        parts.append("type=" + ",".join(t.value for t in pattern.types))
    return " ".join(parts) or "<empty>"


def _summarise_geometry(expr: object) -> str:
    if isinstance(expr, AbsoluteGeometry):
        return f"{expr.w}x{expr.h}+{expr.x},{expr.y}"
    if isinstance(expr, PercentGeometry):
        return (
            f"{expr.w_pct * 100:.0f}%x{expr.h_pct * 100:.0f}%"
            f"+{expr.x_pct * 100:.0f}%,{expr.y_pct * 100:.0f}%"
        )
    if isinstance(expr, PresetGeometry):
        return f"preset:{expr.name}"
    return "-"


def _summarise_apply(action: ApplyAction) -> str:
    """One-line summary of an ``ApplyAction`` for the Apply column."""
    parts: list[str] = []
    if action.geometry is not None:
        parts.append(_summarise_geometry(action.geometry))
    if action.snap is not None:
        parts.append(f"snap={action.snap}")
    if action.monitor is not None:
        parts.append(f"monitor={action.monitor}")
    if action.desktop is not None:
        parts.append(f"desktop={action.desktop}")
    if action.maximized is True:
        parts.append("maximized")
    elif action.maximized is False:
        parts.append("unmaximize")
    return " ".join(parts) or "<no-op>"


def _summarise_context(rule: Rule) -> str:
    ctx = rule.context
    parts: list[str] = []
    if ctx.profile is not None:
        parts.append(f"profile={ctx.profile}")
    if ctx.layout is not None:
        parts.append(f"layout={ctx.layout}")
    if ctx.desktop is not None:
        parts.append(f"desktop={ctx.desktop}")
    return " ".join(parts) or "any"


class RulesModel(QAbstractTableModel):
    """Table model over a working copy of the rules list.

    The caller constructs the model with the current rules; the working
    copy is owned here and returned by :meth:`rules` at OK time. Mutation
    is reorder + delete only in M3.b — per-cell editing comes in M3.c
    once the reusable widgets land.
    """

    def __init__(
        self,
        rules: Sequence[Rule],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        # Rules are immutable ``frozen=True`` dataclasses so a shallow
        # copy of the list is enough — we never mutate a Rule in place.
        self._rules: list[Rule] = list(rules)

    # ── Qt model API ────────────────────────────────────────────────────
    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rules)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else COLUMN_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < COLUMN_COUNT
        ):
            return _COLUMN_HEADERS[section]
        if (
            orientation == Qt.Orientation.Vertical
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return str(section + 1)
        return None

    def data(
        self,
        index: _Index,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rules):
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        rule = self._rules[index.row()]
        col = index.column()
        if col == COL_NAME:
            return rule.name if rule.name is not None else ""
        if col == COL_MATCH:
            return _summarise_match(rule.match)
        if col == COL_APPLY:
            return _summarise_apply(rule.apply)
        if col == COL_CONTEXT:
            return _summarise_context(rule)
        return None

    def flags(self, index: _Index) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if not index.isValid():
            # Drop-between-rows targets "invalid" parent indices; allow drop.
            return base | Qt.ItemFlag.ItemIsDropEnabled
        return base | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def moveRows(
        self,
        source_parent: _Index,
        source_row: int,
        count: int,
        destination_parent: _Index,
        destination_row: int,
    ) -> bool:
        if count <= 0:
            return False
        if source_parent.isValid() or destination_parent.isValid():
            return False
        n = len(self._rules)
        if not 0 <= source_row < n:
            return False
        if source_row + count > n:
            return False
        if destination_row < 0 or destination_row > n:
            return False
        # Dropping onto a position within the moved range is a no-op.
        if source_row <= destination_row <= source_row + count:
            return False
        if not self.beginMoveRows(
            source_parent,
            source_row,
            source_row + count - 1,
            destination_parent,
            destination_row,
        ):
            return False
        moved = [self._rules.pop(source_row) for _ in range(count)]
        insert_at = (
            destination_row if destination_row < source_row else destination_row - count
        )
        for offset, rule in enumerate(moved):
            self._rules.insert(insert_at + offset, rule)
        self.endMoveRows()
        return True

    # ── Public helpers ──────────────────────────────────────────────────
    def rules(self) -> tuple[Rule, ...]:
        """Return the current working copy as an immutable tuple."""
        return tuple(self._rules)

    def permutation(self, original: Sequence[Rule]) -> list[int]:
        """Return the index permutation mapping ``original`` → current order.

        ``original`` must be the list the model was constructed from;
        otherwise :class:`ValueError` is raised. Two rules compare equal
        iff they are the same ``Rule`` *instance* — frozen dataclass
        equality could collide across distinct entries with identical
        fields, which would produce a wrong permutation.
        """
        id_to_index = {id(rule): i for i, rule in enumerate(original)}
        if len(id_to_index) != len(original):
            raise ValueError("original contains duplicate rule instances")
        out: list[int] = []
        for rule in self._rules:
            idx = id_to_index.get(id(rule))
            if idx is None:
                raise ValueError("current rules are not a permutation of original")
            out.append(idx)
        if sorted(out) != list(range(len(original))):
            raise ValueError(
                "current rules are not a permutation of original"
            )
        return out

    def remove_rule(self, row: int) -> None:
        """Remove the rule at ``row`` from the working copy."""
        if not 0 <= row < len(self._rules):
            raise IndexError(f"rule row {row} out of range")
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._rules[row]
        self.endRemoveRows()


__all__ = [
    "COLUMN_COUNT",
    "COL_APPLY",
    "COL_CONTEXT",
    "COL_MATCH",
    "COL_NAME",
    "RulesModel",
]
