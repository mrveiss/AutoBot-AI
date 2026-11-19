# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``delete_collection_if_empty`` never deletes vectors written after the empty check (#20992, #17038)."""

import pytest

from services import chroma_empty_collections as svc
from utils.async_chromadb_client import AsyncChromaClient

_NAME = "autobot_docs"


class _Raw:
    """A sync Chroma collection; ``on_count`` runs between the count and the delete (a concurrent writer)."""

    def __init__(self, owner, name, vectors=0):
        self.owner, self.name, self.vectors, self.on_count = owner, name, vectors, None
        self.fail_rename_back = False

    def count(self):
        seen = self.vectors
        if self.on_count:
            self.on_count()
        return seen

    def modify(self, name=None, metadata=None):
        if name == _NAME and self.fail_rename_back:
            raise ValueError("name taken")
        self.owner.collections[name] = self.owner.collections.pop(self.name)
        self.name = name


class _Sync:
    def __init__(self, raw_vectors=0):
        self.collections = {_NAME: _Raw(self, _NAME, raw_vectors)}
        self.deleted = []

    def get_collection(self, name, embedding_function=None):
        return self.collections[name]

    def delete_collection(self, name):
        self.deleted.append(name)
        self.collections.pop(name)


@pytest.mark.asyncio
async def test_an_empty_collection_is_deleted_under_its_fenced_name():
    sync = _Sync()
    client = AsyncChromaClient(sync)
    assert await client.delete_collection_if_empty(_NAME) == 0
    assert len(sync.deleted) == 1 and sync.deleted[0].startswith(_NAME + ".deleting-")
    assert sync.collections == {}


@pytest.mark.asyncio
async def test_a_writer_looking_the_name_up_after_the_check_does_not_reach_the_collection():
    sync = _Sync()
    seen = []
    sync.collections[_NAME].on_count = lambda: seen.append(_NAME in sync.collections)
    await AsyncChromaClient(sync).delete_collection_if_empty(_NAME)
    assert seen == [False]  # the name was already fenced when the count ran


@pytest.mark.asyncio
async def test_a_non_empty_collection_is_renamed_back_and_kept():
    sync = _Sync(raw_vectors=4)
    assert await AsyncChromaClient(sync).delete_collection_if_empty(_NAME) == 4
    assert sync.deleted == [] and list(sync.collections) == [_NAME]


@pytest.mark.asyncio
async def test_a_write_landing_between_the_existence_check_and_the_delete_is_kept(monkeypatch):
    """The old flow counted, then deleted in a separate await; a write in that gap was destroyed."""
    sync = _Sync()
    raw = sync.collections[_NAME]

    async def _get():
        return AsyncChromaClient(sync)

    async def _exists_then_a_writer_adds(self, name, embedding_function=None):
        raw.vectors = 1  # the concurrent write, after the service looked and before it deletes
        return object()

    monkeypatch.setattr(svc, "get_async_chromadb_client", _get)
    monkeypatch.setattr(AsyncChromaClient, "get_collection_or_none", _exists_then_a_writer_adds)
    done, reason = await svc.delete_empty_collection(_NAME)
    assert done is False and "1 vector" in reason
    assert sync.deleted == [] and list(sync.collections) == [_NAME]


@pytest.mark.asyncio
async def test_a_failed_delete_restores_the_name_and_reports_did_not_run(monkeypatch):
    sync = _Sync()

    def _boom(name):
        raise OSError("chroma down")

    sync.delete_collection = _boom

    async def _get():
        return AsyncChromaClient(sync)

    async def _exists(self, name, embedding_function=None):
        return object()

    monkeypatch.setattr(svc, "get_async_chromadb_client", _get)
    monkeypatch.setattr(AsyncChromaClient, "get_collection_or_none", _exists)
    done, reason = await svc.delete_empty_collection(_NAME)
    assert done is False and "did not run" in reason
    assert list(sync.collections) == [_NAME]


@pytest.mark.asyncio
async def test_a_restore_that_fails_is_named_in_the_error():
    sync = _Sync(raw_vectors=2)
    sync.collections[_NAME].fail_rename_back = True
    with pytest.raises(RuntimeError, match="held as"):
        await AsyncChromaClient(sync).delete_collection_if_empty(_NAME)
