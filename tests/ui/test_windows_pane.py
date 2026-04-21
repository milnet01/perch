"""Tests for the WindowsPage and WindowsTableModel."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from perch.backend.mock import MockBackend
from perch.backend.types import (
    Geometry,
    OutputInfo,
    WindowInfo,
    WindowState,
    WindowType,
)
from perch.core.state_store import StateStore
from perch.ui.dialog import WindowsPage
from perch.ui.windows_model import (
    COL_GEOMETRY,
    COL_IDENTITY,
    COL_LAST_SEEN,
    COL_MONITOR,
    COL_TITLE,
    COLUMN_COUNT,
    WindowsTableModel,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot


def _window(
    wid: str, app_id: str, title: str, monitor: str = "HDMI-1", desktop: int = 0
) -> WindowInfo:
    return WindowInfo(
        id=wid,
        app_id=app_id,
        wm_class=app_id,
        title=title,
        pid=None,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(10, 20, 800, 600),
        monitor=monitor,
        desktop=desktop,
    )


def _output(name: str = "HDMI-1") -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=Geometry(0, 0, 1920, 1080),
        work_area=Geometry(0, 24, 1920, 1056),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=True,
        is_connected=True,
    )


# ── WindowsTableModel ───────────────────────────────────────────────────


def test_model_columns_cover_every_field() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    assert model.columnCount() == COLUMN_COUNT


def test_model_set_windows_populates_rows() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "Home"), _window("2", "konsole", "~")])
    assert model.rowCount() == 2
    assert model.data(model.index(0, COL_IDENTITY)) == "app:firefox"
    assert model.data(model.index(1, COL_IDENTITY)) == "app:konsole"


def test_model_title_and_monitor_display() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "My tab", "DP-2", 1)])
    assert model.data(model.index(0, COL_TITLE)) == "My tab"
    assert model.data(model.index(0, COL_MONITOR)) == "DP-2"


def test_model_geometry_formatted_wxh_at_xy() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "t")])
    assert model.data(model.index(0, COL_GEOMETRY)) == "800x600 @ (10, 20)"


def test_model_last_seen_column_uses_callback() -> None:
    seen = {"app:firefox"}
    model = WindowsTableModel(has_last_seen=lambda i: i in seen)
    model.set_windows(
        [_window("1", "firefox", "t"), _window("2", "konsole", "t")]
    )
    assert model.data(model.index(0, COL_LAST_SEEN)) == "✓"
    assert model.data(model.index(1, COL_LAST_SEEN)) == "—"


def test_model_upsert_inserts_new_then_updates_existing() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    info = _window("1", "firefox", "first")
    model.upsert(info)
    assert model.rowCount() == 1
    assert model.data(model.index(0, COL_TITLE)) == "first"

    model.upsert(replace(info, title="second"))
    assert model.rowCount() == 1
    assert model.data(model.index(0, COL_TITLE)) == "second"


def test_model_remove_drops_row() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "a"), _window("2", "konsole", "b")])
    model.remove("1")
    assert model.rowCount() == 1
    assert model.data(model.index(0, COL_IDENTITY)) == "app:konsole"


def test_model_remove_unknown_wid_noop() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "a")])
    model.remove("unknown")
    assert model.rowCount() == 1


def test_model_update_geometry_mutates_in_place() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "t")])
    model.update_geometry("1", Geometry(100, 200, 300, 400), "HDMI-2", 2)
    assert model.data(model.index(0, COL_GEOMETRY)) == "300x400 @ (100, 200)"
    assert model.data(model.index(0, COL_MONITOR)) == "HDMI-2"


def test_model_update_geometry_unknown_wid_noop() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "t")])
    model.update_geometry("nope", Geometry(0, 0, 1, 1), "X", 0)
    assert model.data(model.index(0, COL_GEOMETRY)) == "800x600 @ (10, 20)"


def test_model_desktop_all_renders_as_all() -> None:
    model = WindowsTableModel(has_last_seen=lambda _i: False)
    model.set_windows([_window("1", "firefox", "t", desktop=-1)])
    from perch.ui.windows_model import COL_DESKTOP

    assert model.data(model.index(0, COL_DESKTOP)) == "all"


# ── WindowsPage (page-level integration) ────────────────────────────────


@pytest.fixture
def backend() -> MockBackend:
    b = MockBackend()
    b._add_output(_output())
    return b


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "state.json")


def test_page_null_backend_shows_inactive_label(qtbot: QtBot) -> None:
    page = WindowsPage(backend=None, state_store=None)
    qtbot.addWidget(page)
    assert page.model is None
    assert page.view is None
    assert page.is_dirty() is False


def test_page_live_window_opened_adds_row(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    assert page.model is not None
    assert page.model.rowCount() == 0

    backend._spawn_window(_window("99", "konsole", "shell"))
    assert page.model.rowCount() == 1


def test_page_window_closed_removes_row(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    assert page.model is not None

    backend._spawn_window(_window("1", "firefox", "t"))
    assert page.model.rowCount() == 1

    backend._fire_close("1")
    assert page.model.rowCount() == 0


def test_page_geometry_changed_updates_row(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    assert page.model is not None

    backend._spawn_window(_window("1", "firefox", "t"))
    backend._move_window("1", Geometry(50, 50, 500, 500))
    assert page.model.data(page.model.index(0, COL_GEOMETRY)) == "500x500 @ (50, 50)"


def test_save_button_records_last_seen_and_dirties_page(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    backend._spawn_window(_window("1", "firefox", "t"))
    assert page.view is not None
    page.view.selectRow(0)
    page._on_save_clicked()

    assert store.get_last_seen("app:firefox") is not None
    assert page.is_dirty() is True


def test_forget_button_drops_last_seen(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    store.record_window("app:firefox", Geometry(0, 0, 10, 10), "HDMI-1", 0)
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    backend._spawn_window(_window("1", "firefox", "t"))
    assert page.view is not None
    page.view.selectRow(0)
    page._on_forget_clicked()

    assert store.get_last_seen("app:firefox") is None
    assert page.is_dirty() is True


def test_forget_button_disabled_when_no_last_seen(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    backend._spawn_window(_window("1", "firefox", "t"))
    assert page.view is not None
    page.view.selectRow(0)
    # selection triggers _update_button_state via the Qt signal
    assert page.save_button.isEnabled()
    assert not page.forget_button.isEnabled()


def test_commit_schedules_state_flush(
    qtbot: QtBot, backend: MockBackend, store: StateStore
) -> None:
    page = WindowsPage(backend=backend, state_store=store)
    qtbot.addWidget(page)
    backend._spawn_window(_window("1", "firefox", "t"))
    assert page.view is not None
    page.view.selectRow(0)
    page._on_save_clicked()

    assert page.is_dirty() is True
    page.commit()
    assert page.is_dirty() is False
    # mark_dirty was called; the store is flagged dirty until the
    # debounced flush or explicit flush lands.
    assert store.is_dirty() is True
