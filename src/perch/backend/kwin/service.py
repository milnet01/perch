"""The Python side of the ``io.github.milnet01.Perch.KWin1`` D-Bus service.

Export-side counterpart to ``src/perch/backend/kwin/script/contents/code/main.js``.
Methods here are invoked *by the JS script* via ``callDBus``; Python holds the
``PollCommand`` reply until a command is queued (or up to a ~5 s heartbeat
ceiling) and correlates ``CommandDone`` payloads back to the awaiter that
enqueued the matching ``seq``.

Poll-invalidation semantics mirror the M2.5 spike (see
``experiments/kwin_ipc_spike/host.py``) — required so that when the script is
unloaded / reloaded, orphan ``PollCommand`` handlers from the old script
instance don't consume the first command queued for the new one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from sdbus import DbusInterfaceCommonAsync, dbus_method_async, get_current_message

from . import INTERFACE_NAME, OBJECT_PATH, SERVICE_NAME
from .protocol import encode_command, encode_nop

log = logging.getLogger("perch.backend.kwin.service")

#: Maximum time a ``PollCommand`` handler blocks waiting for a command.
#: KWin keeps D-Bus callback objects alive only while they're in flight; if
#: we hold one open forever the reply could be GC'd on some configurations.
#: Matches the value from the M2.5 spike.
POLL_CEILING_SECONDS = 5.0


class EventSink(Protocol):
    """Delivery target for decoded inbound events.

    The :class:`KWinBackend` implements this and emits Qt signals from each
    call. Keeping the interface narrow means :class:`PerchKWin1` stays
    testable without a Qt application.
    """

    def on_window_added(self, payload: dict[str, Any]) -> None: ...
    def on_window_removed(self, payload: dict[str, Any]) -> None: ...
    def on_window_geometry_changed(self, payload: dict[str, Any]) -> None: ...
    def on_window_properties_changed(self, payload: dict[str, Any]) -> None: ...
    def on_outputs_changed(self) -> None: ...
    def on_script_ready(self, payload: dict[str, Any]) -> None: ...


@dataclass(slots=True)
class ServiceCounters:
    """Visible counters for diagnostics / tests."""

    window_added: int = 0
    window_removed: int = 0
    window_geometry_changed: int = 0
    window_properties_changed: int = 0
    outputs_changed: int = 0
    poll_requests: int = 0
    poll_ceiling_returns: int = 0
    poll_invalidated_returns: int = 0
    commands_dispatched: int = 0
    commands_completed: int = 0
    foreign_calls: int = 0
    latencies_ns: list[int] = field(default_factory=list)


class PerchKWin1(
    DbusInterfaceCommonAsync,
    interface_name=INTERFACE_NAME,
):
    """Exports ``io.github.milnet01.Perch.KWin1`` on ``/KWin``.

    All methods take a single ``s`` argument (JSON-encoded dict, per the
    KWin bug 486024 workaround). ``PollCommand`` is the only method that
    returns data; the rest are fire-and-forget.
    """

    def __init__(self, sink: EventSink) -> None:
        super().__init__()
        self._sink = sink
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._completions: dict[int, tuple[asyncio.Future[dict[str, Any]], int]] = {}
        self._next_seq: int = 0
        self._invalidated: asyncio.Event = asyncio.Event()
        self.script_ready: asyncio.Event = asyncio.Event()
        # Unique bus name of the KWin script, pinned on its ScriptReady.
        # ``None`` until then, and while it is None every caller is
        # accepted — there is nothing yet to compare against.
        self._script_sender: str | None = None
        self.counters: ServiceCounters = ServiceCounters()

    # ── Lifecycle helpers (called by the backend) ──────────────────────────

    def invalidate_polls(self) -> None:
        """Wake every in-flight ``PollCommand`` with a ``{"nop": true}`` reply.

        Called before :meth:`KWinScripting.unload_script` so that orphan
        awaiters from the old JS instance don't consume the next command
        queued for the new one. Atomically swaps in a fresh
        :class:`asyncio.Event`: handlers landing *after* the swap see a
        clean slate; handlers already blocked on the old event wake up and
        return the nop reply.
        """
        old = self._invalidated
        self._invalidated = asyncio.Event()
        old.set()

    def reset_completion_state(self) -> None:
        """Fail every pending command with :class:`asyncio.CancelledError`.

        Used when the backend is shutting down — if we just drop the
        futures the caller awaits on them forever. Distinct from
        :meth:`invalidate_polls` (which wakes the script-side long-poll)
        because a shutdown must abort both the script-side pump *and* the
        backend-side awaiters.
        """
        for fut, _ in self._completions.values():
            if not fut.done():
                fut.cancel()
        self._completions.clear()

    async def execute(self, cmd: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
        """Queue a command, await its reply, return the parsed ``result`` dict.

        ``cmd`` must have an ``op`` (single op) or ``batch`` (list of ops)
        key but must *not* supply ``seq`` — the sequence number is stamped
        here. Raises :class:`TimeoutError` if no ``CommandDone`` for the
        matching ``seq`` arrives within ``timeout`` seconds, and
        :class:`asyncio.CancelledError` if the service is torn down first.
        """
        loop = asyncio.get_running_loop()
        self._next_seq += 1
        seq = self._next_seq
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._completions[seq] = (fut, time.monotonic_ns())
        self.counters.commands_dispatched += 1
        await self._queue.put(encode_command(seq, cmd))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._completions.pop(seq, None)
            raise

    def pending_replies(self) -> int:
        """Number of commands dispatched with no ``CommandDone`` yet."""
        return len(self._completions)

    async def export(self) -> None:
        """Expose the service on the session bus at :data:`OBJECT_PATH`.

        Thin wrapper so the backend can do ``await self.service.export()``
        without importing ``export_to_dbus`` directly.
        """
        self.export_to_dbus(OBJECT_PATH)

    # ── D-Bus methods invoked by the JS script ─────────────────────────────

    def _from_script(self) -> bool:
        """False when this call came from someone other than the script.

        The service sits on the session bus, so any process at the same UID
        can call it — and these methods feed the reducer and the state
        store. Perch loads the script itself, so the first caller, the one
        that sends ``ScriptReady``, is the real one; every later call has
        to arrive from the same unique bus name.

        ``docs/security-standards.md`` puts a same-UID attacker out of
        scope, so this is cheap insurance rather than a boundary. A call
        made with no D-Bus message in flight — the tests drive these
        methods directly — is allowed through, because there is no sender
        to compare and refusing would only break the caller that is
        already inside the process.
        """
        expected = self._script_sender
        if expected is None:
            return True
        sender = _current_sender()
        if sender is None or sender == expected:
            return True
        self.counters.foreign_calls += 1
        log.warning(
            "dropping call from %r: the KWin script is %r", sender, expected
        )
        return False

    @dbus_method_async(input_signature="s", result_signature="")
    async def WindowAdded(self, payload: str) -> None:
        if not self._from_script():
            return
        self.counters.window_added += 1
        data = _safe_json(payload)
        if data is not None:
            self._sink.on_window_added(data)

    @dbus_method_async(input_signature="s", result_signature="")
    async def WindowRemoved(self, payload: str) -> None:
        if not self._from_script():
            return
        self.counters.window_removed += 1
        data = _safe_json(payload)
        if data is not None:
            self._sink.on_window_removed(data)

    @dbus_method_async(input_signature="s", result_signature="")
    async def WindowGeometryChanged(self, payload: str) -> None:
        if not self._from_script():
            return
        self.counters.window_geometry_changed += 1
        data = _safe_json(payload)
        if data is not None:
            self._sink.on_window_geometry_changed(data)

    @dbus_method_async(input_signature="s", result_signature="")
    async def WindowPropertiesChanged(self, payload: str) -> None:
        if not self._from_script():
            return
        self.counters.window_properties_changed += 1
        data = _safe_json(payload)
        if data is not None:
            self._sink.on_window_properties_changed(data)

    @dbus_method_async(input_signature="s", result_signature="")
    async def OutputsChanged(self, _payload: str) -> None:
        if not self._from_script():
            return
        self.counters.outputs_changed += 1
        self._sink.on_outputs_changed()

    @dbus_method_async(input_signature="s", result_signature="")
    async def ScriptReady(self, payload: str) -> None:
        # First contact pins the sender for every later call. A second
        # ScriptReady from a different name is refused rather than allowed
        # to re-pin, or the check would be one call away from useless.
        if not self._from_script():
            return
        if self._script_sender is None:
            self._script_sender = _current_sender()
        data = _safe_json(payload) or {}
        self.script_ready.set()
        self._sink.on_script_ready(data)

    @dbus_method_async(input_signature="", result_signature="s")
    async def PollCommand(self) -> str:
        if not self._from_script():
            return encode_nop(reason="unknown_caller")
        self.counters.poll_requests += 1
        invalidated = self._invalidated  # snapshot: survives swap from invalidate_polls()
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
            self.counters.poll_invalidated_returns += 1
            return encode_nop(reason="invalidated")
        self.counters.poll_ceiling_returns += 1
        return encode_nop()

    @dbus_method_async(input_signature="s", result_signature="")
    async def CommandDone(self, payload: str) -> None:
        if not self._from_script():
            return
        self.counters.commands_completed += 1
        data = _safe_json(payload)
        if data is None:
            log.warning("CommandDone: malformed payload: %r", payload)
            return
        seq = data.get("seq")
        entry = self._completions.pop(seq, None) if isinstance(seq, int) else None
        if entry is None:
            log.debug("CommandDone: no pending completion for seq=%r", seq)
            return
        fut, start_ns = entry
        self.counters.latencies_ns.append(time.monotonic_ns() - start_ns)
        if not fut.done():
            result = data.get("result")
            if not isinstance(result, dict):
                result = {"ok": False, "error": "malformed_result", "raw": result}
            fut.set_result(result)


# ── Helpers ────────────────────────────────────────────────────────────────


def _current_sender() -> str | None:
    """The unique bus name of the caller, or ``None`` outside a dispatch."""
    try:
        message = get_current_message()
    except LookupError:
        return None
    return getattr(message, "sender", None)


def _safe_json(payload: str) -> dict[str, Any] | None:
    """Parse a JSON object, returning ``None`` (not raising) on malformed input."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


__all__ = [
    "POLL_CEILING_SECONDS",
    "SERVICE_NAME",
    "EventSink",
    "PerchKWin1",
    "ServiceCounters",
]
