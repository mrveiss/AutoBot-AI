# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for registered_source_ids() itself (#17039 review, #17050).

Every detector test monkeypatches this function away, so it was never
exercised directly by the suite -- this is that direct exercise.
"""

import pytest

from api.codebase_analytics import source_storage

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self, members):
        self._members = members

    async def smembers(self, _key):
        return self._members


async def test_raises_registry_unavailable_when_the_client_is_none(monkeypatch):
    async def _no_client(**_kwargs):
        return None

    monkeypatch.setattr(source_storage, "get_async_redis_client", _no_client)

    with pytest.raises(source_storage.RegistryUnavailable):
        await source_storage.registered_source_ids()


async def test_decodes_byte_string_members_from_the_raw_redis_client(monkeypatch):
    async def _fake_client(**_kwargs):
        return _FakeRedis({b"source-1", b"source-2"})

    monkeypatch.setattr(source_storage, "get_async_redis_client", _fake_client)

    ids = await source_storage.registered_source_ids()

    assert ids == {"source-1", "source-2"}


async def test_passes_through_str_members_unchanged(monkeypatch):
    async def _fake_client(**_kwargs):
        return _FakeRedis({"source-1"})

    monkeypatch.setattr(source_storage, "get_async_redis_client", _fake_client)

    ids = await source_storage.registered_source_ids()

    assert ids == {"source-1"}
