# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An admitted agent-config write records who made it, not the literal "admin" (#16547, #16541).

Same defect #16278/#16501 fixed in `api/settings.py`: `update_agent_model`,
`enable_agent` and `disable_agent` were gated by `check_admin_permission` but
discarded which admin (or the internal-service key) it admitted before
writing the audit revision. Under test, `auth_middleware` is a stub whose
`check_admin_permission` admits every caller and whose session user is
"test-user" (`testkit/auth_middleware_stub.py`), so a passing request here
proves the wiring: `require_settings_admin`'s resolved actor reaches
`create_revision`, not a hardcoded string.

#16541 AC2: also forces the internal-service-key branch via
`verify_internal_api_key` (the same override `settings_config_test.py`'s
`TestAnAdmittedWriteRecordsItsAuthor` uses), expecting `INTERNAL_SERVICE_ACTOR`
-- not just the admin-session case.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import settings_config
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


_ROUTES = [
    ("post", "/agents/orchestrator/model", {"agent_id": "orchestrator", "model": "llama3"}),
    ("post", "/agents/orchestrator/enable", None),
    ("post", "/agents/orchestrator/disable", None),
]


def _recorded_author(method: str, path: str, json, *, internal_key: bool) -> str:
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
        patch.object(settings_config, "verify_internal_api_key", return_value=internal_key),
    ):
        client = _client()
        response = getattr(client, method)(path, json=json)

    assert response.status_code == 200, response.text
    return revisions.return_value.create_revision.await_args.kwargs["created_by"]


@pytest.mark.parametrize(("method", "path", "json"), _ROUTES)
def test_recorded_author_is_not_the_literal_admin(method, path, json):
    created_by = _recorded_author(method, path, json, internal_key=False)
    assert created_by != "admin", "must record the actual actor, not the literal string"
    assert created_by == "test-user", "the stub session's user, per testkit/auth_middleware_stub.py"


@pytest.mark.parametrize(("method", "path", "json"), _ROUTES)
def test_the_internal_service_key_is_recorded_as_the_service(method, path, json):
    """#16541 AC2: the internal-key branch, not just the admin-session one."""
    created_by = _recorded_author(method, path, json, internal_key=True)
    assert created_by == settings_config.INTERNAL_SERVICE_ACTOR
