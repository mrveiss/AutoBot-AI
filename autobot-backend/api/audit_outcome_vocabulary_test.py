# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The audit query API carries the canonical event outcome verbatim (#20173).

``AuditEntry.from_event`` copies the event ``outcome``, an open string (the taxonomy
has ``verified`` / ``backup-code`` for ``auth.mfa``). A narrower response ``Literal``
turned one such row into a 500 for every query that returned it.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.audit import check_admin_permission, router
from api.schemas_audit import AuditQueryResponse
from services.audit_logger import AuditEntry

OFF_VOCABULARY = ["verified", "backup-code"]


def _entry(outcome: str) -> AuditEntry:
    return AuditEntry.from_event(
        {
            "id": "evt-1",
            "occurred_at": 1_700_000_000.0,
            "action": "auth.mfa",
            "actor_id": "alice",
            "session_id": "s1",
            "outcome": outcome,
            "metadata": {},
        }
    )


def _client(entries: list) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = lambda: True
    audit_logger = MagicMock()
    audit_logger.query = AsyncMock(return_value=entries)
    patcher = patch("api.audit.get_audit_logger", AsyncMock(return_value=audit_logger))
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


@pytest.mark.parametrize("outcome", OFF_VOCABULARY)
def test_response_model_serialises_the_real_outcome(outcome):
    body = AuditQueryResponse(
        success=True,
        total_returned=1,
        has_more=False,
        entries=[_entry(outcome).to_response_dict()],
        query={},
    )
    assert body.model_dump()["entries"][0]["result"] == outcome


@pytest.mark.parametrize("outcome", OFF_VOCABULARY)
@pytest.mark.parametrize(
    "path",
    ["/api/audit/logs", "/api/audit/session/s1", "/api/audit/user/alice", "/api/audit/failures"],
)
def test_every_query_endpoint_returns_200_with_the_real_outcome(path, outcome):
    client = _client([_entry(outcome)])
    try:
        response = client.get(path)
    finally:
        client._patcher.stop()  # type: ignore[attr-defined]
    assert response.status_code == 200, response.text
    assert response.json()["entries"][0]["result"] == outcome
