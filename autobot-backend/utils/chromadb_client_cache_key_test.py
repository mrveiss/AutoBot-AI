# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10625: the sync + async ChromaDB client caches must key on the client
*settings* (allow_reset, anonymized_telemetry), not just host/path.

Before the fix a caller passing ``allow_reset=True`` after a prior default
(``allow_reset=False``) call silently got the FIRST client with the ORIGINAL
settings. These tests pin the corrected behaviour: differing settings build
distinct clients, while a repeated identical call is still a cache hit.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest


def _load_real_chromadb_modules() -> Tuple[ModuleType, ModuleType]:
    """Return the real, file-backed sync and async ChromaDB client modules.

    #13162: ``services/knowledge/test_analyzer_service.py`` and
    ``services/knowledge/test_kb_synthesizer.py`` install permanent
    ``types.ModuleType`` placeholders for ``utils.chromadb_client`` and
    ``utils.async_chromadb_client`` into ``sys.modules`` at import time and never
    remove them (``repo_tests/sys_modules_leak_guard.py`` reports both). They use
    ``setdefault``, so whichever module pytest imports first wins: in a combined
    run this file was handed the placeholder, whose ``get_async_chromadb_client``
    is a bare ``AsyncMock``. ``test_async_allow_reset_returns_different_client``
    then asserted that one AsyncMock return value ``is not`` itself -- it was
    measuring the mock, never the cache key.

    Load the real files under private names when that has happened. The
    placeholder stays registered, so the modules that installed it keep the
    object they captured at their own import time.
    """
    here = Path(__file__).resolve().parent

    def _real(name: str) -> ModuleType:
        module = sys.modules.get(f"utils.{name}") or importlib.import_module(f"utils.{name}")
        if getattr(module, "__file__", None):
            return module
        private = f"_real_13162_{name}"
        cached = sys.modules.get(private)
        if cached is not None:
            return cached
        spec = importlib.util.spec_from_file_location(private, here / f"{name}.py")
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[private] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    async_module = _real("async_chromadb_client")
    placeholder = sys.modules.get("utils.async_chromadb_client")
    # chromadb_client imports utils.async_chromadb_client at module level, so the
    # real module has to answer that name while chromadb_client executes. Put the
    # placeholder straight back afterwards.
    sys.modules["utils.async_chromadb_client"] = async_module
    try:
        sync_module = _real("chromadb_client")
    finally:
        if placeholder is None:
            sys.modules.pop("utils.async_chromadb_client", None)
        else:
            sys.modules["utils.async_chromadb_client"] = placeholder
    return sync_module, async_module


sync_mod, async_mod = _load_real_chromadb_modules()


def _stub_chromadb():
    """A fake ``chromadb`` module whose client constructors return unique mocks."""
    fake = MagicMock()
    fake.PersistentClient.side_effect = lambda *a, **k: MagicMock(name="PersistentClient")
    fake.HttpClient.side_effect = lambda *a, **k: MagicMock(name="HttpClient")
    fake.config = MagicMock()
    fake.config.Settings.side_effect = lambda *a, **k: MagicMock(name="Settings")
    return fake


@pytest.fixture
def local_chroma(tmp_path):
    """Force the local PersistentClient branch with migrations + chromadb stubbed."""
    fake = _stub_chromadb()
    with (
        patch.dict(sys.modules, {"chromadb": fake, "chromadb.config": fake.config}),
        patch.object(sync_mod, "_CHROMADB_HOST", ""),
        patch.object(async_mod, "_CHROMADB_HOST", ""),
        patch.object(sync_mod, "_migrate_legacy_collection_configs"),
        patch.object(sync_mod, "_fix_segment_hnsw_space"),
        patch.object(sync_mod, "_fix_seq_id_blob_type"),
        patch.object(sync_mod, "_fix_hnsw_pickle_format"),
    ):
        sync_mod._sync_client_cache.clear()
        async_mod._async_client_cache.clear()
        yield str(tmp_path / "chromadb")
        sync_mod._sync_client_cache.clear()
        async_mod._async_client_cache.clear()


def test_sync_allow_reset_returns_different_client(local_chroma):
    default = sync_mod.get_chromadb_client(db_path=local_chroma)
    reset_on = sync_mod.get_chromadb_client(db_path=local_chroma, allow_reset=True)
    assert reset_on is not default


def test_sync_identical_settings_is_cache_hit(local_chroma):
    first = sync_mod.get_chromadb_client(db_path=local_chroma)
    second = sync_mod.get_chromadb_client(db_path=local_chroma)
    assert first is second


def test_sync_telemetry_flag_returns_different_client(local_chroma):
    off = sync_mod.get_chromadb_client(db_path=local_chroma)
    on = sync_mod.get_chromadb_client(db_path=local_chroma, anonymized_telemetry=True)
    assert on is not off


@pytest.mark.asyncio
async def test_async_allow_reset_returns_different_client(local_chroma):
    default = await async_mod.get_async_chromadb_client(db_path=local_chroma)
    reset_on = await async_mod.get_async_chromadb_client(db_path=local_chroma, allow_reset=True)
    assert reset_on is not default


@pytest.mark.asyncio
async def test_async_identical_settings_is_cache_hit(local_chroma):
    first = await async_mod.get_async_chromadb_client(db_path=local_chroma)
    second = await async_mod.get_async_chromadb_client(db_path=local_chroma)
    assert first is second
