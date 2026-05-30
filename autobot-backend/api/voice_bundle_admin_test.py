# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for per-user voice bundle assignment (GH#8605)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# resolve_bundle_for_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_bundle_user_override():
    """DB override wins over role default."""
    from api.redis_mcp.rbac import resolve_bundle_for_user

    mock_row = MagicMock()
    mock_row.fetchone.return_value = ("voice_extended",)
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    with patch("database.session.get_async_session", return_value=mock_session):
        bundle, resolution = await resolve_bundle_for_user("user-123", role="user")

    assert bundle == "voice_extended"
    assert resolution == "user_override"


@pytest.mark.asyncio
async def test_resolve_bundle_role_default_admin():
    """Admin role defaults to voice_admin when no DB override."""
    from api.redis_mcp.rbac import resolve_bundle_for_user

    mock_row = MagicMock()
    mock_row.fetchone.return_value = None
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    with patch("database.session.get_async_session", return_value=mock_session):
        bundle, resolution = await resolve_bundle_for_user("admin-1", role="admin")

    assert bundle == "voice_admin"
    assert resolution == "role_default"


@pytest.mark.asyncio
async def test_resolve_bundle_global_env_fallback():
    """Falls back to AUTOBOT_VOICE_TOOLSETS env when no override or role match."""
    from api.redis_mcp.rbac import resolve_bundle_for_user

    mock_row = MagicMock()
    mock_row.fetchone.return_value = None
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)

    import os

    with (
        patch("database.session.get_async_session", return_value=mock_session),
        patch.dict(os.environ, {"AUTOBOT_VOICE_TOOLSETS": "voice_extended"}),
    ):
        bundle, resolution = await resolve_bundle_for_user("user-99", role="unknown_role")

    assert bundle == "voice_extended"
    assert resolution == "global_env"


@pytest.mark.asyncio
async def test_resolve_bundle_db_failure_falls_through():
    """DB failure should not crash — falls through to role default."""
    from api.redis_mcp.rbac import resolve_bundle_for_user

    with patch("database.session.get_async_session", side_effect=Exception("DB down")):
        bundle, resolution = await resolve_bundle_for_user("user-42", role="user")

    assert bundle == "voice_safe"
    assert resolution == "role_default"


# ---------------------------------------------------------------------------
# Admin endpoint: PUT /admin/voice/bundle/{user_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_user_bundle_invalid_bundle():
    """Reject unknown bundle names."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.voice_bundle_admin import bundle_admin_router

    app = FastAPI()
    app.include_router(bundle_admin_router)

    with TestClient(app) as client:
        with patch(
            "api.voice_bundle_admin._require_admin",
            return_value={"username": "admin", "role": "admin"},
        ):
            resp = client.put(
                "/admin/voice/bundle/user-abc",
                json={"bundle_name": "voice_godmode"},
                headers={"Authorization": "Bearer fake"},
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_user_cannot_call_admin_bundle_endpoint_unauthenticated():
    """Admin endpoint must reject unauthenticated callers."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.voice_bundle_admin import bundle_admin_router

    app = FastAPI()
    app.include_router(bundle_admin_router)

    with TestClient(app, raise_server_exceptions=False) as client:
        with patch(
            "api.voice_bundle_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=None)),
        ):
            resp = client.get("/admin/voice/bundle/user-abc")
    # Expect 401 or 403
    assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# list_realtime_tools with user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_realtime_tools_uses_user_bundle():
    """list_realtime_tools should use per-user bundle when user_id provided."""
    from services.realtime_mcp_bridge import RealtimeMCPBridge

    bridge = RealtimeMCPBridge(is_admin=False)
    bridge._bundle = "voice_safe"  # global default

    fake_tool = MagicMock()
    fake_tool.name = "redis_get"

    with (
        patch.object(bridge, "_discover_tools", AsyncMock(return_value=[fake_tool])),
        patch(
            "api.redis_mcp.rbac.resolve_bundle_for_user",
            AsyncMock(return_value=("voice_extended", "user_override")),
        ),
        patch(
            "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
            return_value=lambda tools, bundle, is_admin, disabled_tools=None: tools,
        ),
    ):
        result = await bridge.list_realtime_tools(user_id="user-1", role="user")

    assert len(result) == 1
    assert result[0].name == "redis_get"


# ---------------------------------------------------------------------------
# set_user_bundle — GH#9096 / GH#9098
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_user_bundle_emit_raises_in_except_still_raises_http_exception():
    """Failure-path emit that raises must not swallow the original HTTPException (GH#9096)."""
    from fastapi import HTTPException

    from api.voice_bundle_user import BundleAssignRequest, set_user_bundle

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("db gone"))
    mock_session.commit = AsyncMock()

    with (
        patch("user_management.database.get_async_session", return_value=mock_session),
        patch("api.voice_bundle_user.emit", side_effect=RuntimeError("audit bus down")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await set_user_bundle(
                "user-42",
                BundleAssignRequest(bundle_name="voice_safe"),
                MagicMock(),
                {"user_id": "admin-1", "role": "admin"},
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Database error"


@pytest.mark.asyncio
async def test_set_user_bundle_success_audit_uses_stored_bundle_name():
    """Success audit must use DB-stored value for bundle_name, not body.bundle_name (GH#9098).

    The requested value goes into requested_bundle_name; the actual stored
    value (returned by the re-read after commit) goes into bundle_name.
    """
    from api.voice_bundle_user import BundleAssignRequest, set_user_bundle

    mock_row = MagicMock()
    mock_row.fetchone.return_value = ("voice_extended",)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(return_value=mock_row)
    mock_session.commit = AsyncMock()

    emitted: list = []

    with (
        patch("user_management.database.get_async_session", return_value=mock_session),
        patch("api.voice_bundle_user.emit", side_effect=emitted.append),
    ):
        resp = await set_user_bundle(
            "user-77",
            BundleAssignRequest(bundle_name="voice_safe"),
            MagicMock(),
            {"user_id": "admin-1", "role": "admin"},
        )

    assert resp.bundle_name == "voice_extended"
    assert len(emitted) == 1
    event = emitted[0]
    assert event.outcome == "success"
    assert event.metadata.get("bundle_name") == "voice_extended"
    assert event.metadata.get("requested_bundle_name") == "voice_safe"
