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

import sys
from unittest.mock import MagicMock, patch

import pytest

import utils.async_chromadb_client as async_mod
import utils.chromadb_auth as auth_mod
import utils.chromadb_client as sync_mod


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
