"""Tests for :mod:`perch.core.profiles`.

Covers the topology key computation, the parser, and the first-match-wins
activation rule. Authoritative spec: ``docs/09-layouts-profiles.md``.
"""

from __future__ import annotations

import pytest

from perch.backend.types import Geometry, OutputInfo
from perch.core.profiles import (
    Profile,
    ProfileOverride,
    ProfileValidationError,
    compute_topology_key,
    parse_profiles,
    select_profile,
)


def _output(
    name: str,
    *,
    x: int = 0,
    y: int = 0,
    w: int = 1920,
    h: int = 1080,
    connected: bool = True,
) -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=Geometry(x, y, w, h),
        work_area=Geometry(x, y, w, h - 40),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=(name == "DP-1"),
        is_connected=connected,
    )


# ── compute_topology_key ────────────────────────────────────────────────────
def test_topology_key_single_output() -> None:
    key = compute_topology_key([_output("eDP-1", w=1920, h=1200)])
    assert key == "eDP-1:1920x1200@0,0"


def test_topology_key_two_outputs_sorted_alphabetically() -> None:
    # Pass in reverse name order on purpose — the key must still be sorted.
    key = compute_topology_key(
        [
            _output("HDMI-1", x=2560, y=360, w=1920, h=1080),
            _output("DP-1", x=0, y=0, w=2560, h=1440),
        ]
    )
    assert key == "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360"


def test_topology_key_drops_disconnected_outputs() -> None:
    key = compute_topology_key(
        [
            _output("DP-1", w=2560, h=1440),
            _output("HDMI-1", x=2560, w=1920, h=1080, connected=False),
        ]
    )
    assert key == "DP-1:2560x1440@0,0"


def test_topology_key_empty_when_no_outputs() -> None:
    assert compute_topology_key([]) == ""


def test_topology_key_empty_when_all_disconnected() -> None:
    assert compute_topology_key([_output("DP-1", connected=False)]) == ""


def test_topology_key_handles_negative_coords() -> None:
    """Some compositors place secondary outputs at negative x (left of primary)."""
    key = compute_topology_key(
        [
            _output("DP-1", x=0, y=0, w=1920, h=1080),
            _output("eDP-1", x=-1920, y=0, w=1920, h=1080),
        ]
    )
    assert key == "DP-1:1920x1080@0,0;eDP-1:1920x1080@-1920,0"


# ── parse_profiles: happy path + overrides ──────────────────────────────────
def test_parse_profiles_minimal() -> None:
    [p] = parse_profiles(
        [{"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"}]
    )
    assert p == Profile(name="Laptop", topology="eDP-1:1920x1200@0,0")


def test_parse_profiles_with_default_layout_and_override() -> None:
    [p] = parse_profiles(
        [
            {
                "name": "Docked",
                "topology": "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360",
                "default_layout": "coding",
                "override": [
                    {
                        "layout": "coding",
                        "windows": [
                            {
                                "match": {"app_id": "code"},
                                "geometry": {
                                    "x": "0%", "y": "0%",
                                    "w": "100%", "h": "100%",
                                    "monitor": "DP-1",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    )
    assert p.default_layout == "coding"
    assert len(p.overrides) == 1
    override = p.overrides[0]
    assert isinstance(override, ProfileOverride)
    assert override.layout == "coding"
    assert override.windows[0]["match"] == {"app_id": "code"}


def test_parse_profiles_empty_returns_empty() -> None:
    assert parse_profiles([]) == []


# ── parse_profiles: rejection cases ─────────────────────────────────────────
def test_parse_profiles_rejects_missing_name() -> None:
    with pytest.raises(ProfileValidationError, match="missing 'name'"):
        parse_profiles([{"topology": "eDP-1:1920x1200@0,0"}])


def test_parse_profiles_rejects_missing_topology() -> None:
    with pytest.raises(ProfileValidationError, match="missing 'topology'"):
        parse_profiles([{"name": "X"}])


def test_parse_profiles_rejects_empty_name() -> None:
    with pytest.raises(ProfileValidationError, match="must not be empty"):
        parse_profiles([{"name": "", "topology": "eDP-1:1920x1200@0,0"}])


def test_parse_profiles_rejects_non_string_name() -> None:
    with pytest.raises(ProfileValidationError, match="must be a string"):
        parse_profiles([{"name": 42, "topology": "eDP-1:1920x1200@0,0"}])


def test_parse_profiles_rejects_duplicate_name() -> None:
    with pytest.raises(ProfileValidationError, match="duplicate profile name"):
        parse_profiles(
            [
                {"name": "X", "topology": "eDP-1:1920x1200@0,0"},
                {"name": "X", "topology": "DP-1:2560x1440@0,0"},
            ]
        )


def test_parse_profiles_rejects_duplicate_topology() -> None:
    """docs/09 §Edge cases: duplicate topology is a validation error."""
    with pytest.raises(ProfileValidationError, match="already used"):
        parse_profiles(
            [
                {"name": "A", "topology": "eDP-1:1920x1200@0,0"},
                {"name": "B", "topology": "eDP-1:1920x1200@0,0"},
            ]
        )


@pytest.mark.parametrize(
    "bad_topology,reason",
    [
        ("", "must not be empty"),
        ("HDMI-1:1920x1080@0,0;DP-1:2560x1440@0,0", "sorted alphabetically"),
        ("DP-1:1920x1080@0,0;DP-1:1920x1080@0,0", "duplicate segments"),
        ("DP-1:1920x@0,0", "malformed"),
        ("DP-1-1920x1080-0-0", "malformed"),
    ],
)
def test_parse_profiles_rejects_malformed_topology(
    bad_topology: str, reason: str
) -> None:
    with pytest.raises(ProfileValidationError, match=reason):
        parse_profiles([{"name": "X", "topology": bad_topology}])


def test_parse_profiles_rejects_unknown_keys() -> None:
    with pytest.raises(ProfileValidationError, match="unknown keys"):
        parse_profiles(
            [
                {
                    "name": "X",
                    "topology": "eDP-1:1920x1200@0,0",
                    "typo_here": True,
                }
            ]
        )


def test_parse_profiles_rejects_malformed_override() -> None:
    with pytest.raises(ProfileValidationError, match="missing 'layout'"):
        parse_profiles(
            [
                {
                    "name": "X",
                    "topology": "eDP-1:1920x1200@0,0",
                    "override": [{"windows": []}],
                }
            ]
        )


def test_parse_profiles_rejects_override_not_list() -> None:
    with pytest.raises(
        ProfileValidationError, match="must be an array of tables"
    ):
        parse_profiles(
            [
                {
                    "name": "X",
                    "topology": "eDP-1:1920x1200@0,0",
                    "override": "not-a-list",
                }
            ]
        )


# ── select_profile ──────────────────────────────────────────────────────────
def test_select_profile_matches_topology() -> None:
    profiles = parse_profiles(
        [
            {"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"},
            {
                "name": "Docked",
                "topology": "DP-1:2560x1440@0,0;HDMI-1:1920x1080@2560,360",
            },
        ]
    )
    p = select_profile(profiles, "eDP-1:1920x1200@0,0")
    assert p is not None and p.name == "Laptop"


def test_select_profile_no_match_returns_none() -> None:
    profiles = parse_profiles(
        [{"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"}]
    )
    assert select_profile(profiles, "DP-1:2560x1440@0,0") is None


def test_select_profile_empty_key_returns_none() -> None:
    """Empty topology (no outputs) never activates a named profile."""
    profiles = parse_profiles(
        [{"name": "Laptop", "topology": "eDP-1:1920x1200@0,0"}]
    )
    assert select_profile(profiles, "") is None


def test_select_profile_empty_list_returns_none() -> None:
    assert select_profile([], "DP-1:2560x1440@0,0") is None


def test_select_profile_roundtrip_with_compute() -> None:
    """Compute → select is the canonical runtime path; must round-trip."""
    outputs = [
        _output("DP-1", x=0, y=0, w=2560, h=1440),
        _output("HDMI-1", x=2560, y=360, w=1920, h=1080),
    ]
    profiles = parse_profiles(
        [
            {
                "name": "Docked",
                "topology": compute_topology_key(outputs),
            }
        ]
    )
    assert select_profile(profiles, compute_topology_key(outputs)) == profiles[0]
