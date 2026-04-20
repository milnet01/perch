"""Unit tests for the JSON command / response codecs in ``protocol.py``."""

from __future__ import annotations

import json

import pytest

from perch.backend.kwin.protocol import (
    CommandError,
    decode_output_entry,
    decode_window_info,
    encode_command,
    encode_nop,
    op_batch,
    op_close_window,
    op_query_windows,
    op_set_desktop,
    op_set_frame_geometry,
    op_set_full_screen,
    op_set_maximize_mode,
    op_set_minimized,
    unwrap_ok,
)
from perch.backend.types import Geometry, WindowState, WindowType


def test_op_set_frame_geometry_includes_only_present_fields() -> None:
    op = op_set_frame_geometry("id-1", Geometry(10, 20, 300, 400))
    assert op == {"op": "setFrameGeometry", "id": "id-1", "x": 10, "y": 20, "w": 300, "h": 400}
    assert "output" not in op
    assert "preplace" not in op


def test_op_set_frame_geometry_preserves_output_and_preplace() -> None:
    op = op_set_frame_geometry(
        "id-1", Geometry(0, 0, 100, 100), output="HDMI-A-1", preplace=True
    )
    assert op["output"] == "HDMI-A-1"
    assert op["preplace"] is True


def test_op_set_maximize_mode_coerces_bools() -> None:
    op = op_set_maximize_mode("id-1", 1, 0)  # type: ignore[arg-type]
    assert op == {"op": "setMaximizeMode", "id": "id-1", "vertical": True, "horizontal": False}


@pytest.mark.parametrize(
    ("builder", "expected_op"),
    [
        (lambda: op_set_full_screen("w", True), "setFullScreen"),
        (lambda: op_set_minimized("w", False), "setMinimized"),
        (lambda: op_set_desktop("w", 2), "setDesktop"),
        (lambda: op_close_window("w"), "closeWindow"),
        (op_query_windows, "queryWindows"),
    ],
)
def test_op_builders_set_correct_op_name(builder: object, expected_op: str) -> None:
    assert callable(builder)
    op = builder()
    assert op["op"] == expected_op


def test_encode_command_stamps_seq_and_is_deterministic() -> None:
    encoded = encode_command(7, {"op": "closeWindow", "id": "x"})
    data = json.loads(encoded)
    assert data == {"op": "closeWindow", "id": "x", "seq": 7}


def test_encode_nop_without_reason_omits_the_field() -> None:
    data = json.loads(encode_nop())
    assert data == {"nop": True}
    assert "reason" not in data


def test_encode_nop_with_reason_includes_it() -> None:
    data = json.loads(encode_nop(reason="invalidated"))
    assert data == {"nop": True, "reason": "invalidated"}


def test_op_batch_wraps_ops_without_mutating_inputs() -> None:
    ops = [op_close_window("a"), op_close_window("b")]
    wrapped = op_batch(ops)
    ops.append(op_close_window("c"))  # should not leak into wrapped
    assert wrapped["batch"] == [
        {"op": "closeWindow", "id": "a"},
        {"op": "closeWindow", "id": "b"},
    ]


def test_decode_window_info_builds_expected_shape() -> None:
    payload = {
        "id": "qUuId-1",
        "app_id": "firefox",
        "wm_class": "firefox",
        "title": "Hi",
        "pid": 42,
        "type": "normal",
        "state": "normal",
        "x": 10,
        "y": 20,
        "w": 300,
        "h": 400,
        "output": "HDMI-A-1",
        "desktop": 1,
        "role": "browser",
    }
    info = decode_window_info(payload)
    assert info.id == "qUuId-1"
    assert info.app_id == "firefox"
    assert info.title == "Hi"
    assert info.pid == 42
    assert info.type is WindowType.NORMAL
    assert info.state is WindowState.NORMAL
    assert info.geometry == Geometry(10, 20, 300, 400)
    assert info.monitor == "HDMI-A-1"
    assert info.desktop == 1
    assert info.role == "browser"


def test_decode_window_info_recovers_from_unknown_type_or_state() -> None:
    payload = {
        "id": "x",
        "type": "exotic-menu-2",
        "state": "frobbing",
    }
    info = decode_window_info(payload)
    assert info.type is WindowType.UNKNOWN
    assert info.state is WindowState.NORMAL


def test_decode_window_info_treats_zero_pid_as_missing() -> None:
    # KWin script falls back to 0 when window.pid is undefined; Perch stores None.
    info = decode_window_info({"id": "x", "pid": 0})
    assert info.pid is None


def test_decode_output_entry_uses_expected_defaults() -> None:
    out = decode_output_entry({"name": "HDMI-A-1", "x": 0, "y": 0, "w": 1920, "h": 1080})
    assert out["name"] == "HDMI-A-1"
    assert out["geometry"] == Geometry(0, 0, 1920, 1080)
    assert out["scale"] == 1.0  # default
    assert out["refresh_mhz"] == 0  # default


def test_unwrap_ok_returns_dict_on_success() -> None:
    r = unwrap_ok({"ok": True, "extra": 1})
    assert r["extra"] == 1


def test_unwrap_ok_raises_command_error_with_kind() -> None:
    with pytest.raises(CommandError) as excinfo:
        unwrap_ok({"ok": False, "error": "unknown_window", "id": "x"})
    assert excinfo.value.kind == "unknown_window"
    assert excinfo.value.detail["id"] == "x"


def test_unwrap_ok_raises_on_malformed_result() -> None:
    with pytest.raises(CommandError) as excinfo:
        unwrap_ok("not-a-dict")  # type: ignore[arg-type]
    assert excinfo.value.kind == "malformed_result"
