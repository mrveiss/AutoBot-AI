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

#: Route decorators on this router, by attribute name.
_ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "websocket"}

#: A floor, not a census: a walk that finds no routes would make
#: `test_every_route_on_this_router_declares_a_gate` pass by matching nothing.
_MIN_ROUTES_SEEN = 10


def _declares_a_gate(node) -> bool:
    """Admin dependency, an authenticated-user parameter, or the socket's own check."""
    import ast

    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and any(kw.arg == "dependencies" for kw in decorator.keywords):
            return True
    args = node.args
    if any(arg.arg == "current_user" for arg in [*args.args, *args.kwonlyargs]):
        return True
    return any(
        isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "open_authenticated_ws"
        for inner in ast.walk(node)
    )


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


# ---------------------------------------------------------------------------
# #17010: no route on this router is anonymous — now, and after the next one
# ---------------------------------------------------------------------------


# The behavioural half of #17010's fourth criterion -- "unauthenticated requests
# are refused" -- CANNOT be written here, and the reason is worth recording where
# the next person will look for the test.
#
# `testkit/auth_middleware_stub.py` replaces the whole `auth_middleware` module in
# `sys.modules` for backend tests, and its `check_admin_permission` stub takes no
# request and refuses nothing. A test that mounted this router without the caller
# overrides and posted to `/codebase/index` gets **501 from the route body** -- the
# gate never ran, because in this process there is no gate. Asserting a refusal
# against that stub would be asserting on the stub, and asserting the 501 would
# read as "anonymous callers reach the route", which is a claim about the harness
# dressed as a claim about production. Tracked as #17343.
#
# What CAN be checked here is that every route declares a gate, which is what the
# router-level dependency #17010 asked for was meant to guarantee.


def test_every_route_on_this_router_declares_a_gate():
    """#17010 asked for a router-level dependency. This is the reason it is not one.

    `get_current_user(request: Request)` cannot be a router-level dependency
    here, because router dependencies apply to the WebSocket route too and
    FastAPI has no `Request` to give it -- `/{operation_id}/progress` would
    break. So the gate stays per-route, and per-route gating does not hold
    itself: a route added without one is anonymous.

    Nothing else would catch that. The repo-wide sweep cannot see this router
    at all -- `router_auth_enumerator.REGISTRY` reads only `core_routers.py`
    while this router is registered as a string tuple in `feature_routers.py`
    (#16375). This test is that missing check, scoped to this module.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(lro))
    routes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _ROUTE_DECORATORS
            for d in node.decorator_list
        )
    ]

    assert len(routes) >= _MIN_ROUTES_SEEN, (
        f"only {len(routes)} route(s) found in {lro.__name__} -- this guard has stopped "
        "reaching its subject, so its verdict means nothing"
    )

    ungated = [node.name for node in routes if not _declares_a_gate(node)]
    assert not ungated, (
        "route(s) on /api/long-running with no authentication gate (#17010):\n  "
        + "\n  ".join(ungated)
        + "\n\nEvery route needs one of: `dependencies=_ADMIN` on the decorator, "
        "`current_user: dict = Depends(get_current_user)` in the signature, or "
        "`open_authenticated_ws(...)` in the body for a WebSocket."
    )
