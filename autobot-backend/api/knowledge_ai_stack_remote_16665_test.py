# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The remote AI-stack reads fail closed for non-admins and are audited for admins (#16665, #19646).

``GET /system/insights`` and ``GET /ai-stack/stats`` call a service that is sent no caller identity and
whose store is not visible from this repository, so only an admin reaches it, and each read is audited.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_ai_stack
from auth_middleware import get_current_user

ALICE, ADMIN = {"user_id": "alice", "role": "user"}, {"user_id": "root", "role": "admin"}
REMOTE = {"insight": "remote-system-knowledge"}


class _StatsKB:
    async def get_stats(self):
        return {"total_facts": 4242}


def _get(user, path, audit=None):
    app = FastAPI()
    app.include_router(knowledge_ai_stack.router)
    app.state.knowledge_base = None
    app.dependency_overrides[get_current_user] = lambda: user
    client = MagicMock()
    client.get_system_knowledge = AsyncMock(return_value=REMOTE)
    with (
        patch.object(knowledge_ai_stack, "get_ai_stack_client", AsyncMock(return_value=client)),
        patch.object(knowledge_ai_stack, "get_or_create_knowledge_base", AsyncMock(return_value=_StatsKB())),
        patch("services.audit_logger.audit_log", new=audit or AsyncMock(return_value=True)),
    ):
        return TestClient(app).get(path), client


def test_insights_are_refused_to_a_non_admin_and_the_remote_is_never_called():
    response, client = _get(ALICE, "/system/insights")

    assert response.status_code == 403 and "remote-system-knowledge" not in response.text
    client.get_system_knowledge.assert_not_awaited()


def test_insights_are_served_to_an_admin_and_audited():
    audit = AsyncMock(return_value=True)
    response, _ = _get(ADMIN, "/system/insights", audit)

    assert response.status_code == 200 and "remote-system-knowledge" in response.text
    assert audit.await_args.args[0] == "kb.admin_read" and audit.await_args.kwargs["user_id"] == "root"


def test_insights_are_withheld_when_the_audit_cannot_be_written():
    response, client = _get(ADMIN, "/system/insights", AsyncMock(side_effect=RuntimeError("down")))

    assert response.status_code == 503 and "remote-system-knowledge" not in response.text
    client.get_system_knowledge.assert_not_awaited()


def test_stats_withhold_the_remote_half_from_a_non_admin():
    response, client = _get(ALICE, "/ai-stack/stats")

    assert response.status_code == 200 and "remote-system-knowledge" not in response.text
    assert "withheld" in response.text
    client.get_system_knowledge.assert_not_awaited()


def test_stats_serve_the_remote_half_to_an_admin_and_audit_it():
    audit = AsyncMock(return_value=True)
    response, _ = _get(ADMIN, "/ai-stack/stats", audit)

    assert "remote-system-knowledge" in response.text
    assert audit.await_args.args[0] == "kb.admin_read"


def test_stats_are_withheld_when_the_admin_audit_cannot_be_written():
    response, _ = _get(ADMIN, "/ai-stack/stats", AsyncMock(side_effect=RuntimeError("down")))

    assert response.status_code == 503 and "remote-system-knowledge" not in response.text


@pytest.mark.parametrize("path", ["/system/insights", "/ai-stack/stats"])
def test_an_unresolvable_caller_is_denied(path):
    response, _ = _get({"role": "user"}, path)

    assert response.status_code == 401


def test_stats_withhold_the_local_half_from_a_non_admin_as_the_admin_only_stats_route_does():
    response, _ = _get(ALICE, "/ai-stack/stats")

    assert "4242" not in response.text and response.json()["data"]["local_knowledge_base"] == {
        "withheld": "admin permission required"
    }


def test_stats_serve_the_local_half_to_an_admin():
    response, _ = _get(ADMIN, "/ai-stack/stats")

    assert response.json()["data"]["local_knowledge_base"] == {"total_facts": 4242}
