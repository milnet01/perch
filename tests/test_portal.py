"""Tests for the shared portal Request/Response handshake (PERC-0048)."""

from __future__ import annotations

from typing import Any

from perch.portal import call_with_response, request_path


def test_request_path_follows_the_portal_rule() -> None:
    assert (
        request_path(":1.42", "abc")
        == "/org/freedesktop/portal/desktop/request/1_42/abc"
    )


class _Waiter:
    def __init__(self, log: list[str], path: str) -> None:
        self.log = log
        self.path = path
        self.payload: tuple[int, dict[str, Any]] | None = None

    async def wait(self, timeout_s: float) -> tuple[int, dict[str, Any]] | None:
        del timeout_s
        return self.payload

    def close(self) -> None:
        self.log.append(f"close {self.path}")


async def test_a_portal_ignoring_handle_token_moves_the_subscription() -> None:
    log: list[str] = []
    waiters: dict[str, _Waiter] = {}

    async def subscribe(path: str) -> _Waiter:
        log.append(f"subscribe {path}")
        waiters[path] = _Waiter(log, path)
        waiters[path].payload = (0, {"ok": True}) if path == "/legacy" else None
        return waiters[path]

    async def sender() -> str:
        return ":1.7"

    async def invoke(token: str) -> str:
        log.append(f"call {token}")
        return "/legacy"

    result = await call_with_response(
        invoke, timeout_s=0.1, subscriber=subscribe, sender=sender
    )
    assert result == (0, {"ok": True})
    assert log[0].startswith("subscribe /org/freedesktop/portal/desktop/request/1_7/")
    assert log[1].startswith("call ")
    assert log[2].startswith("close /org/")
    assert log[3:] == ["subscribe /legacy", "close /legacy"]
