# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBotMCPServer post-auth rate limit: one global count per token prefix (#18087).

Moved from autobot_server_test.py (#5072) when the per-instance dict became the canonical
``RateLimiter``: the 51st request is still refused with -32029, two server instances (workers)
now share one count, and Redis down lets requests through.
"""

import logging
from unittest.mock import patch

import pytest

from autobot_shared.ssot_config import config
from mcp_server.autobot_server import AutoBotMCPServer

TEST_SECRET = "test-mcp-secret"  # pragma: allowlist secret
VALID_TOKEN = f"{TEST_SECRET}:kb,memory,agents"


@pytest.fixture(autouse=True)
def _configure_mcp_secret():
    with patch.object(config.misc, "mcp_token", TEST_SECRET):
        yield


def make_server() -> AutoBotMCPServer:
    return AutoBotMCPServer()


@pytest.fixture
def shared_redis(monkeypatch):
    """One fakeredis behind the canonical limiter -- the 'cross-worker' store (#18087)."""
    fakeredis = pytest.importorskip("fakeredis")
    import fakeredis.aioredis as fakeredis_async

    from autobot_shared import rate_limiter as rl_mod

    server = fakeredis.FakeServer()
    client = fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _client)
    return server


@pytest.mark.asyncio
async def test_rate_limit_after_50_requests(shared_redis, caplog):
    server = make_server()
    # Exhaust the 50-request window
    for _ in range(50):
        r = await server.handle_request("tools/list", {}, VALID_TOKEN)
        assert "result" in r, "should succeed within limit"

    # 51st request should be rate-limited
    with caplog.at_level(logging.WARNING):
        r = await server.handle_request("tools/list", {}, VALID_TOKEN)
    assert "error" in r
    assert r["error"]["code"] == -32029
    assert r["error"]["message"] == "Rate limit exceeded (50 req/60s)"
    assert [x for x in caplog.records if "post-auth rate limit exceeded" in x.getMessage()]
    assert VALID_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_rate_limit_count_is_shared_between_workers(shared_redis, monkeypatch):
    from mcp_server import autobot_server as mod

    monkeypatch.setattr(mod, "_RATE_LIMIT", 4)
    worker_a, worker_b = make_server(), make_server()
    for srv in (worker_a, worker_b, worker_a, worker_b):
        assert "result" in await srv.handle_request("tools/list", {}, VALID_TOKEN)
    r = await worker_a.handle_request("tools/list", {}, VALID_TOKEN)
    assert r["error"]["code"] == -32029


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_is_down(monkeypatch, caplog):
    from autobot_shared import rate_limiter as rl_mod
    from mcp_server import autobot_server as mod

    async def _down(database: str = "main"):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _down)
    monkeypatch.setattr(mod, "_RATE_LIMIT", 1)
    srv = make_server()
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert "result" in await srv.handle_request("tools/list", {}, VALID_TOKEN)
    assert any("fail-open" in x.getMessage() for x in caplog.records)


@pytest.mark.asyncio
async def test_tokens_sharing_a_16_char_prefix_have_independent_quotas(shared_redis, monkeypatch):
    """The key hashes the WHOLE token: a common JWT header prefix must not merge two callers' quotas."""
    from mcp_server import autobot_server as mod

    monkeypatch.setattr(mod, "_RATE_LIMIT", 2)
    tok_a, tok_b = VALID_TOKEN + ":a", VALID_TOKEN + ":b"
    assert tok_a[:16] == tok_b[:16]
    srv = make_server()
    for _ in range(2):
        assert "result" in await srv.handle_request("tools/list", {}, tok_a)
    assert (await srv.handle_request("tools/list", {}, tok_a))["error"]["code"] == -32029
    assert "result" in await srv.handle_request("tools/list", {}, tok_b)
