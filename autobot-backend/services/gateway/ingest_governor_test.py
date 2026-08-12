# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the Gateway ingest governance stage (#14028).

Covers the three guards directly against ``IngestGovernor`` — the wiring
assertion that these guards actually run at the live ingest seams
(``GatewayManager.normalize_message`` and ``Gateway.receive_message``) lives
in ``tests/test_gateway_manager.py`` and ``services/gateway/gateway_test.py``.
"""

import logging

import pytest

from services.gateway import ingest_governor as governor_module
from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH, IngestGovernor


class _FakeAsyncRedis:
    """Minimal in-memory stand-in for the ``SET key val NX EX`` dedup call."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self._store:
            return None  # redis-py returns None/falsy when NX prevents the set
        self._store[key] = value
        return True


@pytest.fixture
def governor() -> IngestGovernor:
    return IngestGovernor()


class TestBotSelfFilter:
    @pytest.mark.asyncio
    async def test_drops_message_authored_by_configured_bot_id(self, governor, monkeypatch):
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_SLACK", "BOT123")

        verdict = await governor.evaluate(
            platform="slack",
            channel_id="C1",
            message_id="m1",
            author_id="BOT123",
        )

        assert verdict.allowed is False
        assert verdict.reason == "bot_self"

    @pytest.mark.asyncio
    async def test_noop_when_no_bot_id_configured(self, governor, monkeypatch):
        monkeypatch.delenv("AUTOBOT_GATEWAY_BOT_ID_SLACK", raising=False)
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory())

        verdict = await governor.evaluate(
            platform="slack",
            channel_id="C1",
            message_id="m1",
            author_id="anyone",
        )

        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_different_author_passes_through_bot_filter(self, governor, monkeypatch):
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_SLACK", "BOT123")
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory())

        verdict = await governor.evaluate(
            platform="slack",
            channel_id="C1",
            message_id="m1",
            author_id="a-human",
        )

        assert verdict.allowed is True


class TestRecursionGuard:
    @pytest.mark.asyncio
    async def test_chain_over_ceiling_is_halted(self, governor):
        verdict = await governor.evaluate(
            platform="slack",
            channel_id="C1",
            message_id="m1",
            author_id="u1",
            chain_depth=INGEST_MAX_CHAIN_DEPTH + 1,
        )

        assert verdict.allowed is False
        assert verdict.reason == "recursion_ceiling"

    @pytest.mark.asyncio
    async def test_chain_at_ceiling_is_allowed(self, governor, monkeypatch):
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory())

        verdict = await governor.evaluate(
            platform="slack",
            channel_id="C1",
            message_id="m1",
            author_id="u1",
            chain_depth=INGEST_MAX_CHAIN_DEPTH,
        )

        assert verdict.allowed is True


class TestDedup:
    @pytest.mark.asyncio
    async def test_same_message_id_delivered_twice_only_the_first_passes(self, governor, monkeypatch):
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        first = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="dup-1", author_id="u1")
        second = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="dup-1", author_id="u1")

        assert first.allowed is True
        assert second.allowed is False
        assert second.reason == "duplicate"

    @pytest.mark.asyncio
    async def test_different_message_ids_both_pass(self, governor, monkeypatch):
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        first = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="a", author_id="u1")
        second = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="b", author_id="u1")

        assert first.allowed is True
        assert second.allowed is True

    @pytest.mark.asyncio
    async def test_same_message_id_different_channel_both_pass(self, governor, monkeypatch):
        """Dedup key is scoped to (platform, channel, message_id) — not message_id alone."""
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        first = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="x", author_id="u1")
        second = await governor.evaluate(platform="telegram", channel_id="chat2", message_id="x", author_id="u1")

        assert first.allowed is True
        assert second.allowed is True


class TestRedisUnavailable:
    """Deliberate decision (#14028): dedup FAILS OPEN when Redis is unavailable.

    The bot-self filter and recursion guard are Redis-independent and keep
    enforcing regardless — this test locks in that the *degradation* (not a
    silent pass-through of the whole stage) is what happens, and that it logs.
    """

    @pytest.mark.asyncio
    async def test_client_returning_none_fails_open_and_logs(self, governor, monkeypatch, caplog):
        async def _none_client(*_a, **_k):
            return None

        monkeypatch.setattr(governor_module, "get_async_redis_client", _none_client)

        with caplog.at_level(logging.ERROR):
            verdict = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="m1", author_id="u1")

        assert verdict.allowed is True
        assert verdict.reason == "redis_unavailable_fail_open"
        assert "FAILING OPEN" in caplog.text

    @pytest.mark.asyncio
    async def test_client_raising_fails_open_and_logs(self, governor, monkeypatch, caplog):
        async def _raising_client(*_a, **_k):
            raise ConnectionError("simulated Redis outage")

        monkeypatch.setattr(governor_module, "get_async_redis_client", _raising_client)

        with caplog.at_level(logging.ERROR):
            verdict = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="m1", author_id="u1")

        assert verdict.allowed is True
        assert verdict.reason == "redis_unavailable_fail_open"
        assert "FAILING OPEN" in caplog.text

    @pytest.mark.asyncio
    async def test_bot_self_filter_still_enforced_when_redis_down(self, governor, monkeypatch):
        """The guard against the unbounded-loop failure mode must not depend on Redis."""
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_SLACK", "BOT123")

        async def _none_client(*_a, **_k):
            return None

        monkeypatch.setattr(governor_module, "get_async_redis_client", _none_client)

        verdict = await governor.evaluate(platform="slack", channel_id="C1", message_id="m1", author_id="BOT123")

        assert verdict.allowed is False
        assert verdict.reason == "bot_self"


class TestNormalMessageStillRoutes:
    @pytest.mark.asyncio
    async def test_ordinary_message_passes_all_guards(self, governor, monkeypatch):
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        verdict = await governor.evaluate(
            platform="discord",
            channel_id="chan1",
            message_id="ordinary-1",
            author_id="a-human",
            chain_depth=0,
        )

        assert verdict.allowed is True
        assert verdict.reason == ""


def _fake_redis_factory(fake: _FakeAsyncRedis | None = None):
    fake = fake or _FakeAsyncRedis()

    async def _get(*_a, **_k):
        return fake

    return _get
