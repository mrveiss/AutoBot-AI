# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20631: holding service.management does not open the SLM; only an admin and the agent key get in.

The REAL ``_SM`` and ``_SM_OR_AGENT`` dependencies run over HTTP on routers mounted the way
``main.py`` mounts them, with real tokens. Revocation (Redis) and the deny audit are stood in for.
The refusal of a person itself is ``get_current_user``'s (#20628); this file proves it reaches both gates.
"""

import ast
import secrets
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402

from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))
_MAIN = Path(__file__).resolve().parents[2] / "main.py"
_INTERNAL_KEY = "internal-key-for-this-test"  # pragma: allowlist secret


def _client() -> TestClient:
    app = fastapi.FastAPI()
    app.add_api_route("/sm", lambda: {"ok": True}, dependencies=[fastapi.Depends(_auth.require_service_management)])
    app.add_api_route(
        "/agent", lambda: {"ok": True}, dependencies=[fastapi.Depends(_auth.require_service_management_or_internal)]
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_redis_no_db():
    with (
        patch.object(_auth, "is_jti_revoked", AsyncMock(return_value=False)),
        patch.object(_auth, "is_token_revoked_by_password_change", AsyncMock(return_value=False)),
        patch.object(_auth._permission_gate, "_wire_rbac", lambda: None),
        patch.object(_auth, "verify_internal_api_key", lambda key: key == _INTERNAL_KEY),
        patch("autobot_shared.auth.permission_gate.audit_permission_denied", AsyncMock()),
    ):
        yield


def _bearer(role: str, admin: bool) -> dict:
    token = _auth.auth_service.create_access_token(data={"sub": "someone", "admin": admin, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_the_operator_role_does_hold_service_management() -> None:
    """The control for the refusals below: they are not a missing permission."""
    assert Permission.SERVICE_MANAGEMENT in ROLE_PERMISSIONS[Role.OPERATOR]


@pytest.mark.parametrize("path", ["/sm", "/agent"])
def test_a_service_management_non_admin_is_refused(path) -> None:
    response = _client().get(path, headers=_bearer(Role.OPERATOR.value, admin=False))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("path", ["/sm", "/agent"])
def test_the_control_an_admin_gets_through(path) -> None:
    response = _client().get(path, headers=_bearer(Role.ADMIN.value, admin=True))
    assert response.status_code == 200, response.text


def test_the_internal_key_passes_the_agent_gate_with_no_user() -> None:
    assert _client().get("/agent", headers={"X-Internal-API-Key": _INTERNAL_KEY}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-Internal-API-Key": "wrong"}], ids=["no key", "wrong key"])
def test_the_control_no_key_and_a_wrong_key_get_no_entry(headers) -> None:
    assert _client().get("/agent", headers=headers).status_code == 401


def test_main_mounts_these_same_gates() -> None:
    """What is tested above is what ``main.py`` names, so a renamed gate cannot leave this file behind."""
    assigned = {
        node.targets[0].id: ast.unparse(node.value)
        for node in ast.parse(_MAIN.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert assigned["_SM"] == "[Depends(require_service_management)]"
    assert assigned["_SM_OR_AGENT"] == "[Depends(require_service_management_or_internal)]"
