# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
create_connector API tests for the Google Drive surface (Issue #9003).

Verifies the create endpoint now accepts ``connector_type="gdrive"`` (previously
422'd because gdrive was absent from ``_SUPPORTED_TYPES``) and that an OAuth
``secret_id`` is attached by reference — never re-stored — with the bearer token
resolved at invocation time via ``get_access_token`` (ADR-007 §10).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import knowledge.connectors.gdrive  # noqa: F401 — register gdrive
from api import knowledge_connectors as mod
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.schemas.connectors import CreateConnectorRequest


def test_gdrive_registered_and_supported():
    """gdrive is reachable: registered class is non-None and in supported types."""
    assert "gdrive" in mod._SUPPORTED_TYPES
    assert ConnectorRegistry.get_registered_class("gdrive") is not None


@pytest.mark.asyncio
async def test_create_rejects_unknown_type():
    """An unregistered connector_type still 422s."""
    req = CreateConnectorRequest(connector_type="no_such_type", name="x")
    with pytest.raises(HTTPException) as exc:
        await mod.create_connector(req)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_gdrive_with_oauth_secret_attaches_by_reference():
    """gdrive create with a secret_id attaches it, skips store, resolves token via OAuth."""
    req = CreateConnectorRequest(
        connector_type="gdrive",
        name="My Drive",
        config={"source_type": "mydrive", "sync_subfolders": True},
        secret_id="sec-oauth-123",
    )

    store = MagicMock()
    store.store = AsyncMock()  # must NOT be called when secret_id is supplied
    store.get_access_token = AsyncMock(return_value="live-access-token")

    healthy_instance = MagicMock()
    healthy_instance.test_connection = AsyncMock(return_value=True)

    saved = {}

    async def _fake_save(cfg):
        saved["cfg"] = cfg

    with (
        patch.object(mod, "get_credential_store", return_value=store),
        patch.object(mod, "_load_or_create_instance", AsyncMock(return_value=healthy_instance)),
        patch.object(mod, "_save_connector", _fake_save),
        patch.object(mod, "_maybe_schedule", AsyncMock()),
    ):
        result = await mod.create_connector(req)

    # secret attached by reference; credentials never re-stored.
    store.store.assert_not_called()
    cfg = saved["cfg"]
    assert cfg.secret_id == "sec-oauth-123"
    assert cfg.auth_type == mod._OAUTH_AUTH_TYPE
    assert cfg.connector_type == "gdrive"
    # OAuth resolver produced a live access token for the connection test.
    store.get_access_token.assert_awaited_once_with("sec-oauth-123", "system")
    assert result["connector_id"]
    # secret_id is internal — never echoed in the public config.
    assert "secret_id" not in result["config"]


@pytest.mark.asyncio
async def test_oauth_full_config_injects_token_into_bearer_field():
    """OAuth resolution injects the access token into BearerAuth's sensitive field."""
    from autobot_shared.auth import BearerAuth
    from knowledge.connectors.models import ConnectorConfig

    cfg = ConnectorConfig(
        connector_id="c1",
        connector_type="gdrive",
        name="g",
        config={"source_type": "mydrive"},
        secret_id="sec-1",
        auth_type=mod._OAUTH_AUTH_TYPE,
        owner_id="user-1",
    )
    store = MagicMock()
    store.get_access_token = AsyncMock(return_value="tok-abc")
    with patch.object(mod, "get_credential_store", return_value=store):
        full = await mod._oauth_full_config(cfg, BearerAuth, "user-1")
    assert full["token"] == "tok-abc"
    assert full["source_type"] == "mydrive"
    store.get_access_token.assert_awaited_once_with("sec-1", "user-1")
