# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A rejected tool and an unreachable server are different answers (#17467).

Two failures were reported as log lines and one word. A tool that failed
validation vanished from the returned list with its reason in a backend log, and
every discovery failure -- connect refused, bad schema, our own bug -- was
logged as *"skipping unreachable server"*.

So an operator adding a server saw four of its six tools with nothing to ask,
or was told a server that answered perfectly was unreachable. *Nothing found*
and *we rejected what we found* were indistinguishable, which is the
MEASUREMENT_DISCIPLINE rule broken at the discovery seam.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.mcp_aggregation import discover_tools_multi_server_detailed
from skills.sync.mcp_client import MCPClient, ToolDiscovery, _advertised_name
from type_defs.mcp import MCPToolDefinition

_GOOD = {"name": "good", "description": "fine", "inputSchema": {"type": "object", "properties": {}, "required": []}}
_MALFORMED = {"name": "broken", "inputSchema": "not-an-object"}


def _client_returning(raw_tools: list) -> MCPClient:
    """A real MCPClient whose transport answers `tools/list` with *raw_tools*."""
    client = MCPClient.__new__(MCPClient)
    client._call = AsyncMock(return_value={"tools": raw_tools})  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# AC1 / AC4 — a rejected tool is returned with its reason, not dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_good_and_one_malformed_tool_yields_both_outcomes() -> None:
    """#17467 AC4, and the assertion the old code could not satisfy.

    Previously `discover_tools` returned `[good]` and the reason for `broken`
    existed only in a log line. The count was right and the explanation was
    unreachable.
    """
    discovery = await _client_returning([_GOOD, _MALFORMED]).discover_tools_detailed()

    assert [t.name for t in discovery.accepted] == ["good"]
    assert len(discovery.rejected) == 1
    assert discovery.rejected[0].name == "broken"
    assert discovery.rejected[0].reason, "a rejection with no reason is the defect with extra steps"


@pytest.mark.asyncio
async def test_the_plain_form_still_returns_only_accepted_tools() -> None:
    """The compatibility half: three existing callers read a plain list."""
    assert [t.name for t in await _client_returning([_GOOD, _MALFORMED]).discover_tools()] == ["good"]


@pytest.mark.asyncio
async def test_a_non_dict_entry_does_not_abort_discovery() -> None:
    """The error path used to raise from inside itself.

    `raw.get("name")` sat in the `except` handler, so a non-dict entry raised
    `AttributeError` *while reporting* a validation failure -- and took every
    remaining tool with it. An error reporter that fails on the input it is
    describing is worse than the error it describes.
    """
    discovery = await _client_returning(["just-a-string", _GOOD]).discover_tools_detailed()

    assert [t.name for t in discovery.accepted] == ["good"]
    assert len(discovery.rejected) == 1
    assert discovery.rejected[0].name is None


def test_the_name_extractor_never_raises() -> None:
    for raw in ({"name": "x"}, {"name": 7}, {}, "string", None, 42, []):
        _advertised_name(raw)  # must not raise for any shape a server can send


# ---------------------------------------------------------------------------
# AC2 — transport and schema failures are different answers
# ---------------------------------------------------------------------------


def _server(*, raises: BaseException | None = None, discovery: ToolDiscovery | None = None) -> AsyncMock:
    client = AsyncMock()
    client.__aexit__ = AsyncMock(return_value=False)
    if raises is not None:
        client.__aenter__ = AsyncMock(side_effect=raises)
        return client
    client.__aenter__ = AsyncMock(return_value=client)
    client.discover_tools_detailed = AsyncMock(return_value=discovery or ToolDiscovery())
    return client


@pytest.mark.asyncio
async def test_a_transport_failure_is_labelled_transport() -> None:
    outcome = await discover_tools_multi_server_detailed(
        ["http://dead:1"], lambda uri: _server(raises=ConnectionRefusedError("no route"))
    )

    assert outcome.servers == []
    assert [f.kind for f in outcome.failures] == ["transport"]


@pytest.mark.asyncio
async def test_a_schema_failure_is_not_labelled_unreachable() -> None:
    """The misinformation this issue names: a server that answered, reported as down."""

    class FakeValidationError(Exception):
        pass

    FakeValidationError.__name__ = "ValidationError"

    outcome = await discover_tools_multi_server_detailed(
        ["http://alive:2"], lambda uri: _server(raises=FakeValidationError("bad payload"))
    )

    assert [f.kind for f in outcome.failures] == [
        "schema"
    ], "a reachable server with an unusable payload was reported as a transport failure"


@pytest.mark.asyncio
async def test_one_failing_server_does_not_cost_the_others_their_tools() -> None:
    good = MCPToolDefinition.model_validate(_GOOD)
    alive = _server(discovery=ToolDiscovery(accepted=[good], rejected=[]))
    dead = _server(raises=OSError("down"))

    outcome = await discover_tools_multi_server_detailed(
        ["http://dead:1", "http://alive:2"], lambda uri: dead if "dead" in uri else alive
    )

    assert [t.name for s in outcome.servers for t in s.tools] == ["good"]
    assert len(outcome.failures) == 1


# ---------------------------------------------------------------------------
# The laundering fix — our bug must not become a server's fault (#17439)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_programming_error_is_raised_not_recorded_as_a_server_failure() -> None:
    """#17439's shape: a `KeyError` from our own code came back as "Redis unavailable".

    A broad `except Exception` over a per-server loop absorbs genuine defects and
    reports them as the environment's fault. The operator then investigates a
    server that is fine. Re-raised instead -- a bug here affects every server, so
    failing loudly is both honest and more useful.
    """
    with pytest.raises(KeyError):
        await discover_tools_multi_server_detailed(
            ["http://a:1"], lambda uri: _server(raises=KeyError("undeclared_name"))
        )


@pytest.mark.asyncio
async def test_a_rejection_reason_is_sanitized() -> None:
    """AC3: reasons reach an operator, so they pass through the provider redactor.

    A validation message quotes the payload, which can carry a token or a path.
    `redact_provider_error` is the redactor REDACTION_BOUNDARY.md names for a
    provider exception; this asserts the value went through it rather than
    re-implementing what it masks.
    """
    leaky = {"name": "leaky", "inputSchema": "Authorization: Bearer sk-secret-value"}

    discovery = await _client_returning([leaky]).discover_tools_detailed()

    assert len(discovery.rejected) == 1
    assert "sk-secret-value" not in discovery.rejected[0].reason


# ---------------------------------------------------------------------------
# The contract is required, and a double must be able to fail it.
#
# `AsyncMock` auto-creates every attribute, which is why mcp_aggregation states
# the `discover_tools_detailed` contract instead of probing for it. The same
# property bites from the other side: two test files kept doubles that stubbed
# only `discover_tools()`, so the detailed call returned a mock, `.accepted` was
# a mock, and nine tests failed with empty tool sets several layers away rather
# than an AttributeError naming the missing method.
# ---------------------------------------------------------------------------


class _OnlyPlainDiscovery:
    """A client with the old surface and nothing auto-created behind it."""

    async def discover_tools(self):
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_a_client_without_the_detailed_form_raises_instead_of_yielding_mocks() -> None:
    """A missing method is our bug, so it must surface as one.

    `AttributeError` is in `_OUR_BUG`, so this is re-raised rather than recorded
    as an unreachable server -- the laundering #17439 found, where a programming
    error came back as an operational metric.
    """
    from services.mcp_aggregation import discover_tools_multi_server_detailed

    with pytest.raises(AttributeError):
        await discover_tools_multi_server_detailed(["stdio://one"], lambda uri: _OnlyPlainDiscovery())


@pytest.mark.asyncio
async def test_the_shared_double_satisfies_the_contract_it_stands_in_for() -> None:
    """Otherwise the helper is the next place a mock leaks in as a tool list."""
    from testkit.mcp_client_doubles import mcp_client_double

    discovery = await mcp_client_double(["a-tool"]).discover_tools_detailed()

    assert discovery.accepted == ["a-tool"]
    assert discovery.rejected == []
