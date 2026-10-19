# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18789: both local ChromaDB open paths run the 4 legacy repairs, once per path.

The async client used to open its own PersistentClient with none of the repairs.
It now delegates to the sync client's single local open.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

from utils.chromadb_client_cache_key_test import _stub_chromadb, async_mod, repairs_mod, sync_mod

_REPAIRS = (
    "_migrate_legacy_collection_configs",
    "_fix_segment_hnsw_space",
    "_fix_seq_id_blob_type",
    "_fix_hnsw_pickle_format",
)


@pytest.fixture
def repairs(tmp_path):
    fake = _stub_chromadb()
    mocks = {}
    with (
        patch.dict(
            sys.modules,
            {"chromadb": fake, "chromadb.config": fake.config, "utils.chromadb_client": sync_mod},
        ),
        patch.object(sync_mod, "_CHROMADB_HOST", ""),
        patch.object(async_mod, "_CHROMADB_HOST", ""),
    ):
        patchers = [patch.object(repairs_mod, n, MagicMock(return_value=True)) for n in _REPAIRS]
        for name, p in zip(_REPAIRS, patchers):
            mocks[name] = p.start()
        for cache in (
            sync_mod._sync_client_cache,
            async_mod._async_client_cache,
            repairs_mod._prepared_paths,
        ):
            cache.clear()
        mocks["path"] = str(tmp_path / "chromadb")
        mocks["fake"] = fake
        yield mocks
        for p in patchers:
            p.stop()


def _assert_each_once(mocks):
    for name in _REPAIRS:
        assert mocks[name].call_count == 1, name


@pytest.mark.asyncio
async def test_async_first_runs_each_repair_once(repairs):
    await async_mod.get_async_chromadb_client(db_path=repairs["path"])
    _assert_each_once(repairs)


@pytest.mark.asyncio
async def test_sync_then_async_runs_repairs_once_and_one_persistent_client(repairs):
    sync_mod.get_chromadb_client(db_path=repairs["path"])
    await async_mod.get_async_chromadb_client(db_path=repairs["path"])
    await async_mod.get_async_chromadb_client(db_path=repairs["path"], allow_reset=False)
    _assert_each_once(repairs)
    assert repairs["fake"].PersistentClient.call_count == 1


@pytest.mark.asyncio
async def test_concurrent_async_first_calls_run_repairs_once(repairs):
    await asyncio.gather(*(async_mod.get_async_chromadb_client(db_path=repairs["path"]) for _ in range(8)))
    _assert_each_once(repairs)
    assert repairs["fake"].PersistentClient.call_count == 1
