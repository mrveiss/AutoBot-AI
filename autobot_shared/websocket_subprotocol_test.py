# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading the bearer token and echoing ``bearer`` are one contract (#16457)."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot_shared.websocket_subprotocol import (
    accept_websocket,
    bearer_subprotocol_token,
    negotiated_subprotocol,
    resolve_ws_token,
)


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
