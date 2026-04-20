"""Exercises :class:`PerchKWin1` without a live D-Bus connection.

We instantiate the service directly (no ``export_to_dbus``) and call its
``@dbus_method_async`` methods as ordinary coroutines. This covers the
long-poll loop, the ``execute`` round-trip, poll invalidation, and event
routing into the sink.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from perch.backend.kwin.protocol import op_close_window
from perch.backend.kwin.service import POLL_CEILING_SECONDS, PerchKWin1


@dataclass
class _RecordingSink:
    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    geom: list[dict[str, Any]] = field(default_factory=list)
    props: list[dict[str, Any]] = field(default_factory=list)
    outputs_changed: int = 0
    ready: list[dict[str, Any]] = field(default_factory=list)

    def on_window_added(self, payload: dict[str, Any]) -> None:
        self.added.append(payload)

    def on_window_removed(self, payload: dict[str, Any]) -> None:
        self.removed.append(payload)

    def on_window_geometry_changed(self, payload: dict[str, Any]) -> None:
        self.geom.append(payload)

    def on_window_properties_changed(self, payload: dict[str, Any]) -> None:
        self.props.append(payload)

    def on_outputs_changed(self) -> None:
        self.outputs_changed += 1

    def on_script_ready(self, payload: dict[str, Any]) -> None:
        self.ready.append(payload)


# ── Inbound events route to the sink ───────────────────────────────────────


async def test_window_added_routes_decoded_payload_to_sink() -> None:
    sink = _RecordingSink()
    svc = PerchKWin1(sink)
    await svc.WindowAdded(json.dumps({"id": "w-1", "app_id": "firefox"}))
    assert sink.added == [{"id": "w-1", "app_id": "firefox"}]
    assert svc.counters.window_added == 1


async def test_malformed_payload_is_dropped_without_raising() -> None:
    sink = _RecordingSink()
    svc = PerchKWin1(sink)
    await svc.WindowAdded("not-json")
    # Counter still increments (we saw the call); sink got nothing.
    assert svc.counters.window_added == 1
    assert sink.added == []


async def test_outputs_changed_bumps_sink_regardless_of_payload() -> None:
    sink = _RecordingSink()
    svc = PerchKWin1(sink)
    await svc.OutputsChanged("")
    await svc.OutputsChanged("irrelevant")
    assert sink.outputs_changed == 2


async def test_script_ready_sets_event_and_notifies_sink() -> None:
    sink = _RecordingSink()
    svc = PerchKWin1(sink)
    assert not svc.script_ready.is_set()
    await svc.ScriptReady(json.dumps({"version": "1.0.0"}))
    assert svc.script_ready.is_set()
    assert sink.ready == [{"version": "1.0.0"}]


# ── Long-poll loop ─────────────────────────────────────────────────────────


async def test_poll_command_returns_queued_command() -> None:
    sink = _RecordingSink()
    svc = PerchKWin1(sink)
    # Queue via execute() running in the background; it stamps the seq.
    exec_task = asyncio.create_task(svc.execute(op_close_window("w")))
    # Give execute() a tick to push onto the queue.
    await asyncio.sleep(0)
    reply = await svc.PollCommand()
    data = json.loads(reply)
    assert data["op"] == "closeWindow"
    assert data["id"] == "w"
    assert isinstance(data["seq"], int)
    # Deliver the result so execute() doesn't leak.
    await svc.CommandDone(json.dumps({"seq": data["seq"], "result": {"ok": True}}))
    result = await exec_task
    assert result == {"ok": True}


async def test_poll_command_returns_nop_after_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Shrink the ceiling to keep the test fast; monkeypatch the module constant.
    import perch.backend.kwin.service as service_mod

    monkeypatch.setattr(service_mod, "POLL_CEILING_SECONDS", 0.1)
    svc = PerchKWin1(_RecordingSink())
    reply = await svc.PollCommand()
    data = json.loads(reply)
    assert data == {"nop": True}
    assert svc.counters.poll_ceiling_returns == 1


async def test_poll_ceiling_constant_is_5_seconds_at_module_level() -> None:
    # Regression guard: the spike recorded exactly 5 s; changing it changes the
    # observed heartbeat rate in SPIKE_RESULTS.md.
    assert POLL_CEILING_SECONDS == 5.0


async def test_invalidate_polls_wakes_in_flight_handler() -> None:
    svc = PerchKWin1(_RecordingSink())
    poll_task = asyncio.create_task(svc.PollCommand())
    await asyncio.sleep(0)  # let PollCommand enter the wait
    svc.invalidate_polls()
    reply = await asyncio.wait_for(poll_task, timeout=1.0)
    data = json.loads(reply)
    assert data == {"nop": True, "reason": "invalidated"}
    assert svc.counters.poll_invalidated_returns == 1


async def test_invalidate_polls_fresh_handlers_see_clean_slate() -> None:
    """After invalidation, a brand-new PollCommand must not be fired by the
    same event — it must wait on the freshly-swapped Event until the next
    command (or ceiling)."""
    svc = PerchKWin1(_RecordingSink())
    svc.invalidate_polls()  # no in-flight handler; just rotates the event
    # New handler should wait normally; we verify that it doesn't return
    # immediately with the "invalidated" marker.
    poll_task = asyncio.create_task(svc.PollCommand())
    await asyncio.sleep(0.05)
    assert not poll_task.done()
    # Queue a real command; the poll resolves with it.
    exec_task = asyncio.create_task(svc.execute(op_close_window("w"), timeout=2.0))
    await asyncio.sleep(0)
    reply = await asyncio.wait_for(poll_task, timeout=2.0)
    data = json.loads(reply)
    assert data["op"] == "closeWindow"
    await svc.CommandDone(json.dumps({"seq": data["seq"], "result": {"ok": True}}))
    await exec_task


# ── execute / CommandDone correlation ──────────────────────────────────────


async def test_command_done_unknown_seq_is_ignored(caplog: pytest.LogCaptureFixture) -> None:
    svc = PerchKWin1(_RecordingSink())
    # No execute() call; so no matching seq exists.
    await svc.CommandDone(json.dumps({"seq": 999, "result": {"ok": True}}))
    # Counter still increments; nothing blows up.
    assert svc.counters.commands_completed == 1


async def test_command_done_with_malformed_result_yields_error_dict() -> None:
    svc = PerchKWin1(_RecordingSink())
    exec_task = asyncio.create_task(svc.execute(op_close_window("w"), timeout=2.0))
    await asyncio.sleep(0)
    # Drain the queue so the seq gets assigned.
    reply = await svc.PollCommand()
    data = json.loads(reply)
    seq = data["seq"]
    # Reply has ``result`` not being a dict:
    await svc.CommandDone(json.dumps({"seq": seq, "result": "not-a-dict"}))
    result = await exec_task
    assert result["ok"] is False
    assert result["error"] == "malformed_result"


async def test_execute_times_out_if_command_done_never_arrives() -> None:
    svc = PerchKWin1(_RecordingSink())
    with pytest.raises(TimeoutError):
        await svc.execute(op_close_window("w"), timeout=0.1)
    # Pending completion pruned on timeout so it doesn't leak.
    assert svc.pending_replies() == 0


async def test_reset_completion_state_cancels_pending_futures() -> None:
    svc = PerchKWin1(_RecordingSink())
    # Use a long timeout so the test doesn't race the normal TimeoutError path.
    exec_task = asyncio.create_task(svc.execute(op_close_window("w"), timeout=10.0))
    await asyncio.sleep(0)
    svc.reset_completion_state()
    with pytest.raises(asyncio.CancelledError):
        await exec_task
    assert svc.pending_replies() == 0


async def test_latency_ns_is_recorded_for_each_round_trip() -> None:
    svc = PerchKWin1(_RecordingSink())
    exec_task = asyncio.create_task(svc.execute(op_close_window("w"), timeout=2.0))
    await asyncio.sleep(0)
    data = json.loads(await svc.PollCommand())
    await svc.CommandDone(json.dumps({"seq": data["seq"], "result": {"ok": True}}))
    await exec_task
    assert len(svc.counters.latencies_ns) == 1
    assert svc.counters.latencies_ns[0] > 0
