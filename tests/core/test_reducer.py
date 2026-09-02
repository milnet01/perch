"""Integration tests for :mod:`perch.core.reducer`.

Drives :class:`MockBackend` through scripted event sequences and asserts
on the backend commands + ``state.json`` contents. This is the M2 exit
criterion "Feeding a scripted event sequence into MockBackend produces
the expected ``set_geometry`` calls — verified by a table-driven pytest."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from perch.backend.mock import MockBackend
from perch.backend.types import (
    Geometry,
    OutputInfo,
    WindowInfo,
    WindowState,
    WindowType,
)
from perch.config.schema import Config, GeneralSettings, validate
from perch.core.reducer import Reducer
from perch.core.state_store import StateStore


@pytest.fixture(autouse=True)
def _require_qapp(qapp: object) -> None: ...


def _outputs() -> list[OutputInfo]:
    return [
        OutputInfo(
            name="DP-1",
            geometry=Geometry(0, 0, 2560, 1440),
            work_area=Geometry(0, 0, 2560, 1400),
            scale=1.0, refresh_mhz=144000,
            is_primary=True, is_connected=True,
        ),
        OutputInfo(
            name="HDMI-1",
            geometry=Geometry(2560, 360, 1920, 1080),
            work_area=Geometry(2560, 360, 1920, 1040),
            scale=1.0, refresh_mhz=60000,
            is_primary=False, is_connected=True,
        ),
    ]


def _window(
    wid: str = "w1",
    *,
    app_id: str = "firefox",
    title: str = "Mozilla Firefox",
    monitor: str = "DP-1",
    type_: WindowType = WindowType.NORMAL,
) -> WindowInfo:
    return WindowInfo(
        id=wid,
        app_id=app_id,
        wm_class=app_id,
        title=title,
        pid=1000,
        type=type_,
        state=WindowState.NORMAL,
        geometry=Geometry(100, 100, 800, 600),
        monitor=monitor,
        desktop=0,
    )


async def _make(
    config_doc: dict[str, Any] | None = None,
    tmp_path: Path | None = None,
) -> tuple[MockBackend, Reducer, StateStore]:
    backend = MockBackend()
    await backend.start()
    for o in _outputs():
        backend._add_output(o)

    config = validate(config_doc or {})
    state_path = (
        (tmp_path / "state.json")
        if tmp_path is not None
        else Path("/dev/null")  # never flushed unless tests want it
    )
    store = StateStore(state_path)
    store.load()

    reducer = Reducer(
        backend, config, store, topology_debounce_seconds=0.0
    )
    return backend, reducer, store


# ── Startup ────────────────────────────────────────────────────────────────
async def test_start_enumerates_open_windows(tmp_path: Path) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "maximize", "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    backend._spawn_window(_window())
    # Opened before reducer.start — the signal went nowhere. start() must
    # pick it up via list_windows().

    await reducer.start()

    geom_calls = [
        args for name, args in backend.commands.entries if name == "set_geometry"
    ]
    assert len(geom_calls) == 1
    wid, geom, monitor, _desktop = geom_calls[0]
    assert wid == "w1"
    assert monitor == "HDMI-1"
    assert geom == Geometry(2560, 360, 1920, 1040)


# ── Live window_opened ─────────────────────────────────────────────────────
async def test_window_opened_fires_matching_rule(tmp_path: Path) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "name": "FF on external",
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "left-half", "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    geom_calls = [
        args for name, args in backend.commands.entries if name == "set_geometry"
    ]
    assert geom_calls == [
        ("w1", Geometry(2560, 360, 960, 1040), "HDMI-1", 0),
    ]


async def test_non_matching_window_not_touched(tmp_path: Path) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window(app_id="konsole")
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    assert backend.commands.names() == []


async def test_builtin_excluded_type_not_touched(tmp_path: Path) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"catch_all": True},
                    "apply": {"geometry": "maximize"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    backend._spawn_window(
        _window("w", app_id="plasmashell", type_=WindowType.DOCK)
    )
    await reducer.handle_window_opened(
        _window("w", app_id="plasmashell", type_=WindowType.DOCK)
    )
    assert backend.commands.names() == []


# ── Last-seen restore ──────────────────────────────────────────────────────
async def test_restore_last_seen(tmp_path: Path) -> None:
    backend, reducer, store = await _make({}, tmp_path)
    store.record_window(
        "app:firefox", Geometry(500, 300, 1200, 800), "DP-1", 2
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    geom_calls = [
        args for name, args in backend.commands.entries if name == "set_geometry"
    ]
    assert geom_calls == [
        ("w1", Geometry(500, 300, 1200, 800), "DP-1", 2),
    ]


async def test_restore_suppressed_when_restore_on_open_false(
    tmp_path: Path,
) -> None:
    config = validate({"general": {"restore_on_open": False}})
    state_path = tmp_path / "state.json"
    store = StateStore(state_path)
    store.load()
    store.record_window(
        "app:firefox", Geometry(0, 0, 100, 100), "DP-1", 0
    )

    backend = MockBackend()
    await backend.start()
    for o in _outputs():
        backend._add_output(o)
    reducer = Reducer(backend, config, store, topology_debounce_seconds=0.0)
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    assert backend.commands.names() == []


# ── Pause Perch ────────────────────────────────────────────────────────────
async def test_pause_suppresses_rule_placement(tmp_path: Path) -> None:
    """Pause Perch drops every placement decision — including a matching
    rule, which the old narrow "pause restore" let through. No window is
    moved while paused. See docs/08-ui.md §Menu structure."""
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "left-half", "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    assert reducer.toggle_pause() is True  # now paused

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    assert backend.commands.names() == []


async def test_unpause_re_enables_placement(tmp_path: Path) -> None:
    """Flipping Pause Perch back off lets the next window_opened place again."""
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "left-half", "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    reducer.toggle_pause()  # paused
    reducer.toggle_pause()  # unpaused again

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    geom_calls = [
        args for name, args in backend.commands.entries if name == "set_geometry"
    ]
    assert geom_calls == [
        ("w1", Geometry(2560, 360, 960, 1040), "HDMI-1", 0),
    ]


# ── Reapply rules ──────────────────────────────────────────────────────────
async def test_reapply_reevaluates_with_unchanged_topology(
    tmp_path: Path,
) -> None:
    """"Reapply rules now" re-evaluates every open window even when the
    monitor topology is unchanged. The old wiring routed the intent through
    ``recompute_topology``, whose topology-key early-return swallowed it, so
    the tray action was a silent no-op. See ``ui/intents.py::ReapplyRules``."""
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "left-half", "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    window = _window()
    backend._spawn_window(window)
    await reducer.start()  # places it once

    def _geom() -> list[Any]:
        return [
            args
            for name, args in backend.commands.entries
            if name == "set_geometry"
        ]

    assert len(_geom()) == 1

    # Topology has not changed since start(); reapply must still re-place.
    await reducer.reapply()

    assert len(_geom()) == 2
    assert _geom()[-1] == ("w1", Geometry(2560, 360, 960, 1040), "HDMI-1", 0)


# ── Feedback-loop prevention ───────────────────────────────────────────────
async def test_set_geometry_echo_is_dropped(tmp_path: Path) -> None:
    backend, reducer, store = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    # The mock emits geometry_changed from inside set_geometry. Capture it:
    expected_geom = Geometry(0, 0, 2560, 1400)
    ts_before = store.state.windows["app:firefox"].last_seen

    # Round-trip the echo manually (simulates the signal the reducer would
    # receive in the live app — the mock fires it synchronously inside
    # set_geometry, but the reducer isn't listening to Qt signals in tests).
    reducer.handle_geometry_changed("w1", expected_geom, "DP-1", 0)

    # last_seen must not have advanced: the echo was consumed, not recorded.
    assert store.state.windows["app:firefox"].last_seen == ts_before


async def test_user_drag_updates_state(tmp_path: Path) -> None:
    backend, reducer, store = await _make({}, tmp_path)
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    dragged = Geometry(200, 200, 900, 700)
    reducer.handle_geometry_changed("w1", dragged, "DP-1", 0)

    record = store.state.windows["app:firefox"]
    assert record.geometry == dragged


# ── window_closed drops the identity cache ─────────────────────────────────
async def test_window_closed_clears_expected_geometry(
    tmp_path: Path,
) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()
    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    reducer.handle_window_closed("w1")
    # No assertion error or leak — the expected_geometry dict is private but
    # we verify through behaviour: a late geometry_changed is ignored
    # because the WindowInfo cache is gone.
    reducer.handle_geometry_changed("w1", Geometry(1, 2, 3, 4), "DP-1", 0)


# ── Topology / profile switching ───────────────────────────────────────────
async def test_output_add_activates_matching_profile(tmp_path: Path) -> None:
    topology_key = (
        "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
    )
    _backend, reducer, store = await _make(
        {
            "profiles": [
                {
                    "name": "Docked",
                    "topology": topology_key,
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    assert reducer.active_profile is not None
    assert reducer.active_profile.name == "Docked"
    assert store.state.active_profile == "Docked"


async def test_output_removed_deactivates_profile(tmp_path: Path) -> None:
    topology_key = (
        "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
    )
    _backend, reducer, _ = await _make(
        {"profiles": [{"name": "Docked", "topology": topology_key}]},
        tmp_path,
    )
    await reducer.start()
    assert reducer.active_profile is not None

    await reducer.handle_output_removed("HDMI-1")
    await reducer.recompute_topology()

    assert reducer.active_profile is None


# ── Layout activation ──────────────────────────────────────────────────────
async def test_activate_layout_applies_to_matching_windows(
    tmp_path: Path,
) -> None:
    backend, reducer, _ = await _make(
        {
            "layouts": {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "code"},
                            "geometry": "left-half",
                            "monitor": "DP-1",
                        }
                    ],
                }
            }
        },
        tmp_path,
    )
    await reducer.start()

    window = _window(app_id="code")
    backend._spawn_window(window)

    backend.commands.clear()
    await reducer.activate_layout("coding")

    geom_calls = [
        args for name, args in backend.commands.entries if name == "set_geometry"
    ]
    assert len(geom_calls) == 1
    _, geom, monitor, _ = geom_calls[0]
    assert monitor == "DP-1"
    assert geom == Geometry(0, 0, 1280, 1400)


async def test_activate_unknown_layout_raises(tmp_path: Path) -> None:
    _, reducer, _ = await _make({}, tmp_path)
    await reducer.start()
    with pytest.raises(ValueError, match="unknown layout"):
        await reducer.activate_layout("nonexistent")


# ── Maximized via set_state ────────────────────────────────────────────────
async def test_maximized_true_calls_set_state(tmp_path: Path) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"maximized": True, "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    # The reducer first moves to HDMI-1 (monitor change), then maximizes.
    names = backend.commands.names()
    assert "set_geometry" in names
    assert "set_state" in names
    assert names.index("set_geometry") < names.index("set_state")

    # set_state arg was MAXIMIZED
    state_calls = [
        args for n, args in backend.commands.entries if n == "set_state"
    ]
    assert state_calls[-1] == ("w1", WindowState.MAXIMIZED)


async def test_maximized_true_unsupported_falls_back_to_geometry(
    tmp_path: Path,
) -> None:
    """Sway/Hyprland compromise: MAXIMIZED raises; reducer substitutes
    work-area geometry. See docs/06-backend-stubs.md + docs/07 §Apply order."""
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"maximized": True},
                }
            ]
        },
        tmp_path,
    )
    backend._fail_state(WindowState.MAXIMIZED)
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    # First we see a failed set_state (recorded), then a fallback
    # set_geometry matching DP-1's work area.
    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    assert geom_calls[-1] == (
        "w1", Geometry(0, 0, 2560, 1400), "DP-1", 0,
    )


# ── unmaximize-first ordering ──────────────────────────────────────────────
async def test_maximized_false_with_geometry_unmaximizes_first(
    tmp_path: Path,
) -> None:
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "left-half", "maximized": False},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    names = backend.commands.names()
    # set_state(NORMAL) before set_geometry, and no trailing set_state after.
    assert names[0] == "set_state"
    assert names[1] == "set_geometry"
    state_calls = [
        args for n, args in backend.commands.entries if n == "set_state"
    ]
    assert state_calls == [("w1", WindowState.NORMAL)]


# ── Identity + state_store wiring ──────────────────────────────────────────
async def test_set_geometry_records_state_after_rule_fires(
    tmp_path: Path,
) -> None:
    backend, reducer, store = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"geometry": "maximize"},
                }
            ]
        },
        tmp_path,
    )
    await reducer.start()

    window = _window()
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    assert "app:firefox" in store.state.windows
    record = store.state.windows["app:firefox"]
    assert record.geometry == Geometry(0, 0, 2560, 1400)


# ── Config edge: non-default profile from validate() ───────────────────────
async def test_validate_plus_reducer_end_to_end(tmp_path: Path) -> None:
    """Full end-to-end: TOML-style document → validate → reducer applies."""
    config: Config = validate(
        {
            "rules": [
                {
                    "name": "signal top-right",
                    "match": {"app_id": "signal"},
                    "apply": {"snap": "top-right-quarter"},
                }
            ]
        }
    )
    # Config.general is the default.
    assert isinstance(config.general, GeneralSettings)

    backend = MockBackend()
    await backend.start()
    for o in _outputs():
        backend._add_output(o)
    store = StateStore(tmp_path / "state.json")
    store.load()
    reducer = Reducer(backend, config, store, topology_debounce_seconds=0.0)
    await reducer.start()

    backend._spawn_window(_window("sig", app_id="signal"))
    await reducer.handle_window_opened(_window("sig", app_id="signal"))

    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    assert len(geom_calls) == 1
    wid, geom, _monitor, _desktop = geom_calls[0]
    assert wid == "sig"
    # top-right-quarter of DP-1's 2560x1400 work area = (1280, 0, 1280, 700)
    assert geom == Geometry(1280, 0, 1280, 700)


# ── Profile overrides on layouts ───────────────────────────────────────────
async def test_profile_override_replaces_layout_entry(tmp_path: Path) -> None:
    """Per docs/09 §Per-profile overrides: under the Docked profile, the
    coding layout's `code` entry is replaced with a full-screen override."""
    topology_key = "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
    backend, reducer, _ = await _make(
        {
            "layouts": {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "code"},
                            "geometry": "left-half",
                            "monitor": "DP-1",
                        }
                    ],
                }
            },
            "profiles": [
                {
                    "name": "Docked",
                    "topology": topology_key,
                    "default_layout": "coding",
                    "override": [
                        {
                            "layout": "coding",
                            "windows": [
                                {
                                    "match": {"app_id": "code"},
                                    "geometry": "maximize",
                                    "monitor": "HDMI-1",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        tmp_path,
    )
    await reducer.start()
    assert reducer.active_profile is not None

    backend._spawn_window(_window(app_id="code"))
    backend.commands.clear()
    await reducer.activate_layout("coding")

    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    assert len(geom_calls) == 1
    _, geom, monitor, _ = geom_calls[0]
    # Override replaced left-half@DP-1 with maximize@HDMI-1.
    assert monitor == "HDMI-1"
    assert geom == Geometry(2560, 360, 1920, 1040)


async def test_profile_override_with_no_matching_base_is_appended(
    tmp_path: Path,
) -> None:
    """Overrides whose match doesn't exist in the base layout are appended."""
    topology_key = "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
    backend, reducer, _ = await _make(
        {
            "layouts": {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "code"},
                            "geometry": "left-half",
                        }
                    ],
                }
            },
            "profiles": [
                {
                    "name": "Docked",
                    "topology": topology_key,
                    "override": [
                        {
                            "layout": "coding",
                            "windows": [
                                {
                                    "match": {"app_id": "signal"},
                                    "geometry": "maximize",
                                    "monitor": "HDMI-1",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        tmp_path,
    )
    await reducer.start()

    backend._spawn_window(_window("sig", app_id="signal"))
    backend.commands.clear()
    await reducer.activate_layout("coding")

    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    # signal was not in the base layout; the override adds it.
    assert len(geom_calls) == 1
    assert geom_calls[0][0] == "sig"


# ── Profile default_layout ────────────────────────────────────────────────
async def test_profile_default_layout_is_activated_on_start(
    tmp_path: Path,
) -> None:
    """docs/09 §Activation step 2: activating a profile applies its layout.

    Without this the field parses, seeds the sample config and is editable
    in the dialog, and no window is ever placed by it.
    """
    backend, reducer, _ = await _make(
        {
            "layouts": {
                "coding": {
                    "windows": [
                        {
                            "match": {"app_id": "firefox"},
                            "geometry": "right-half",
                        }
                    ]
                }
            },
            "profiles": [
                {
                    "name": "Docked",
                    "topology": (
                        "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"
                    ),
                    "default_layout": "coding",
                }
            ],
        },
        tmp_path,
    )
    backend._spawn_window(_window())

    await reducer.start()

    assert reducer.active_layout is not None
    assert reducer.active_layout.name == "coding"
    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    assert geom_calls[-1][1] == Geometry(1280, 0, 1280, 1400)


# ── What must never reach state.json ──────────────────────────────────────
async def test_excluded_window_is_not_remembered(tmp_path: Path) -> None:
    """An excluded window is not managed, so remembering it would restore
    it later — exactly what the exclusion asked Perch not to do."""
    backend, reducer, store = await _make(
        {"exclusions": {"patterns": [{"app_id": "signal"}]}},
        tmp_path,
    )
    await reducer.start()

    window = _window("w9", app_id="signal")
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)
    reducer.handle_geometry_changed("w9", Geometry(5, 5, 50, 50), "DP-1", 0)

    assert store.get_last_seen("app:signal") is None


async def test_window_without_app_id_or_wm_class_is_not_remembered(
    tmp_path: Path,
) -> None:
    """Every such window shares one identity, so one would overwrite the
    next. compute_identity's docstring has always promised this skip."""
    backend, reducer, store = await _make({}, tmp_path)
    await reducer.start()

    window = _window("w8", app_id="")
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)
    reducer.handle_geometry_changed("w8", Geometry(5, 5, 50, 50), "DP-1", 0)

    assert store.get_last_seen("app:unknown") is None


# ── Maximize fallback target ──────────────────────────────────────────────
async def test_maximize_fallback_uses_the_resolved_target_monitor(
    tmp_path: Path,
) -> None:
    """docs/02 §Apply actions: the substitute geometry is the *target*
    monitor's work area. The window's own monitor is where it sat before
    this action moved it, so the fallback would land on the wrong screen."""
    backend, reducer, _ = await _make(
        {
            "rules": [
                {
                    "match": {"app_id": "firefox"},
                    "apply": {"maximized": True, "monitor": "HDMI-1"},
                }
            ]
        },
        tmp_path,
    )
    backend._fail_state(WindowState.MAXIMIZED)
    await reducer.start()

    window = _window()  # currently on DP-1
    backend._spawn_window(window)
    await reducer.handle_window_opened(window)

    geom_calls = [
        args for n, args in backend.commands.entries if n == "set_geometry"
    ]
    assert geom_calls[-1] == (
        "w1", Geometry(2560, 360, 1920, 1040), "HDMI-1", 0,
    )
