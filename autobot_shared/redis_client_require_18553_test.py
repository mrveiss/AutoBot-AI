# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`require_redis_client` returns the client, or raises when there is none (#18553)."""

import pytest

from autobot_shared import redis_client
from autobot_shared.redis_require import require_redis_client


def test_returns_the_client_and_passes_arguments_through(monkeypatch):
    sentinel = object()
    seen = {}

    def _fake(**kwargs):
        seen.update(kwargs)
        return sentinel

    monkeypatch.setattr(redis_client, "get_redis_client", _fake)
    assert require_redis_client("knowledge", decode_responses=True) is sentinel
    assert seen == {"database": "knowledge", "decode_responses": True}


def test_raises_connection_error_on_none(monkeypatch):
    monkeypatch.setattr(redis_client, "get_redis_client", lambda **kw: None)
    with pytest.raises(ConnectionError, match="Redis 'knowledge' unavailable"):
        require_redis_client("knowledge")


def test_unsupported_kwarg_is_rejected_by_signature():
    with pytest.raises(TypeError):
        require_redis_client("knowledge", async_client=True)


def test_reexported_from_redis_client():
    assert redis_client.require_redis_client is require_redis_client
    assert "require_redis_client" in redis_client.__all__
