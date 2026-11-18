# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WhatsApp credentials are sealed per Redis key and fail closed (#17981)."""

import base64
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from autobot_shared.field_encryption import FieldDecryptionError
from services import whatsapp_service as wa


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()

    async def _client(*_a, **_k):
        return fake

    monkeypatch.setattr(wa, "get_redis_client", _client)
    monkeypatch.setenv("AUTOBOT_SECRETS_ROOT_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    return fake


@pytest.mark.asyncio
async def test_a_credential_round_trips_and_is_stored_sealed(redis):
    await wa._set_encrypted(wa.WHATSAPP_ACCESS_TOKEN_KEY, "tok")
    assert redis.data[wa.WHATSAPP_ACCESS_TOKEN_KEY].startswith("enc:fe1.")
    assert wa._decode(wa.WHATSAPP_ACCESS_TOKEN_KEY, redis.data[wa.WHATSAPP_ACCESS_TOKEN_KEY]) == "tok"


@pytest.mark.asyncio
async def test_a_credential_moved_to_another_key_does_not_open(redis):
    await wa._set_encrypted(wa.WHATSAPP_ACCESS_TOKEN_KEY, "tok")
    with pytest.raises(FieldDecryptionError, match="whatsapp_app_secret"):
        wa._decode(wa.WHATSAPP_APP_SECRET_KEY, redis.data[wa.WHATSAPP_ACCESS_TOKEN_KEY])


def test_a_pre_17981_credential_still_reads(monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("AUTOBOT_FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode())
    nonce = os.urandom(12)
    legacy = "enc:" + base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, b"old", None)).decode()
    assert wa._decode(wa.WHATSAPP_ACCESS_TOKEN_KEY, legacy) == "old"
