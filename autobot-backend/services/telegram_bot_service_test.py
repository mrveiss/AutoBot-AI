# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Redis client shape used by telegram_bot_service (#19042).

``get_redis_client`` returns a sync client unless ``async_client=True``; awaiting
a sync client raises TypeError. The fake below mirrors that contract.
"""

import base64
import os

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
    monkeypatch.setenv("AUTOBOT_SECRETS_ROOT_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    return fake


@pytest.mark.asyncio
async def test_token_roundtrip_and_from_redis(redis):
    await tbs.save_telegram_bot_token("tok")
    assert redis.data[tbs.TELEGRAM_BOT_TOKEN_KEY].startswith("enc:fe1.")  # #17981: sealed, bound
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


@pytest.mark.asyncio
async def test_a_token_moved_to_another_key_does_not_open_17981(redis):
    from autobot_shared.field_encryption import FieldDecryptionError

    await tbs.save_telegram_bot_token("tok")
    redis.data[tbs.TELEGRAM_WEBHOOK_SECRET_KEY] = redis.data[tbs.TELEGRAM_BOT_TOKEN_KEY]
    with pytest.raises(FieldDecryptionError, match="telegram_webhook_secret"):
        await tbs.get_telegram_webhook_secret()


@pytest.mark.asyncio
async def test_a_pre_17981_token_still_reads(redis, monkeypatch):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = os.urandom(32)
    monkeypatch.setenv("AUTOBOT_FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode())
    nonce = os.urandom(12)
    legacy = base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, b"old-tok", None)).decode()
    redis.data[tbs.TELEGRAM_BOT_TOKEN_KEY] = "enc:" + legacy
    assert await tbs.get_telegram_bot_token() == "old-tok"


@pytest.mark.asyncio
async def test_an_unreadable_token_is_an_error_never_not_configured_17981(redis):
    from autobot_shared.field_encryption import FieldDecryptionError

    redis.data[tbs.TELEGRAM_BOT_TOKEN_KEY] = "enc:fe1.AAAA"
    with pytest.raises(FieldDecryptionError):
        await tbs.get_telegram_bot_token()
