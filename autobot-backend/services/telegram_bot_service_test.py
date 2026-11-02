# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Redis client shape used by telegram_bot_service (#19042).

``get_redis_client`` returns a sync client unless ``async_client=True``; awaiting
a sync client raises TypeError. The fake below mirrors that contract.
"""

import pytest

from services import telegram_bot_service as tbs


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value


class SyncClient:
    """A sync client: not awaitable, as the real one."""


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()

    def fake_get_redis_client(async_client=False, **_kwargs):
        if not async_client:
            return SyncClient()

        async def _client():
            return fake

        return _client()

    monkeypatch.setattr(tbs, "get_redis_client", fake_get_redis_client)
    monkeypatch.setattr(tbs, "encrypt_field", lambda v: "E(" + v + ")")
    monkeypatch.setattr(tbs, "decrypt_field", lambda v: v[2:-1])
    return fake


@pytest.mark.asyncio
async def test_token_roundtrip_and_from_redis(redis):
    await tbs.save_telegram_bot_token("tok")
    assert redis.data[tbs.TELEGRAM_BOT_TOKEN_KEY] == "enc:E(tok)"
    assert await tbs.get_telegram_bot_token() == "tok"
    service = await tbs.TelegramBotService.from_redis()
    assert service.bot_token == "tok"


@pytest.mark.asyncio
async def test_webhook_secret_roundtrip(redis):
    await tbs.save_telegram_webhook_secret("sec")
    assert await tbs.get_telegram_webhook_secret() == "sec"


@pytest.mark.asyncio
async def test_bot_id_roundtrip(redis):
    await tbs.save_telegram_bot_id("42")
    assert await tbs.get_telegram_bot_id() == "42"
