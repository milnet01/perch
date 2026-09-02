"""Hyprland backend tests that need no live compositor."""

from __future__ import annotations

import pytest

from perch.backend.hyprland import backend as hypr


# ── Instance signature is a path component (PERC-0050) ────────────────────
def test_signature_rejects_a_traversing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is joined under $XDG_RUNTIME_DIR and, on older Hyprland, /tmp.

    A value carrying a separator walks out of the runtime directory and
    points the socket probe at a path the caller chose.
    """
    monkeypatch.setenv(hypr.HYPRLAND_SIGNATURE_ENV, "../../etc")
    assert hypr._signature() is None

    monkeypatch.setenv(hypr.HYPRLAND_SIGNATURE_ENV, "..")
    assert hypr._signature() is None

    monkeypatch.setenv(hypr.HYPRLAND_SIGNATURE_ENV, "sig/with/slash")
    assert hypr._signature() is None


def test_signature_accepts_a_real_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(hypr.HYPRLAND_SIGNATURE_ENV, "v0.41.2_1712345678")
    assert hypr._signature() == "v0.41.2_1712345678"


def test_socket_paths_are_none_without_a_usable_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(hypr.HYPRLAND_SIGNATURE_ENV, "../..")
    assert hypr._socket_paths() is None
