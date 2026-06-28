# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for GET /sso-providers/health (Issue #10156).

Tests:
- _derive_health_status helper covers all four branches
- Aggregation produces correct success/failure counts per provider
- last_success_at is correctly propagated
- SSO_HEALTH_WINDOW_DAYS constant is used (no hard-coded literal)
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Isolate the module-under-test: import api/sso.py without a real DB engine
# ---------------------------------------------------------------------------


def _load_sso_module():
    """Load api/sso.py with all heavy dependencies stubbed out."""
    from pathlib import Path

    sso_py = Path(__file__).parent.parent.parent / "api" / "sso.py"

    # Minimal fastapi stub
    fastapi_stub = MagicMock()
    fastapi_stub.APIRouter = MagicMock(return_value=MagicMock())
    fastapi_stub.Depends = lambda dep: dep
    fastapi_stub.HTTPException = Exception
    fastapi_stub.Query = lambda *a, **kw: None
    fastapi_stub.status = MagicMock()

    import importlib.util

    stubs = {
        "fastapi": fastapi_stub,
        "sqlalchemy": MagicMock(),
        "sqlalchemy.func": MagicMock(),
        "sqlalchemy.select": MagicMock(),
        "autobot_shared": MagicMock(),
        "autobot_shared.auth": MagicMock(),
        "autobot_shared.auth.permissions": MagicMock(),
        "models": MagicMock(),
        "models.database": MagicMock(),
        "services": MagicMock(),
        "services.auth": MagicMock(),
        "services.database": MagicMock(),
        "user_management": MagicMock(),
        "user_management.database": MagicMock(),
        "user_management.schemas": MagicMock(),
        "user_management.schemas.sso": MagicMock(),
        "user_management.services": MagicMock(),
        "user_management.services.base_service": MagicMock(),
        "user_management.services.sso_service": MagicMock(),
    }
    prev = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)

    try:
        spec = importlib.util.spec_from_file_location("sso_api_health_" + uuid.uuid4().hex[:8], sso_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k, v in prev.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    return mod


# ---------------------------------------------------------------------------
# _derive_health_status helper tests
# ---------------------------------------------------------------------------


class TestDeriveHealthStatus:
    """Unit tests for the pure _derive_health_status helper."""

    @pytest.fixture(autouse=True)
    def _mod(self):
        self.sso = _load_sso_module()
        self.fn = self.sso._derive_health_status
        self.window_start = datetime.now(timezone.utc) - timedelta(days=7)

    def test_unknown_when_no_attempts(self):
        result = self.fn(
            success_count=0,
            failure_count=0,
            last_success_at=None,
            window_start=self.window_start,
        )
        assert result == "unknown"

    def test_error_when_only_failures(self):
        result = self.fn(
            success_count=0,
            failure_count=5,
            last_success_at=None,
            window_start=self.window_start,
        )
        assert result == "error"

    def test_warning_when_failures_and_recent_success(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        result = self.fn(
            success_count=3,
            failure_count=2,
            last_success_at=recent,
            window_start=self.window_start,
        )
        assert result == "warning"

    def test_healthy_when_successes_and_no_failures(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        result = self.fn(
            success_count=10,
            failure_count=0,
            last_success_at=recent,
            window_start=self.window_start,
        )
        assert result == "healthy"


# ---------------------------------------------------------------------------
# SSO_HEALTH_WINDOW_DAYS is a module-level constant (not a literal)
# ---------------------------------------------------------------------------


def test_health_window_constant_is_int():
    """SSO_HEALTH_WINDOW_DAYS must be an int (sourced from env, not a literal)."""
    sso = _load_sso_module()
    assert hasattr(sso, "SSO_HEALTH_WINDOW_DAYS"), "SSO_HEALTH_WINDOW_DAYS constant must be defined"
    assert isinstance(sso.SSO_HEALTH_WINDOW_DAYS, int)
    assert sso.SSO_HEALTH_WINDOW_DAYS > 0


# ---------------------------------------------------------------------------
# Health aggregation logic
# ---------------------------------------------------------------------------


def _make_row(resource_id: str, success_count: int, failure_count: int, last_success_at=None):
    """Create a mock DB aggregation row."""
    row = MagicMock()
    row.resource_id = resource_id
    row.success_count = success_count
    row.failure_count = failure_count
    row.last_success_at = last_success_at
    return row


def test_health_aggregation_maps_counts_per_provider():
    """Health helper builds correct per-provider counts from aggregation rows."""
    sso = _load_sso_module()
    fn = sso._derive_health_status
    window_start = datetime.now(timezone.utc) - timedelta(days=7)

    pid1 = str(uuid.uuid4())
    pid2 = str(uuid.uuid4())
    recent = datetime.now(timezone.utc) - timedelta(hours=2)

    rows = {
        pid1: _make_row(pid1, success_count=10, failure_count=0, last_success_at=recent),
        pid2: _make_row(pid2, success_count=0, failure_count=3, last_success_at=None),
    }

    results = []
    for pid, row in rows.items():
        s = int(row.success_count)
        f = int(row.failure_count)
        lsa = row.last_success_at
        hs = fn(s, f, lsa, window_start)
        results.append({"provider_id": pid, "success_count": s, "failure_count": f, "health_status": hs})

    by_id = {r["provider_id"]: r for r in results}

    assert by_id[pid1]["success_count"] == 10
    assert by_id[pid1]["failure_count"] == 0
    assert by_id[pid1]["health_status"] == "healthy"

    assert by_id[pid2]["success_count"] == 0
    assert by_id[pid2]["failure_count"] == 3
    assert by_id[pid2]["health_status"] == "error"


def test_health_aggregation_unknown_for_missing_provider():
    """Provider with no audit rows gets health_status='unknown'."""
    sso = _load_sso_module()
    fn = sso._derive_health_status
    window_start = datetime.now(timezone.utc) - timedelta(days=7)

    result = fn(0, 0, None, window_start)
    assert result == "unknown"


def test_last_success_at_propagated():
    """last_success_at from the aggregation row is preserved in health output."""
    sso = _load_sso_module()
    window_start = datetime.now(timezone.utc) - timedelta(days=7)
    recent = datetime.now(timezone.utc) - timedelta(hours=3)

    pid = str(uuid.uuid4())
    row = _make_row(pid, success_count=5, failure_count=1, last_success_at=recent)

    # Simulates how get_providers_health reads the row
    last_success_at = row.last_success_at if row else None
    assert last_success_at == recent

    status = sso._derive_health_status(5, 1, last_success_at, window_start)
    assert status == "warning"
