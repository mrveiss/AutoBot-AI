# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12513: ChromaDB CHROMA_SERVER_AUTHN_* client-auth wiring.

Verifies:
- ``chroma_client_auth_kwargs()`` is empty when AUTOBOT_CHROMADB_AUTH_TOKEN
  is unset (backward-compat: unauthenticated dev/local server keeps working).
- It returns the token-auth provider + credentials when the token is set.
- Both the sync and async HttpClient construction sites forward those kwargs
  into ``chromadb.config.Settings(...)``.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

import utils.chromadb_auth as auth_mod


def _load_real_chromadb_modules() -> Tuple[ModuleType, ModuleType]:
    """Return the real, file-backed sync and async ChromaDB client modules.

    #13162: ``services/knowledge/test_analyzer_service.py`` and
    ``services/knowledge/test_kb_synthesizer.py`` install permanent
    ``types.ModuleType`` placeholders for ``utils.chromadb_client`` and
    ``utils.async_chromadb_client`` into ``sys.modules`` at import time and never
    remove them (``repo_tests/sys_modules_leak_guard.py`` reports both). They use
    ``setdefault``, so whichever module pytest imports first wins: in a combined
    run this file was handed the placeholder, whose ``get_async_chromadb_client``
    is a bare ``AsyncMock``. Every assertion below then compared one mock against
    itself -- ``test_async_http_client_sends_token_when_configured`` read a
    ``Settings.call_args`` that was never populated, and the sibling cache-key
    test asserted an AsyncMock ``is not`` itself.

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


def test_auth_kwargs_empty_when_token_unset():
    with patch.object(auth_mod._ssot_config.misc, "chromadb_auth_token", ""):
        assert auth_mod.chroma_client_auth_kwargs() == {}


def test_auth_kwargs_populated_when_token_set():
    with patch.object(auth_mod._ssot_config.misc, "chromadb_auth_token", "s3cr3t"):
        kwargs = auth_mod.chroma_client_auth_kwargs()
    assert kwargs == {
        "chroma_client_auth_provider": "chromadb.auth.token_authn.TokenAuthClientProvider",
        "chroma_client_auth_credentials": "s3cr3t",
    }


def _stub_chromadb():
    """A fake ``chromadb`` module that records Settings(...) kwargs."""
    fake = MagicMock()
    fake.HttpClient.side_effect = lambda *a, **k: MagicMock(name="HttpClient")
    fake.config = MagicMock()
    fake.config.Settings = MagicMock(side_effect=lambda **k: MagicMock(name="Settings", _kwargs=k))
    return fake


@pytest.fixture
def remote_chroma():
    """Force the remote HttpClient branch with chromadb stubbed."""
    fake = _stub_chromadb()
    with (
        patch.dict(sys.modules, {"chromadb": fake, "chromadb.config": fake.config}),
        patch.object(sync_mod, "_CHROMADB_HOST", "chroma-host"),
        patch.object(async_mod, "_CHROMADB_HOST", "chroma-host"),
    ):
        sync_mod._sync_client_cache.clear()
        async_mod._async_client_cache.clear()
        yield fake
        sync_mod._sync_client_cache.clear()
        async_mod._async_client_cache.clear()


def test_sync_http_client_sends_token_when_configured(remote_chroma):
    with patch.object(sync_mod, "chroma_client_auth_kwargs", return_value={"chroma_client_auth_credentials": "tok"}):
        sync_mod.get_chromadb_client()

    _, kwargs = remote_chroma.config.Settings.call_args
    assert kwargs["chroma_client_auth_credentials"] == "tok"


def test_sync_http_client_omits_auth_when_unset(remote_chroma):
    with patch.object(sync_mod, "chroma_client_auth_kwargs", return_value={}):
        sync_mod.get_chromadb_client()

    _, kwargs = remote_chroma.config.Settings.call_args
    assert "chroma_client_auth_credentials" not in kwargs


@pytest.mark.asyncio
async def test_async_http_client_sends_token_when_configured(remote_chroma):
    with patch.object(async_mod, "chroma_client_auth_kwargs", return_value={"chroma_client_auth_credentials": "tok"}):
        await async_mod.get_async_chromadb_client()

    _, kwargs = remote_chroma.config.Settings.call_args
    assert kwargs["chroma_client_auth_credentials"] == "tok"
