# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A key-authenticated route refuses an out-of-scope key with 403, through the real dependencies (#16040).

``require_key_permission`` is exercised over HTTP. The ``X-API-Key`` header goes
through the real ``get_api_key_user`` (key validation, owner lookup, grace-period
check, payload) and then the real ``permission_allowed``. Only the two database
edges are stood in for: ``APIKeyService.validate_key`` and the owner lookup.

No production route accepts a key yet; which ones will is #16294's decision. So
the routes here are test routes, as the owner ruled for #16040 AC4 and AC6 on
2026-09-11.
"""

import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402

from autobot_shared.auth.key_scopes import scope_granted  # noqa: E402
from autobot_shared.auth.permissions import Permission  # noqa: E402
from services.api_key_authority import API_KEY_SCOPES_ENFORCED_FROM  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))
_KEY = "ak_test_plaintext"
#: A day after the configured enforcement cutoff, so the key is held to its scopes (no AC5 grace).
_AFTER_ENFORCEMENT = datetime.fromisoformat(API_KEY_SCOPES_ENFORCED_FROM).replace(tzinfo=timezone.utc) + timedelta(
    days=1
)


def _app() -> fastapi.FastAPI:
    app = fastapi.FastAPI()

    @app.get("/knowledge")
    async def read(caller: dict = fastapi.Depends(_auth.require_key_permission(Permission.KNOWLEDGE_READ))):
        return {"sub": caller["sub"]}

    @app.post("/knowledge")
    async def write(caller: dict = fastapi.Depends(_auth.require_key_permission(Permission.KNOWLEDGE_WRITE))):
        return {"sub": caller["sub"]}

    @app.put("/settings")
    async def configure(caller: dict = fastapi.Depends(_auth.require_key_permission(Permission.ADMIN_CONFIG_WRITE))):
        return {"sub": caller["sub"]}

    async def _no_db():
        yield None

    app.dependency_overrides[_auth.get_slm_db] = _no_db
    return app


def _api_key(scopes: list) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        key_prefix="ak_test",
        scopes=scopes,
        created_at=_AFTER_ENFORCEMENT,
        has_scope=lambda scope: scope_granted(scopes, scope),  # what APIKey.has_scope delegates to
    )


@pytest.fixture
def call(monkeypatch):
    """Send one request as a key holding *scopes*, owned by an admin or a plain user."""

    def _call(method: str, path: str, *, scopes=("knowledge:read",), owner_admin=True, key=_KEY, known=True):
        service = MagicMock()
        service.return_value.validate_key = AsyncMock(return_value=_api_key(list(scopes)) if known else None)
        for name, attr, value in (
            ("user_management.services.api_key_service", "APIKeyService", service),
            ("user_management.services.base_service", "TenantContext", MagicMock()),
        ):
            module = ModuleType(name)
            setattr(module, attr, value)
            monkeypatch.setitem(sys.modules, name, module)
        owner = SimpleNamespace(username="owner", is_platform_admin=owner_admin)
        headers = {"X-API-Key": key} if key else {}
        with patch.object(_auth, "_get_user_for_api_key", AsyncMock(return_value=owner)):
            return TestClient(_app()).request(method, path, headers=headers)

    return _call


def test_a_narrow_key_is_refused_an_out_of_scope_route_with_403(call):
    """#16040 AC6. The owner is an admin and holds knowledge.write; the key does not, so it is refused."""
    response = call("POST", "/knowledge")

    assert response.status_code == 403, response.text
    assert "knowledge.write" in response.json()["detail"]


def test_the_control_the_same_key_is_allowed_its_in_scope_route(call):
    response = call("GET", "/knowledge")

    assert response.status_code == 200, response.text
    assert response.json() == {"sub": "owner"}


def test_a_key_never_exceeds_its_owner(call):
    """A plain user's key carrying ``admin:*`` still cannot do what its owner cannot."""
    assert call("PUT", "/settings", scopes=("admin:*",), owner_admin=False).status_code == 403
    assert call("GET", "/knowledge", scopes=("admin:*",), owner_admin=False).status_code == 200


@pytest.mark.parametrize(("key", "known"), [(None, True), (_KEY, False)], ids=["no key", "unknown key"])
def test_a_missing_or_unknown_key_is_401_not_403(call, key, known):
    """Not authenticated is 401. 403 is kept for an authenticated key that lacks the scope."""
    assert call("GET", "/knowledge", key=key, known=known).status_code == 401
