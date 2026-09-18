# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading the bearer token and echoing ``bearer`` are one contract (#16457)."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot_shared import websocket_subprotocol
from autobot_shared.websocket_subprotocol import (
    accept_websocket,
    bearer_subprotocol_token,
    negotiated_subprotocol,
    resolve_ws_token,
)


class _FakeRedis:
    """Minimal in-memory stand-in for the calls AlertCooldownManager makes.

    Real, stateful (not a per-call MagicMock return) so a burst of calls
    within one test can actually observe the cooldown key a prior call set --
    ``alert_cooldown_test.py``'s own ``_make_redis`` fixes each call's return
    value instead, which cannot simulate that sequence.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> bytes | None:
        value = self._store.get(key)
        return value.encode() if value is not None else None

    def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self._store[key] = str(value)
        return True

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._incr_keys: list[str] = []

    def incr(self, key: str) -> None:
        self._incr_keys.append(key)

    def expire(self, key: str, seconds: int) -> None:
        pass  # TTL isn't observable through this fake; irrelevant to what these tests assert.

    def execute(self) -> list[int]:
        results = []
        for key in self._incr_keys:
            current = int(self._redis._store.get(key, "0")) + 1
            self._redis._store[key] = str(current)
            results.append(current)
        self._incr_keys = []
        return results


@pytest.fixture(autouse=True)
def _isolated_fallback_cooldown(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Every test in this file gets its own in-memory Redis stand-in.

    Without this, `resolve_ws_token`'s fallback-warning throttle (#16457
    review, round 3) shares the real `alert_cooldown` Redis state across
    every test run -- confirmed by running the fallback test twice in a row
    locally: the second run's cooldown key was still live from the first,
    and the "logs a warning" assertion failed. Each test gets a fresh,
    empty fake, so the first fallback call in any test always passes the
    cooldown check.
    """
    fake = _FakeRedis()
    monkeypatch.setattr(websocket_subprotocol._fallback_cooldown, "_get_client", lambda: fake)
    return fake


def _ws(header: str | None) -> SimpleNamespace:
    headers = {} if header is None else {"sec-websocket-protocol": header}
    return SimpleNamespace(headers=headers, accept=AsyncMock())


def _ws_with_query(header: str | None, query_token: str | None = None, path: str = "/ws/example") -> SimpleNamespace:
    headers = {} if header is None else {"sec-websocket-protocol": header}
    query_params = {} if query_token is None else {"token": query_token}
    return SimpleNamespace(
        headers=headers,
        accept=AsyncMock(),
        query_params=query_params,
        url=SimpleNamespace(path=path),
    )


def _inline_parse_from_16891(header: str | None) -> str | None:
    """The parse ``authenticate_websocket`` carried inline, verbatim, for parity."""
    protocols = [p.strip() for p in (header or "").split(",")]
    return protocols[1] if len(protocols) == 2 and protocols[0] == "bearer" and protocols[1] else None


HEADERS = [None, "", "bearer", "bearer, ", "bearer, tok", " bearer ,  tok ", "bearerX, tok", "x, bearer",
           "bearer, a, b", "bearer,,tok", "Bearer, tok", "tok, bearer"]  # fmt: skip


@pytest.mark.parametrize("header", HEADERS)
def test_token_parsing_is_unchanged_from_what_it_replaced(header: str | None) -> None:
    """Moving the parser must not change which headers yield a token."""
    assert bearer_subprotocol_token(_ws(header)) == _inline_parse_from_16891(header)


def test_a_well_formed_header_yields_the_token_and_the_echo() -> None:
    ws = _ws("bearer, tok")
    assert bearer_subprotocol_token(ws) == "tok"
    assert negotiated_subprotocol(ws) == "bearer"


def test_a_protocol_the_client_did_not_offer_is_never_echoed() -> None:
    """The drift this replaces: endpoints echoed on ``startswith("bearer")``.

    A client that offered ``bearerX`` got ``bearer`` back, which it never offered,
    and RFC 6455 says the browser must fail the handshake on that.
    """
    ws = _ws("bearerX, tok")
    assert "bearerX, tok".startswith("bearer"), "control: the old rule would have echoed this"
    assert negotiated_subprotocol(ws) is None
    assert bearer_subprotocol_token(ws) is None


def test_bearer_offered_without_a_token_still_echoes() -> None:
    """Completing the handshake lets the endpoint send a clean 4001 close; not
    echoing would fail it outright with no reason given to the client."""
    ws = _ws("bearer")
    assert negotiated_subprotocol(ws) == "bearer"
    assert bearer_subprotocol_token(ws) is None


@pytest.mark.parametrize("header", [None, "", "chat.v1"])
def test_no_bearer_offer_means_no_echo(header: str | None) -> None:
    assert negotiated_subprotocol(_ws(header)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("header", "echo"), [("bearer, tok", "bearer"), (None, None), ("bearerX, tok", None)])
async def test_accept_websocket_echoes_exactly_what_was_negotiated(header: str | None, echo: str | None) -> None:
    ws = _ws(header)
    await accept_websocket(ws)
    ws.accept.assert_awaited_once_with(subprotocol=echo)


# --- resolve_ws_token: the read side, and the fallback's own visibility (#16457 review) ---


def test_resolve_ws_token_prefers_the_subprotocol_over_the_query_param() -> None:
    ws = _ws_with_query("bearer, tok", query_token="other")
    assert resolve_ws_token(ws) == "tok"


def test_resolve_ws_token_falls_back_to_the_query_param(caplog: pytest.LogCaptureFixture) -> None:
    ws = _ws_with_query(None, query_token="other", path="/ws/deployments/dep-1")
    with caplog.at_level(logging.WARNING):
        assert resolve_ws_token(ws) == "other"
    assert "/ws/deployments/dep-1" in caplog.text
    # The route is named; the value itself never is.
    assert "other" not in caplog.text


def test_resolve_ws_token_logs_nothing_when_the_subprotocol_supplied_it(caplog: pytest.LogCaptureFixture) -> None:
    ws = _ws_with_query("bearer, tok", query_token="other")
    with caplog.at_level(logging.WARNING):
        resolve_ws_token(ws)
    assert caplog.text == ""


def test_resolve_ws_token_logs_nothing_when_neither_source_has_a_value(caplog: pytest.LogCaptureFixture) -> None:
    ws = _ws_with_query(None)
    with caplog.at_level(logging.WARNING):
        assert resolve_ws_token(ws) is None
    assert caplog.text == ""


def test_a_burst_of_fallback_handshakes_on_one_route_logs_once(caplog: pytest.LogCaptureFixture) -> None:
    """#16457 review, round 3: unthrottled, a reconnect loop or a prober
    floods the log with one line per handshake attempt. Five handshakes in
    a burst on the same route must log exactly once."""
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            ws = _ws_with_query(None, query_token="other", path="/ws/deployments/dep-1")
            assert resolve_ws_token(ws) == "other"
    assert caplog.text.count("/ws/deployments/dep-1") == 1


def test_a_burst_on_a_different_route_is_not_suppressed_by_the_first(caplog: pytest.LogCaptureFixture) -> None:
    """The cooldown is per route, not global: a second route in the same
    burst must still get its own first warning."""
    with caplog.at_level(logging.WARNING):
        resolve_ws_token(_ws_with_query(None, query_token="other", path="/ws/deployments/dep-1"))
        resolve_ws_token(_ws_with_query(None, query_token="other", path="/ws/deployments/dep-2"))
    assert "/ws/deployments/dep-1" in caplog.text
    assert "/ws/deployments/dep-2" in caplog.text
