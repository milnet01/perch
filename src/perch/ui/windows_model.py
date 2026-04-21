"""QAbstractTableModel for the Windows pane of the settings dialog.

One row per currently-managed window. Columns map to the live
``WindowInfo`` fields plus a derived "has last-seen" flag that probes
``StateStore`` so the user can see at a glance which identities Perch
already remembers and which are first-time.

The model owns a short list — typical desktop sessions have a few dozen
windows at most — so a flat ``list[WindowInfo]`` backed with a lookup
dict keyed by ``WindowId`` is all the indexing we need. Incremental
updates via ``upsert`` / ``remove`` emit the narrow ``dataChanged``
signals that keep ``QTableView`` scroll position stable during live
updates.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from perch.backend.types import Geometry, WindowId, WindowInfo
from perch.core.identity import compute_identity

_Index = QModelIndex | QPersistentModelIndex

COL_IDENTITY = 0
COL_TITLE = 1
COL_MONITOR = 2
COL_GEOMETRY = 3
COL_DESKTOP = 4
COL_LAST_SEEN = 5
COLUMN_COUNT = 6


def _format_geometry(geom: Geometry) -> str:
    """Human-readable one-line geometry string used in the Geometry column."""
    return f"{geom.w}x{geom.h} @ ({geom.x}, {geom.y})"


def _format_desktop(desktop: int) -> str:
    """Desktop index as a short label; ``-1`` renders as ``all`` per docs/02."""
    if desktop == -1:
        return "all"
    return str(desktop)


class WindowsTableModel(QAbstractTableModel):
    """Live table of currently-open windows the backend reports.

    Construct with a ``has_last_seen`` callable so the model stays
    ignorant of the :class:`~perch.core.state_store.StateStore` type
    (the dialog does the binding). The callable takes an identity
    string and returns ``True`` when a last-seen record exists.
    """

    def __init__(
        self,
        has_last_seen: Callable[[str], bool],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._has_last_seen = has_last_seen
        self._order: list[WindowId] = []
        self._info: dict[WindowId, WindowInfo] = {}

    # ── Public API ──────────────────────────────────────────────────────
    def set_windows(self, windows: list[WindowInfo]) -> None:
        """Replace the current window list wholesale. Used on page open."""
        self.beginResetModel()
        self._order = [w.id for w in windows]
        self._info = {w.id: w for w in windows}
        self.endResetModel()

    def upsert(self, info: WindowInfo) -> None:
        """Insert or update ``info``. Emits the narrowest signal possible."""
        if info.id in self._info:
            self._info[info.id] = info
            row = self._order.index(info.id)
            top = self.index(row, 0)
            bottom = self.index(row, COLUMN_COUNT - 1)
            self.dataChanged.emit(top, bottom)
            return
        row = len(self._order)
        self.beginInsertRows(QModelIndex(), row, row)
        self._order.append(info.id)
        self._info[info.id] = info
        self.endInsertRows()

    def remove(self, wid: WindowId) -> None:
        if wid not in self._info:
            return
        row = self._order.index(wid)
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._order[row]
        del self._info[wid]
        self.endRemoveRows()

    def update_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: str,
        desktop: int,
    ) -> None:
        """Mutate the row's geometry/monitor/desktop without reshuffling."""
        info = self._info.get(wid)
        if info is None:
            return
        from dataclasses import replace

        self._info[wid] = replace(
            info, geometry=geom, monitor=monitor, desktop=desktop
        )
        row = self._order.index(wid)
        top = self.index(row, COL_MONITOR)
        bottom = self.index(row, COL_DESKTOP)
        self.dataChanged.emit(top, bottom)

    def refresh_last_seen(self) -> None:
        """Repaint the Last-seen column — called after record/forget actions."""
        if not self._order:
            return
        top = self.index(0, COL_LAST_SEEN)
        bottom = self.index(len(self._order) - 1, COL_LAST_SEEN)
        self.dataChanged.emit(top, bottom)

    def window_at(self, row: int) -> WindowInfo | None:
        if 0 <= row < len(self._order):
            return self._info[self._order[row]]
        return None

    # ── QAbstractTableModel overrides ───────────────────────────────────
    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._order)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return COLUMN_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation != Qt.Orientation.Horizontal:
            return None
        headers = {
            COL_IDENTITY: self.tr("Identity"),
            COL_TITLE: self.tr("Title"),
            COL_MONITOR: self.tr("Monitor"),
            COL_GEOMETRY: self.tr("Geometry"),
            COL_DESKTOP: self.tr("Desktop"),
            COL_LAST_SEEN: self.tr("Last-seen"),
        }
        return headers.get(section)

    def data(
        self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        info = self.window_at(index.row())
        if info is None:
            return None
        col = index.column()
        if col == COL_IDENTITY:
            return compute_identity(info)
        if col == COL_TITLE:
            return info.title
        if col == COL_MONITOR:
            return info.monitor
        if col == COL_GEOMETRY:
            return _format_geometry(info.geometry)
        if col == COL_DESKTOP:
            return _format_desktop(info.desktop)
        if col == COL_LAST_SEEN:
            return "✓" if self._has_last_seen(compute_identity(info)) else "—"
        return None
