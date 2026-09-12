# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An admitted agent-config write records who made it, not the literal "admin" (#16547).

Same defect #16278/#16501 fixed in `api/settings.py`: `update_agent_model`,
`enable_agent` and `disable_agent` were gated by `check_admin_permission` but
discarded which admin (or the internal-service key) it admitted before
writing the audit revision. Under test, `auth_middleware` is a stub whose
`check_admin_permission` admits every caller and whose session user is
"test-user" (`testkit/auth_middleware_stub.py`), so a passing request here
proves the wiring: `require_settings_admin`'s resolved actor reaches
`create_revision`, not a hardcoded string.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.agent_config import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_unified_config_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.get_nested = MagicMock(side_effect=lambda _key, default=None: default)
    mgr.set_nested = MagicMock()
    mgr.save_settings = MagicMock()
    return mgr


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/agents/orchestrator/model", {"agent_id": "orchestrator", "model": "llama3"}),
        ("post", "/agents/orchestrator/enable", None),
        ("post", "/agents/orchestrator/disable", None),
    ],
)
def test_recorded_author_is_not_the_literal_admin(method, path, json):
    revisions = MagicMock()
    revisions.return_value.create_revision = AsyncMock()

    with (
        patch("api.agent_config.ConfigRevisionService", revisions),
        patch("api.agent_config.ConfigService.clear_cache"),
        patch("config.unified_config_manager", _fake_unified_config_manager()),
        patch(
            "api.agent_config.get_db_session",
            return_value=MagicMock(__aenter__=AsyncMock(return_value=MagicMock()), __aexit__=AsyncMock()),
        ),
    ):
        client = _client()
        response = getattr(client, method)(path, json=json)

    assert response.status_code == 200, response.text
    created_by = revisions.return_value.create_revision.await_args.kwargs["created_by"]
    assert created_by != "admin", "must record the actual actor, not the literal string"
    assert created_by == "test-user", "the stub session's user, per testkit/auth_middleware_stub.py"
