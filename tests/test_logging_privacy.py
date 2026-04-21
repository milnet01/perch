"""Tests for :mod:`perch.logging_privacy` (M7.e)."""

from __future__ import annotations

from perch.logging_privacy import redact_payload, summarize_keys


def test_redact_strips_title_from_dict() -> None:
    payload = {
        "id": "w1",
        "title": "Passwords — KeePass",
        "geometry": {"x": 0, "y": 0, "w": 100, "h": 100},
    }
    redacted = redact_payload(payload)
    assert redacted["title"] == "<redacted>"
    assert redacted["id"] == "w1"
    assert redacted["geometry"] == payload["geometry"]


def test_redact_strips_hyprland_initial_title_and_class() -> None:
    payload = {
        "address": "0x1",
        "title": "Email from someone@example.com",
        "initialTitle": "Email from someone@example.com",
        "initialClass": "firefox",
        "class": "firefox",
    }
    redacted = redact_payload(payload)
    for k in ("title", "initialTitle", "initialClass", "class"):
        assert redacted[k] == "<redacted>"


def test_redact_recurses_into_nested_dicts() -> None:
    payload = {"windows": [{"id": "w1", "title": "secret"}]}
    redacted = redact_payload(payload)
    assert redacted["windows"][0]["title"] == "<redacted>"
    assert redacted["windows"][0]["id"] == "w1"


def test_redact_preserves_empty_title_field() -> None:
    """An already-empty title isn't replaced with ``<redacted>`` noise."""
    redacted = redact_payload({"id": "w1", "title": ""})
    assert redacted["title"] == ""


def test_redact_passes_scalars_through_unchanged() -> None:
    assert redact_payload(None) is None
    assert redact_payload(42) == 42
    assert redact_payload("plain string") == "plain string"


def test_redact_handles_lists_and_tuples() -> None:
    payload = [{"title": "a"}, {"title": "b"}]
    assert [p["title"] for p in redact_payload(payload)] == [
        "<redacted>",
        "<redacted>",
    ]
    tup = redact_payload(({"title": "c"},))
    assert tup[0]["title"] == "<redacted>"


def test_summarize_keys_returns_sorted_keys() -> None:
    payload = {"title": "x", "id": "w1", "geometry": {}}
    assert summarize_keys(payload) == "keys=geometry,id,title"


def test_summarize_keys_on_list_returns_count() -> None:
    assert summarize_keys([1, 2, 3]) == "<list of 3>"


def test_summarize_keys_on_scalar_returns_type() -> None:
    assert summarize_keys(42) == "<int>"
    assert summarize_keys(None) == "<NoneType>"
