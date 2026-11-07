# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unreadable registry answers 503 through `with_error_handling`-wrapped handlers (#17982).

Before: the shared decorator swallowed `RegistryUnavailable` into a generic
trace-id 500 before the app-level handler could map it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codebase_analytics.endpoints import ownership
from api.codebase_analytics.endpoints.shared import require_source_access
from api.codebase_analytics.router import router as analytics_router
from api.codebase_analytics.source_storage import RegistryUnavailable
from auth_middleware import check_admin_permission


def test_ownership_analysis_answers_503_not_500_when_the_registry_is_down():
    from initialization.registry_handlers import register_registry_handlers

    app = FastAPI()
    register_registry_handlers(app)
    # The package router, with its gates: the real mount, not ownership.router bare.
    # The two gates are overridden (they need a live session), never removed.
    app.include_router(analytics_router)
    app.dependency_overrides[check_admin_permission] = lambda: None
    app.dependency_overrides[require_source_access] = lambda: None
    down = AsyncMock(side_effect=RegistryUnavailable("secret-host:6379 refused"))
    with (
        patch.object(ownership, "_check_ownership_cache", AsyncMock(return_value=None)),
        patch("api.codebase_analytics.source_storage.get_default_source_id", down),
    ):
        response = TestClient(app, raise_server_exceptions=False).get("/ownership/analysis")
    assert response.status_code == 503, response.text
    assert "secret-host" not in response.text
