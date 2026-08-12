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
The round-trip regression test proving the recursion guard survives a real
platform (no payload field carries state across the hop) also lives in
``tests/test_gateway_manager.py``.
"""

import logging

import pytest

from services.gateway import ingest_governor as governor_module
from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH, IngestGovernor


class _FakeAsyncRedis:
    """Minimal in-memory stand-in for the Redis calls the governor makes."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self._store:
            return None  # redis-py returns None/falsy when NX prevents the set
        self._store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def incr(self, key: str) -> int:
        value = int(self._store.get(key) or 0) + 1
        self._store[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self._store


def _fake_redis_factory(fake: "_FakeAsyncRedis | None" = None):
    fake = fake or _FakeAsyncRedis()

    async def _get(*_a, **_k):
        return fake

    return _get


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

    @pytest.mark.asyncio
    async def test_warns_once_per_platform_when_bot_id_unconfigured(self, governor, monkeypatch, caplog):
        """A no-op filter must be loud, not silent (#14028 HIGH finding) — but
        not spammy: one WARNING per platform per governor lifetime."""
        monkeypatch.delenv("AUTOBOT_GATEWAY_BOT_ID_SLACK", raising=False)
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory())

        with caplog.at_level(logging.WARNING):
            await governor.evaluate(platform="slack", channel_id="C1", message_id="m1", author_id="u1")
            await governor.evaluate(platform="slack", channel_id="C1", message_id="m2", author_id="u2")

        occurrences = caplog.text.count("no bot identity resolved for platform=slack")
        assert occurrences == 1

    @pytest.mark.asyncio
    async def test_registered_resolver_takes_precedence_over_env_var(self, governor, monkeypatch):
        """Telegram's real wiring (#14028): a dynamic resolver (getMe() id
        cached in Redis) beats a static env var when both are present."""
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_TELEGRAM", "env-bot-id")

        async def _resolver():
            return "resolved-bot-id"

        governor.register_bot_id_resolver("telegram", _resolver)

        verdict = await governor.evaluate(
            platform="telegram", channel_id="C1", message_id="m1", author_id="resolved-bot-id"
        )

        assert verdict.allowed is False
        assert verdict.reason == "bot_self"

    @pytest.mark.asyncio
    async def test_resolver_exception_falls_back_to_env_var(self, governor, monkeypatch):
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_TELEGRAM", "env-bot-id")

        async def _broken_resolver():
            raise RuntimeError("redis down")

        governor.register_bot_id_resolver("telegram", _broken_resolver)

        verdict = await governor.evaluate(platform="telegram", channel_id="C1", message_id="m1", author_id="env-bot-id")

        assert verdict.allowed is False
        assert verdict.reason == "bot_self"


class TestRecursionGuard:
    """The recursion counter is server-side Redis state, incremented by
    ``record_agent_send`` and read (never trusted from the inbound payload)
    at ingest — see the module docstring and the #14028 review correction:
    no real platform round-trips an AutoBot-internal payload field back
    through its own inbound webhook."""

    @pytest.mark.asyncio
    async def test_chain_over_ceiling_is_halted(self, governor, monkeypatch):
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        for _ in range(INGEST_MAX_CHAIN_DEPTH + 1):
            await governor.record_agent_send(platform="slack", channel_id="C1")

        verdict = await governor.evaluate(platform="slack", channel_id="C1", message_id="m1", author_id="u1")

        assert verdict.allowed is False
        assert verdict.reason == "recursion_ceiling"

    @pytest.mark.asyncio
    async def test_chain_at_ceiling_is_allowed(self, governor, monkeypatch):
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        for _ in range(INGEST_MAX_CHAIN_DEPTH):
            await governor.record_agent_send(platform="slack", channel_id="C1")

        verdict = await governor.evaluate(platform="slack", channel_id="C1", message_id="m1", author_id="u1")

        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_counter_is_scoped_per_platform_and_channel(self, governor, monkeypatch):
        """Sends in one channel must not trip the guard in a different one."""
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        for _ in range(INGEST_MAX_CHAIN_DEPTH + 1):
            await governor.record_agent_send(platform="slack", channel_id="noisy-channel")

        verdict = await governor.evaluate(platform="slack", channel_id="quiet-channel", message_id="m1", author_id="u1")

        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_no_platform_payload_field_can_influence_the_recursion_check(self, governor, monkeypatch):
        """The whole point of the fix: ``evaluate`` takes no chain_depth kwarg
        at all — nothing an inbound payload carries can move this counter."""
        fake = _FakeAsyncRedis()
        monkeypatch.setattr(governor_module, "get_async_redis_client", _fake_redis_factory(fake))

        import inspect

        signature = inspect.signature(governor.evaluate)
        assert "chain_depth" not in signature.parameters


class TestRecordAgentSend:
    @pytest.mark.asyncio
    async def test_fails_open_and_logs_when_redis_unavailable(self, governor, monkeypatch, caplog):
        async def _none_client(*_a, **_k):
            return None

        monkeypatch.setattr(governor_module, "get_async_redis_client", _none_client)

        with caplog.at_level(logging.ERROR):
            await governor.record_agent_send(platform="telegram", channel_id="chat1")

        assert "recursion tracking degraded" in caplog.text


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
    """Deliberate decision (#14028): dedup and the recursion counter both
    FAIL OPEN when Redis is unavailable; the bot-self filter alone is
    Redis-independent and keeps enforcing regardless. Every fail-open is
    both logged at ERROR and recorded via prometheus_metrics.record_error —
    this test class locks in the *degradation* (not a silent pass-through
    of the whole stage), that it logs, and that it emits a metric.
    """

    @pytest.mark.asyncio
    async def test_dedup_client_returning_none_fails_open_and_logs(self, governor, monkeypatch, caplog):
        async def _none_client(*_a, **_k):
            return None

        monkeypatch.setattr(governor_module, "get_async_redis_client", _none_client)

        with caplog.at_level(logging.ERROR):
            verdict = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="m1", author_id="u1")

        assert verdict.allowed is True
        assert verdict.reason == "redis_unavailable_fail_open"
        assert "FAILING OPEN" in caplog.text

    @pytest.mark.asyncio
    async def test_dedup_client_raising_fails_open_and_logs(self, governor, monkeypatch, caplog):
        async def _raising_client(*_a, **_k):
            raise ConnectionError("simulated Redis outage")

        monkeypatch.setattr(governor_module, "get_async_redis_client", _raising_client)

        with caplog.at_level(logging.ERROR):
            verdict = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="m1", author_id="u1")

        assert verdict.allowed is True
        assert verdict.reason == "redis_unavailable_fail_open"
        assert "FAILING OPEN" in caplog.text

    @pytest.mark.asyncio
    async def test_recursion_check_fails_open_and_logs_when_redis_down(self, governor, monkeypatch, caplog):
        """Unlike the first PR revision, the recursion guard now depends on
        Redis (server-side counter) — this locks in that an outage degrades
        it visibly rather than either silently blocking every message or
        silently never tripping."""

        async def _none_client(*_a, **_k):
            return None

        monkeypatch.setattr(governor_module, "get_async_redis_client", _none_client)

        with caplog.at_level(logging.ERROR):
            verdict = await governor.evaluate(platform="telegram", channel_id="chat1", message_id="m1", author_id="u1")

        # Recursion check fails open (returns None -> falls through to dedup,
        # which independently also fails open here) -- net allowed.
        assert verdict.allowed is True
        assert "recursion check FAILING OPEN" in caplog.text

    @pytest.mark.asyncio
    async def test_bot_self_filter_still_enforced_when_redis_down(self, governor, monkeypatch):
        """The one guard that must not depend on Redis."""
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
        )

        assert verdict.allowed is True
        assert verdict.reason == ""
