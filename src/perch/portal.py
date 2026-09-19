"""The xdg-desktop-portal Request/Response handshake, shared by every caller.

A portal method does not answer in its return value. It returns the object
path of a ``org.freedesktop.portal.Request`` and later emits ``Response``
on that path. The reply can arrive before the method call itself returns,
so the portal documentation requires the caller to subscribe FIRST — to a
path it predicts from its own unique bus name and the ``handle_token`` it
passes in the call's options::

    /org/freedesktop/portal/desktop/request/<sender>/<handle_token>

where ``<sender>`` is the unique name with the leading ``:`` dropped and
every ``.`` replaced by ``_``. Subscribing after the call loses a fast
reply and the caller waits out its whole timeout.

:func:`call_with_response` does the handshake in that order. Its
``subscriber`` and ``sender`` parameters are the test seams.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
_REQUEST_PREFIX = "/org/freedesktop/portal/desktop/request"

#: ``(status, results)`` as the portal sends it; results are still variants.
PortalResponse = tuple[int, dict[str, Any]]


class ResponseWaiter(Protocol):
    """A subscription already in place on one Request path."""

    async def wait(self, timeout_s: float) -> PortalResponse | None: ...

    def close(self) -> None: ...


#: Installs the match for ``path`` and returns once it is in place.
Subscriber = Callable[[str], Awaitable[ResponseWaiter]]
#: Returns this connection's unique bus name (``:1.42``).
SenderName = Callable[[], Awaitable[str]]


def new_token() -> str:
    """A handle token: portal tokens must match ``^[a-zA-Z0-9_]+$``."""
    return secrets.token_hex(8)


def request_path(sender: str, token: str) -> str:
    """The Request path the portal will use for ``token``."""
    return f"{_REQUEST_PREFIX}/{sender.lstrip(':').replace('.', '_')}/{token}"


async def default_sender_name() -> str:
    """Unique name of the default bus connection.

    sdbus does not expose it directly, but every reply from the bus daemon
    is addressed to it.
    """
    from sdbus import get_default_bus

    bus = get_default_bus()
    message = bus.new_method_call_message(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetId"
    )
    reply = await bus.call_async(message)
    destination = reply.destination
    if not destination:
        raise RuntimeError("bus daemon reply carried no destination")
    return destination


class _SignalWaiter:
    def __init__(self, queue: asyncio.Queue[Any], slot: Any) -> None:
        self._queue = queue
        self._slot = slot

    async def wait(self, timeout_s: float) -> PortalResponse | None:
        try:
            message = await asyncio.wait_for(self._queue.get(), timeout=timeout_s)
        except TimeoutError:
            return None
        status, results = message.get_contents()
        return int(status), dict(results)

    def close(self) -> None:
        with suppress(Exception):
            self._slot.close()


async def default_subscriber(path: str) -> ResponseWaiter:
    """Match ``Response`` on ``path`` on the default bus."""
    from sdbus import get_default_bus

    queue: asyncio.Queue[Any] = asyncio.Queue()
    slot = await get_default_bus().match_signal_async(
        PORTAL_SERVICE, path, REQUEST_INTERFACE, "Response", queue.put_nowait
    )
    return _SignalWaiter(queue, slot)


async def call_with_response(
    invoke: Callable[[str], Awaitable[str]],
    *,
    timeout_s: float,
    subscriber: Subscriber | None = None,
    sender: SenderName | None = None,
) -> PortalResponse | None:
    """Subscribe, then call, then wait for the one Response.

    ``invoke`` receives the handle token to put in the call's options and
    returns the Request path the portal answered with. A portal that
    ignores ``handle_token`` returns a different path; the subscription is
    then moved to it, which is the best that portal allows. Returns
    ``None`` when no Response arrives within ``timeout_s``.
    """
    subscribe = subscriber or default_subscriber
    token = new_token()
    predicted = request_path(await (sender or default_sender_name)(), token)
    waiter = await subscribe(predicted)
    try:
        actual = await invoke(token)
        if actual != predicted:
            waiter.close()
            waiter = await subscribe(actual)
        return await waiter.wait(timeout_s)
    finally:
        waiter.close()
