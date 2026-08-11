# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The authenticated role must reach MCPDispatcher.dispatch() (#13821).

`dispatch()` takes ``role: str = "user"`` and, before this, nothing in production
ever passed it. #2629 wired ``role`` as far as ``_dispatch_tool_call``'s signature
and stopped; ``_process_tool_calls`` had no ``role`` parameter at all, so the
default won every call.

Two consequences, and the tests below pin both:

- an admin was evaluated as a user and *denied* the admin-only tools they are
  entitled to — over-restrictive, which is why nobody reported it
- #13228's shadow inventory could only ever contain ``role="user"`` rows, so the
  question its stage-3 flip exists to answer was unanswerable

The security direction matters more than the plumbing. ``context`` is the
caller's own ``request_data["context"]`` bag, so a client can put
``auth_role: "admin"`` in it. The trusted overlay must therefore *always* write
or remove that key — never leave the caller's value in place.
"""

from types import SimpleNamespace

import pytest

from chat_workflow.session_role import (
    AUTH_ROLE_CONTEXT_KEY,
    DEFAULT_AUTH_ROLE,
    apply_auth_role,
    resolve_auth_role,
)
from chat_workflow.tool_handler import ToolHandlerMixin


class _Recorder(ToolHandlerMixin):
    """Captures the role `_process_tool_calls` forwards to the dispatch seam."""

    def __init__(self):
        self.seen: list[str] = []

    async def _dispatch_tool_call(
        self,
        tool_call,
        session_id,
        terminal_session_id,
        ollama_endpoint,
        selected_model,
        execution_results,
        additional_response_parts,
        ctx=None,
        role: str = DEFAULT_AUTH_ROLE,
    ):
        self.seen.append(role)
        return
        yield  # pragma: no cover - makes this an async generator


async def _roles_forwarded(ctx) -> list[str]:
    handler = _Recorder()
    async for _ in handler._process_tool_calls(
        [{"name": "redis_flushall", "params": {}}],
        "sess-1",
        "term-1",
        "http://llm",
        "model",
        ctx=ctx,
    ):
        pass
    return handler.seen


class TestTheTrustedOverlay:
    """`context` is caller-supplied, so the overlay is a security boundary."""

    def test_a_server_role_overrides_a_client_supplied_one(self):
        merged = apply_auth_role({AUTH_ROLE_CONTEXT_KEY: "admin"}, "user")

        assert merged[AUTH_ROLE_CONTEXT_KEY] == "user"

    def test_a_missing_server_role_strips_the_client_value(self):
        """The whole vulnerability in one assertion.

        `apply_role` returns context unchanged on a falsy role. Copying that
        here would let a caller who writes `auth_role: "admin"` into their own
        request body keep it — an unauthenticated path would hand the tool seam
        the privileges the caller named for themselves.
        """
        merged = apply_auth_role({AUTH_ROLE_CONTEXT_KEY: "admin", "language": "en"}, None)

        assert AUTH_ROLE_CONTEXT_KEY not in merged
        assert resolve_auth_role(merged) == DEFAULT_AUTH_ROLE
        assert merged["language"] == "en", "unrelated context keys must survive"

    def test_the_caller_bag_is_not_mutated(self):
        original = {AUTH_ROLE_CONTEXT_KEY: "admin"}

        apply_auth_role(original, "user")

        assert original[AUTH_ROLE_CONTEXT_KEY] == "admin", "must copy, not mutate the request bag"

    @pytest.mark.parametrize("bad", [None, "", 123, {"nested": "dict"}, []])
    def test_a_non_string_or_empty_role_resolves_to_the_default(self, bad):
        assert resolve_auth_role({AUTH_ROLE_CONTEXT_KEY: bad}) == DEFAULT_AUTH_ROLE

    def test_an_absent_context_resolves_to_the_default(self):
        assert resolve_auth_role(None) == DEFAULT_AUTH_ROLE
        assert resolve_auth_role({}) == DEFAULT_AUTH_ROLE


class TestTheRoleReachesTheDispatchSeam:
    """AC: the authenticated role reaches dispatch() from the live chat path."""

    @pytest.mark.asyncio
    async def test_the_iteration_context_role_is_forwarded(self):
        assert await _roles_forwarded(SimpleNamespace(auth_role="admin")) == ["admin"]

    @pytest.mark.asyncio
    async def test_a_non_admin_role_is_forwarded_unchanged(self):
        """Forwarding must carry whatever the role is, not just recognise admin."""
        assert await _roles_forwarded(SimpleNamespace(auth_role="analyst")) == ["analyst"]

    @pytest.mark.asyncio
    async def test_no_iteration_context_falls_back_to_the_default_role(self):
        assert await _roles_forwarded(None) == [DEFAULT_AUTH_ROLE]


class TestTheEffectOnAdminOnlyTools:
    """AC: an admin session reaches an admin-only MCP tool; a user session does not.

    Exercised against the real `MCPDispatcher` gate rather than a stand-in, since
    the bug was that this gate never saw a role other than "user".
    """

    @staticmethod
    def _dispatcher():
        from services.mcp_dispatch import MCPDispatcher

        d = MCPDispatcher()
        d._tool_cache = {"redis_flushall": {"name": "redis_flushall", "bridge": "redis", "endpoint": "/x"}}

        async def _fresh():
            return None

        async def _call(tool_name, bridge, endpoint, arguments):
            return {"success": True, "result": "ran", "bridge": bridge}

        d._ensure_cache_fresh = _fresh
        d._call_bridge = _call
        return d

    @pytest.mark.asyncio
    async def test_an_admin_reaches_an_admin_only_tool(self):
        result = await self._dispatcher().dispatch("redis_flushall", {}, role="admin")

        assert result["success"] is True, "an admin was being denied a tool they are entitled to"

    @pytest.mark.asyncio
    async def test_a_user_is_denied_an_admin_only_tool(self):
        result = await self._dispatcher().dispatch("redis_flushall", {}, role=DEFAULT_AUTH_ROLE)

        assert result["success"] is False
        assert "admin" in str(result["result"]).lower()
