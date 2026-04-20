"""Tests for :mod:`perch.core.state_store`.

Covers load/fallback-to-bak, atomic write semantics, schema versioning,
and the synchronous mutation API. Async debounce behaviour is exercised
via the reducer integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perch.backend.types import Geometry
from perch.core.state_store import (
    CURRENT_STATE_SCHEMA_VERSION,
    PersistedState,
    StateLoadError,
    StateStore,
)


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "state.json"


# ── Load ────────────────────────────────────────────────────────────────────
def test_load_missing_file_yields_empty_state(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    assert store.state.windows == {}
    assert store.state.active_profile is None


def test_load_valid_state(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active_profile": "Docked",
                "active_layout": None,
                "windows": {
                    "app:firefox": {
                        "identity": "app:firefox",
                        "geometry": {"x": 10, "y": 20, "w": 800, "h": 600},
                        "monitor": "DP-1",
                        "desktop": 1,
                        "last_seen": "2026-04-20T12:00:00+00:00",
                    }
                },
            }
        )
    )
    store = StateStore(state_path)
    store.load()
    assert store.state.active_profile == "Docked"
    record = store.state.windows["app:firefox"]
    assert record.geometry == Geometry(10, 20, 800, 600)


def test_load_falls_back_to_bak(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not json")
    bak = state_path.with_name(state_path.name + ".bak")
    bak.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "windows": {
                    "app:konsole": {
                        "identity": "app:konsole",
                        "geometry": {"x": 0, "y": 0, "w": 400, "h": 300},
                        "monitor": "DP-1",
                        "desktop": 0,
                        "last_seen": "2026-04-20T12:00:00+00:00",
                    }
                },
            }
        )
    )
    store = StateStore(state_path)
    store.load()
    assert "app:konsole" in store.state.windows


def test_load_future_version_rejected(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_STATE_SCHEMA_VERSION + 1,
                "windows": {},
            }
        )
    )
    # Surfaces as a warning + empty state — we never load a future-version file.
    store = StateStore(state_path)
    store.load()
    assert store.state.windows == {}


def test_persisted_state_from_json_raises_on_non_dict() -> None:
    with pytest.raises(StateLoadError, match="top-level must be an object"):
        PersistedState.from_json([])


# ── Mutations ───────────────────────────────────────────────────────────────
def test_record_window_marks_dirty(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    assert not store.is_dirty()
    store.record_window(
        "app:firefox", Geometry(0, 0, 800, 600), "DP-1", 0
    )
    assert store.is_dirty()
    assert store.state.windows["app:firefox"].geometry == Geometry(0, 0, 800, 600)


async def test_forget_window_removes_and_marks_dirty(
    state_path: Path,
) -> None:
    store = StateStore(state_path)
    store.load()
    store.record_window("app:x", Geometry(0, 0, 1, 1), "DP-1", 0)
    await store.flush()
    assert not store.is_dirty()
    store.forget_window("app:x")
    assert "app:x" not in store.state.windows
    assert store.is_dirty()  # removal re-dirties the store


async def test_set_active_deduplicates(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    store.set_active(profile="A", layout=None)
    assert store.is_dirty()
    await store.flush()
    assert not store.is_dirty()
    store.set_active(profile="A", layout=None)  # same values — no-op
    assert not store.is_dirty()


# ── Atomic flush ────────────────────────────────────────────────────────────
async def test_flush_writes_atomically(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    store.record_window(
        "app:firefox", Geometry(0, 0, 800, 600), "DP-1", 0
    )
    await store.flush()

    assert state_path.exists()
    raw = json.loads(state_path.read_text())
    assert raw["windows"]["app:firefox"]["geometry"]["w"] == 800


async def test_flush_noop_when_clean(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    await store.flush()
    # A no-op flush must not create a file.
    assert not state_path.exists()


async def test_flush_rotates_old_to_bak(state_path: Path) -> None:
    store = StateStore(state_path)
    store.load()
    store.record_window(
        "app:a", Geometry(0, 0, 100, 100), "DP-1", 0
    )
    await store.flush()

    store.record_window(
        "app:a", Geometry(10, 20, 100, 100), "DP-1", 0
    )
    await store.flush()

    assert state_path.exists()
    bak = state_path.with_name(state_path.name + ".bak")
    assert bak.exists()
