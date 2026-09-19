# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Long-running operations: honest start routes, a create that works, creator-scoped access (#17017).

The routes run through FastAPI against the real ``OperationIntegrationManager`` and
``LongRunningOperationManager`` (in memory, no Redis). Only the caller is stood in
for: ``get_current_user`` and ``check_admin_permission`` are overridden per test.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import long_running_operations as lro
from auth_middleware import check_admin_permission, get_current_user
from utils.long_running_operations_framework import (
    LongRunningOperation,
    LongRunningOperationManager,
    OperationCheckpoint,
    OperationType,
)
from utils.operation_timeout_integration import OperationIntegrationManager

ALICE = {"username": "alice", "role": "user"}
BOB = {"username": "bob", "role": "user"}
ADMIN = {"username": "root", "role": "admin"}


@pytest.fixture
def integration():
    manager = OperationIntegrationManager()
    manager.operation_manager = LongRunningOperationManager(None)
    return manager


def _client(integration, caller) -> TestClient:
    def _admin_check():
        if caller.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin required")
        return True

    app = FastAPI()
    app.include_router(lro.router)
    app.dependency_overrides[lro.get_operation_manager] = lambda: integration
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[check_admin_permission] = _admin_check
    return TestClient(app)


def _checkpoint(operation_id: str) -> OperationCheckpoint:
    return OperationCheckpoint(
        checkpoint_id=f"c-{operation_id}",
        operation_id=operation_id,
        checkpoint_time=datetime.now(),
        progress_percent=40.0,
        state_data={},
    )


def _resumable(integration, operation_id: str) -> None:
    """Stand in for checkpoint storage only; the real ``resume_operation`` runs."""
    checkpoint = _checkpoint(operation_id)
    integration.list_operation_checkpoints = AsyncMock(return_value=[checkpoint])
    integration.operation_manager.checkpoint_manager.load_checkpoint = AsyncMock(return_value=checkpoint)


def _operation(integration, operation_id: str, creator: str | None) -> None:
    metadata = {"created_by": creator} if creator else {}
    integration.operation_manager.operations[operation_id] = LongRunningOperation(
        operation_id=operation_id,
        operation_type=OperationType.COMPREHENSIVE_TEST_SUITE,
        name=operation_id,
        description="fixture",
        metadata=metadata,
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/codebase/index", {"codebase_path": "."}),
        ("/knowledge-base/populate", {"source_paths": ["."]}),
        ("/security/scan", {"scan_paths": ["."]}),
    ],
    ids=["indexing", "kb population", "security scan"],
)
def test_a_start_route_with_no_working_operation_answers_501_and_queues_nothing(integration, path, body):
    response = _client(integration, ADMIN).post(path, json=body)

    assert response.status_code == 501, response.text
    assert "#17023" in response.json()["detail"]
    assert integration.operation_manager.operations == {}


def test_the_test_suite_route_creates_an_operation_that_records_its_creator(integration, tmp_path):
    """#17017: this route raised TypeError inside the create call and answered 500."""
    with patch.object(lro, "validate_path", return_value=Path(tmp_path)):
        response = _client(integration, ADMIN).post("/testing/comprehensive", json={"test_path": str(tmp_path)})

    assert response.status_code == 200, response.text
    operation = integration.operation_manager.operations[response.json()["operation_id"]]
    assert operation.metadata["created_by"] == "root"


def test_a_non_admin_cannot_start_work(integration):
    assert _client(integration, ALICE).post("/testing/comprehensive", json={"test_path": "."}).status_code == 403


def test_a_non_admin_lists_only_their_own_and_an_admin_lists_all(integration):
    _operation(integration, "a-1", "alice")
    _operation(integration, "b-1", "bob")
    _operation(integration, "legacy", None)  # created before #17017: an admin's alone

    def ids(caller):
        with patch.object(lro.logger, "error") as logged:
            response = _client(integration, caller).get("/")
        assert response.status_code == 200, (response.text, logged.call_args_list)
        body = response.json()
        return sorted(op["operation_id"] for op in body["operations"]), body["total_count"]

    assert ids(ALICE) == (["a-1"], 1)
    assert ids(ADMIN) == (["a-1", "b-1", "legacy"], 3)


def test_the_creator_reads_and_cancels_their_own(integration):
    _operation(integration, "a-1", "alice")
    client = _client(integration, ALICE)

    assert client.get("/a-1").status_code == 200
    assert client.post("/a-1/cancel").status_code == 200


@pytest.mark.parametrize("caller", [BOB, ALICE], ids=["bob", "alice"])
def test_another_users_or_an_unowned_operation_is_refused_without_disclosing_it(integration, caller):
    _operation(integration, "b-1", "bob" if caller is ALICE else "alice")  # always the other user's
    _operation(integration, "legacy", None)
    client = _client(integration, caller)

    for operation_id in ("b-1", "legacy"):
        assert client.get(f"/{operation_id}").status_code == 404
        assert client.post(f"/{operation_id}/cancel").status_code == 404
        assert client.post(f"/{operation_id}/resume").status_code == 404
    assert integration.operation_manager.operations["b-1"].status.value != "cancelled"


def test_an_admin_reads_and_cancels_anyones(integration):
    _operation(integration, "a-1", "alice")
    client = _client(integration, ADMIN)

    assert client.get("/a-1").status_code == 200
    assert client.post("/a-1/cancel").status_code == 200


#: The ``Operation`` interface in autobot-frontend/src/types/operations.ts.
PANEL_FIELDS = {
    "operation_id", "name", "description", "operation_type", "status", "priority", "progress", "current_step",
    "estimated_items", "processed_items", "created_at", "started_at", "completed_at", "error_message",
    "context", "checkpoints_count", "can_resume",
}  # fmt: skip


def test_an_operation_reaches_the_panel_in_the_shape_it_reads(integration):
    """Every status and list request answered 500: the old conversion had drifted from both ends (#17017)."""
    _operation(integration, "a-1", "alice")

    body = _client(integration, ALICE).get("/a-1").json()

    assert set(body) == PANEL_FIELDS
    assert (body["status"], body["priority"]) == ("pending", "normal")  # queued reads as pending
    assert "created_by" not in body["context"]


def test_a_resumed_operation_reaches_the_panel_without_its_raw_checkpoint(integration):
    """#17027 review: resume stores an ``OperationCheckpoint`` dataclass in metadata; it must not reach ``context``."""
    _operation(integration, "r-1", "alice")
    integration.operation_manager.operations["r-1"].metadata["resume_checkpoint"] = _checkpoint("a-1")

    response = _client(integration, ALICE).get("/r-1")

    assert response.status_code == 200, response.text
    assert "resume_checkpoint" not in response.json()["context"]
    json.dumps(response.json())


def test_a_migrated_operation_records_its_creator(integration):
    """#17027 review: the migrator had the same unaccepted ``estimated_items`` argument, and no creator."""
    with patch("utils.operation_timeout_integration.operation_integration_manager", integration):
        response = _client(integration, ADMIN).post(
            "/migrate/existing", params={"operation_name": "legacy-job", "timeout_seconds": 60}
        )

    assert response.status_code == 200, response.text
    operation = integration.operation_manager.operations[response.json()["operation_id"]]
    assert operation.metadata["created_by"] == "root"


@pytest.mark.parametrize(("caller", "owner"), [(ALICE, "alice"), (ADMIN, "bob")], ids=["its creator", "an admin"])
def test_a_resumed_operation_keeps_its_original_creator(integration, caller, owner):
    """#17027 review: the creator may resume their own; an admin may resume anyone's, and the
    resumed operation stays the original creator's, not the admin's."""
    _operation(integration, "o-1", owner)
    _resumable(integration, "o-1")

    response = _client(integration, caller).post("/o-1/resume")

    assert response.status_code == 200, response.text
    resumed = integration.operation_manager.operations[response.json()["new_operation_id"]]
    assert resumed.metadata["created_by"] == owner
