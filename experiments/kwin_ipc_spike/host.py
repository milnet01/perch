"""Perch M2.5 KWin IPC spike — the Python half.

Implements the Python side of the long-poll pattern described in
``docs/05-backend-kwin.md``: owns the ``io.github.milnet01.Perch.spike`` bus
name, exports the ``io.github.milnet01.Perch.spike.KWin1`` interface at
``/KWin``, and holds ``PollCommand`` replies until a command is queued (up to
a 5 s heartbeat ceiling).

This is spike code. It is not loaded from the shipped ``perch`` package; it
lives under ``experiments/`` and is invoked by ``harness.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from sdbus import (  # type: ignore[import-untyped]
    DbusInterfaceCommonAsync,
    dbus_method_async,
    request_default_bus_name_async,
)

BUS_NAME = "io.github.milnet01.Perch.spike"
OBJ_PATH = "/KWin"
IFACE = "io.github.milnet01.Perch.spike.KWin1"
POLL_CEILING_SECONDS = 5.0

log = logging.getLogger("perch.spike.host")


@dataclass(slots=True)
class Counters:
    """Visible state of the host across a run. Read by the harness for reports."""

    window_added: int = 0
    poll_requests: int = 0
    poll_ceiling_returns: int = 0
    commands_dispatched: int = 0
    commands_completed: int = 0
    latencies_ns: list[int] = field(default_factory=list)


class PerchSpikeKWin1(  # type: ignore[misc]
    DbusInterfaceCommonAsync,
    interface_name=IFACE,
):
    """Service exported on /KWin. Methods here are invoked by the JS script."""

    def __init__(self) -> None:
        super().__init__()
        self.counters = Counters()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._completions: dict[int, tuple[asyncio.Future[str], int]] = {}
        self._next_seq = 0
        self._invalidated: asyncio.Event = asyncio.Event()
        self.script_ready = asyncio.Event()

    def invalidate_polls(self) -> None:
        """Wake any in-flight PollCommand handler with a no-op reply.

        Must be called whenever the JS script is about to be unloaded or
        reloaded; without it, an orphan PollCommand awaiter from the old
        script instance will happily consume the next real command queued
        for the *new* instance, and that command's reply will be routed to
        nobody. Bumping the Event atomically swaps in a fresh one so that
        PollCommand calls landing *after* the swap see a pristine slate.
        """
        old = self._invalidated
        self._invalidated = asyncio.Event()
        old.set()

    @dbus_method_async(input_signature="s", result_signature="")
    async def WindowAdded(self, _payload: str) -> None:
        self.counters.window_added += 1

    @dbus_method_async(input_signature="", result_signature="s")
    async def PollCommand(self) -> str:
        self.counters.poll_requests += 1
        invalidated = self._invalidated  # snapshot: survives swap by invalidate_polls
        get_task = asyncio.create_task(self._queue.get())
        inv_task = asyncio.create_task(invalidated.wait())
        try:
            done, _ = await asyncio.wait(
                {get_task, inv_task},
                timeout=POLL_CEILING_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for t in (get_task, inv_task):
                if not t.done():
                    t.cancel()
        if get_task in done and not get_task.cancelled():
            return get_task.result()
        if inv_task in done:
            return json.dumps({"nop": True, "reason": "invalidated"})
        self.counters.poll_ceiling_returns += 1
        return json.dumps({"nop": True})

    @dbus_method_async(input_signature="s", result_signature="")
    async def CommandDone(self, payload: str) -> None:
        self.counters.commands_completed += 1
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            log.warning("CommandDone: malformed payload: %r", payload)
            return
        seq = data.get("seq")
        entry = self._completions.pop(seq, None) if isinstance(seq, int) else None
        if entry is None:
            return
        fut, start_ns = entry
        self.counters.latencies_ns.append(time.monotonic_ns() - start_ns)
        if not fut.done():
            fut.set_result(str(data.get("result", "")))

    @dbus_method_async(input_signature="s", result_signature="")
    async def ScriptReady(self, _payload: str) -> None:
        self.script_ready.set()

    async def echo(self, value: str, timeout: float = 5.0) -> str:
        """Drive one round-trip: queue an echo command, wait for CommandDone."""
        loop = asyncio.get_running_loop()
        self._next_seq += 1
        seq = self._next_seq
        fut: asyncio.Future[str] = loop.create_future()
        self._completions[seq] = (fut, time.monotonic_ns())
        self.counters.commands_dispatched += 1
        await self._queue.put(json.dumps({"seq": seq, "echo": value}))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._completions.pop(seq, None)
            raise

    def pending_replies(self) -> int:
        """Outstanding echoes awaiting CommandDone. Harness uses this to detect leaks."""
        return len(self._completions)


async def start_host() -> PerchSpikeKWin1:
    """Acquire the bus name and export the interface. Returns the live service."""
    await request_default_bus_name_async(BUS_NAME)
    iface = PerchSpikeKWin1()
    iface.export_to_dbus(OBJ_PATH)
    log.info("spike host up: %s at %s", BUS_NAME, OBJ_PATH)
    return iface
