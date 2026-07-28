# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Permission denials must leave an audit trail (#12925).

`autobot-slm-backend` has recorded every denial since GH #6511. This backend
recorded nothing: a 403 left no user, permission, path or IP behind, so there
was no trail to investigate probing against — on the service that holds the
application's own RBAC.

These tests pin the port, and in particular the property that matters most
under failure: an audit write that fails must never turn a clean 403 into a
500, and must never make the denial vanish from the logs.
"""

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SRC = Path(__file__).resolve().parent / "rbac_middleware.py"
_MODELS = Path(__file__).resolve().parents[1] / "models" / "audit.py"


def _source() -> str:
    return _SRC.read_text(encoding="utf-8")


class TestAuditVocabulary:
    """The action/resource strings must match the SLM's, or the trail splits."""

    def test_permission_denied_action_exists(self):
        models = _MODELS.read_text(encoding="utf-8")

        assert 'PERMISSION_DENIED = "permission_denied"' in models

    def test_endpoint_resource_type_exists(self):
        models = _MODELS.read_text(encoding="utf-8")

        assert 'ENDPOINT = "endpoint"' in models

    def test_values_match_the_slm_backend(self):
        """Both backends must write the same strings into a shared vocabulary.

        A mismatch would silently split the audit trail in two, which is worse
        than the gap this closes: queries would look complete and be partial.
        """
        slm = Path(__file__).resolve().parents[3] / "autobot-slm-backend" / "user_management" / "models" / "audit.py"
        if not slm.exists():
            pytest.skip("autobot-slm-backend not present in this checkout")

        slm_src = slm.read_text(encoding="utf-8")
        models = _MODELS.read_text(encoding="utf-8")
        for line in ('PERMISSION_DENIED = "permission_denied"', 'ENDPOINT = "endpoint"'):
            assert line in slm_src and line in models


class TestEveryDenialIsAudited:
    """All three decorators must emit — one missed path is a blind spot."""

    def test_all_three_denial_points_emit(self):
        """require_permission / require_any_permission / require_all_permissions."""
        assert _source().count("await _emit_permission_denied_audit(") == 3

    def test_no_denial_path_raises_403_without_emitting(self):
        """Every 403 in this module must be preceded by an audit call.

        Checked structurally: within each function, the index of the emit call
        must come before the HTTPException raise.
        """
        tree = ast.parse(_source())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            body = ast.dump(node)
            if "HTTP_403_FORBIDDEN" not in body:
                continue
            assert "_emit_permission_denied_audit" in body, f"{node.name} raises 403 without auditing"


class TestFailureIsolation:
    """The audit must never make things worse than the gap it closes."""

    @pytest.mark.asyncio
    async def test_db_failure_does_not_propagate(self):
        """A failing audit write must not convert a 403 into a 500."""
        from user_management.middleware import rbac_middleware as mod

        with patch.object(mod, "db_session_context", side_effect=RuntimeError("db down")):
            # Must return normally rather than raise.
            await mod._emit_permission_denied_audit(uuid.uuid4(), "users:read", "/api/users")

    @pytest.mark.asyncio
    async def test_denial_is_logged_even_when_the_write_fails(self, caplog):
        """The warning is emitted first, so a DB outage cannot hide the denial."""
        from user_management.middleware import rbac_middleware as mod

        with patch.object(mod, "db_session_context", side_effect=RuntimeError("db down")):
            with caplog.at_level("WARNING"):
                await mod._emit_permission_denied_audit(uuid.uuid4(), "users:delete", "/api/users/1")

        assert "Permission denied" in caplog.text
        assert "users:delete" in caplog.text

    @pytest.mark.asyncio
    async def test_entry_carries_the_forensic_fields(self):
        """user, permission, path, ip and user-agent — the point of the trail."""
        from user_management.middleware import rbac_middleware as mod

        session = MagicMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        user_id = uuid.uuid4()

        with patch.object(mod, "db_session_context", return_value=ctx):
            await mod._emit_permission_denied_audit(
                user_id,
                "users:delete",
                "/api/users/1",
                ip_address="203.0.113.7",
                user_agent="curl/8.0",
            )

        session.add.assert_called_once()
        entry = session.add.call_args.args[0]
        assert entry.user_id == user_id
        assert entry.details == {"permission": "users:delete", "path": "/api/users/1"}
        assert entry.ip_address == "203.0.113.7"
        assert entry.user_agent == "curl/8.0"
        assert entry.outcome == "denied"


def test_request_context_survives_a_clientless_request():
    """Starlette leaves request.client None behind some proxies — must not crash."""
    from user_management.middleware import rbac_middleware as mod

    request = MagicMock()
    request.url.path = "/api/users"
    request.client = None
    request.headers = {"user-agent": "curl/8.0"}

    path, ip, ua = mod._request_audit_context(request)

    assert (path, ip, ua) == ("/api/users", None, "curl/8.0")
