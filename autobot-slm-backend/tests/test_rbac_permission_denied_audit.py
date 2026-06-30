# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for _emit_permission_denied_audit (GH #10719).

Verifies that:
- A permission denial writes an AuditLog entry with the correct fields
  (user_id, action=PERMISSION_DENIED, resource_type=ENDPOINT, outcome="denied",
   permission in details, path in details).
- If the DB write raises, the function swallows the exception, logs an error,
  and does NOT propagate — the deny flow is unaffected.

Bootstrap strategy mirrors test_rbac_middleware_cache.py: stub heavy deps
into sys.modules before loading the module under test via importlib.
"""

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap — must happen before any import of rbac_middleware
# ---------------------------------------------------------------------------

_SLM_ROOT = Path(__file__).parent.parent
_SHARED_ROOT = _SLM_ROOT.parent / "autobot_shared"

for _p in (str(_SLM_ROOT), str(_SHARED_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_MOCK_NAMES = [
    "fastapi",
    "fastapi.exceptions",
    "fastapi.responses",
    "autobot_shared",
    "autobot_shared.redis_client",
    "autobot_shared.auth",
    "autobot_shared.auth.permissions",
    "user_management.services",
    "user_management.database",
    "user_management.config",
    # audit model — we supply a hand-rolled stub below
    "user_management.models.audit",
    "user_management.models",
    "user_management.models.base",
]
for _name in _MOCK_NAMES:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

import http  # noqa: E402

_fastapi_mock = sys.modules["fastapi"]
_fastapi_mock.HTTPException = type("HTTPException", (Exception,), {"__init__": lambda s, **kw: None})
_fastapi_mock.Request = type("Request", (), {})
_fastapi_mock.status = http.HTTPStatus

# Provide just enough of the AuditLog model/constants for the module to import.
_audit_mod = sys.modules["user_management.models.audit"]


class _AuditLog:
    """Minimal AuditLog stand-in captured by tests to inspect fields."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _AuditAction:
    PERMISSION_DENIED = "permission_denied"


class _AuditResourceType:
    ENDPOINT = "endpoint"


_audit_mod.AuditLog = _AuditLog
_audit_mod.AuditAction = _AuditAction
_audit_mod.AuditResourceType = _AuditResourceType

# Load the module under test
_SPEC = importlib.util.spec_from_file_location(
    "user_management.middleware.rbac_middleware",
    _SLM_ROOT / "user_management" / "middleware" / "rbac_middleware.py",
)
_rbac_mod: types.ModuleType = types.ModuleType(_SPEC.name)
_SPEC.loader.exec_module(_rbac_mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_ctx(session):
    """Return an async context manager that yields *session*."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmitPermissionDeniedAudit:
    @pytest.mark.asyncio
    async def test_writes_audit_entry_with_correct_fields(self):
        """A denied permission call persists an AuditLog with the right field values."""
        user_id = uuid.uuid4()
        permission = "agents.write"
        path = "/api/agents"
        ip = "10.0.0.1"
        ua = "pytest/1.0"

        added_entries = []

        session = MagicMock()
        session.add = MagicMock(side_effect=added_entries.append)

        with patch.object(_rbac_mod, "db_session_context", return_value=_make_session_ctx(session)):
            await _rbac_mod._emit_permission_denied_audit(user_id, permission, path, ip_address=ip, user_agent=ua)

        assert len(added_entries) == 1
        entry = added_entries[0]
        assert entry.user_id == user_id
        assert entry.action == "permission_denied"
        assert entry.resource_type == "endpoint"
        assert entry.outcome == "denied"
        assert entry.details["permission"] == permission
        assert entry.details["path"] == path
        assert entry.ip_address == ip
        assert entry.user_agent == ua

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed_and_does_not_propagate(self):
        """If the DB session raises, _emit_permission_denied_audit catches it silently."""
        user_id = uuid.uuid4()

        broken_ctx = MagicMock()
        broken_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        broken_ctx.__aexit__ = AsyncMock(return_value=False)

        # Must NOT raise — the deny flow must be unaffected
        with patch.object(_rbac_mod, "db_session_context", return_value=broken_ctx):
            await _rbac_mod._emit_permission_denied_audit(user_id, "agents.read", "/api/x")

    @pytest.mark.asyncio
    async def test_db_failure_logs_error(self, caplog):
        """A DB failure is logged at ERROR level (not silently swallowed without trace)."""
        import logging

        user_id = uuid.uuid4()

        broken_ctx = MagicMock()
        broken_ctx.__aenter__ = AsyncMock(side_effect=OSError("timeout"))
        broken_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(_rbac_mod, "db_session_context", return_value=broken_ctx):
            with caplog.at_level(logging.ERROR):
                await _rbac_mod._emit_permission_denied_audit(user_id, "admin.system", "/admin")

        assert any("failed to persist permission-denied audit entry" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_none_user_id_is_accepted(self):
        """user_id=None (e.g. anonymous) must not crash the audit call."""
        added_entries = []
        session = MagicMock()
        session.add = MagicMock(side_effect=added_entries.append)

        with patch.object(_rbac_mod, "db_session_context", return_value=_make_session_ctx(session)):
            await _rbac_mod._emit_permission_denied_audit(None, "users.read", "/api/users")

        assert len(added_entries) == 1
        assert added_entries[0].user_id is None

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_none(self):
        """ip_address and user_agent default to None when not supplied."""
        added_entries = []
        session = MagicMock()
        session.add = MagicMock(side_effect=added_entries.append)

        with patch.object(_rbac_mod, "db_session_context", return_value=_make_session_ctx(session)):
            await _rbac_mod._emit_permission_denied_audit(uuid.uuid4(), "reports.view", "/reports")

        entry = added_entries[0]
        assert entry.ip_address is None
        assert entry.user_agent is None
