# Copyright 2026 asketeddy
# SPDX-License-Identifier: Apache-2.0
"""Approval create responses using real async ORM and migrated PostgreSQL.

No fake session or SQLite backend.
"""

import importlib
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from models.approval import Approval, TaskApprovalLink
from services.approval_gate_service import ApprovalGateService
from testkit.module_stubs import StubSet
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]


@pytest.fixture
def approval_route():
    """Bypass only an unused knowledge package initializer; keep its real stamp leaf.

    The existing StubSet owns new child-module keys and restores parent bindings
    in finally. No package stub remains between collection of unrelated tests.
    An already imported real knowledge package is never replaced.
    """
    backend = Path(__file__).resolve().parents[2]
    stubs = StubSet()
    try:
        knowledge = sys.modules.get("services.knowledge")
        if not isinstance(getattr(knowledge, "__file__", None), str):
            stubs.install_package("services.knowledge", backend / "services" / "knowledge")
            stubs.import_real("services.knowledge.collection_space_stamp_action")
        route = importlib.import_module("api.approval_gates")
        assert route.ApprovalGateService is ApprovalGateService
        assert route.get_db_session is get_db_session
        assert route.get_current_user is get_current_user
        assert route._to_response.__module__ == "api.approval_gates"
        assert Path(route._to_response.__code__.co_filename).resolve() == backend / "api" / "approval_gates.py"
        assert ApprovalGateService.create_approval.__module__ == "services.approval_gate_service"
        assert Path(ApprovalGateService.create_approval.__code__.co_filename).resolve() == (
            backend / "services" / "approval_gate_service.py"
        )
        assert Path(route.register_stamp_action.__code__.co_filename).resolve() == (
            backend / "services" / "knowledge" / "collection_space_stamp_action.py"
        )
        yield route
    finally:
        stubs.restore()


@pytest.fixture
async def approval_sessions(fresh_db_url, monkeypatch):
    """Reuse the disposable-Postgres migration gate, without external notifications."""
    assert fresh_db_url.startswith("postgresql+asyncpg://")
    assert sqlalchemy.inspect(Approval).class_ is Approval, "real mapped Approval required"
    assert sqlalchemy.inspect(TaskApprovalLink).class_ is TaskApprovalLink, "real mapped task links required"
    migrated = run_alembic(["upgrade", "head"], fresh_db_url)
    assert migrated.returncode == 0, "disposable database migration failed"
    monkeypatch.setattr(ApprovalGateService, "_notify", AsyncMock())
    engine = create_async_engine(fresh_db_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        await engine.dispose()


async def _post_create(sessions, body, approval_route):
    """Use the real router/service/session; only the authenticated test identity is supplied."""
    app = FastAPI()
    app.include_router(approval_route.router)

    async def db_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db_session] = db_session
    app.dependency_overrides[get_current_user] = lambda: {
        "username": "synthetic-create-regression",
        "role": "user",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://approval-regression"
    ) as client:
        return await client.post("/approval-gates", json=body)


@pytest.fixture
def response_failures(monkeypatch, approval_route):
    """Record the real serializer's exception class without replacing its behavior."""
    failures = []
    original = approval_route._to_response

    def observed(row):
        try:
            return original(row)
        except Exception as error:
            failures.append(type(error).__module__ + "." + type(error).__name__)
            raise

    monkeypatch.setattr(approval_route, "_to_response", observed)
    return failures


async def _read_approval_snapshot(reader, title):
    """Read committed ordinary approval fields for #18803."""
    return (
        (
            await reader.execute(
                select(Approval.id, Approval.company_id, Approval.title, Approval.context, Approval.status).where(
                    Approval.title == title
                )
            )
        )
        .mappings()
        .all()
    )


async def _read_task_link_rows(reader, approval_id):
    """Read independent persisted task-link fields for #18803."""
    return (
        (
            await reader.execute(
                select(TaskApprovalLink.id, TaskApprovalLink.approval_id, TaskApprovalLink.task_id).where(
                    TaskApprovalLink.approval_id == approval_id
                )
            )
        )
        .mappings()
        .all()
    )


async def _read_task_links(reader, approval_id):
    """Read the remaining company approval links for #18803."""
    return (
        (await reader.execute(select(TaskApprovalLink).where(TaskApprovalLink.approval_id == approval_id)))
        .scalars()
        .all()
    )


async def test_http_create_returns_201_and_commits_empty_relationships(
    approval_sessions, response_failures, approval_route
):
    title = "synthetic ordinary gate"
    response = await _post_create(
        approval_sessions,
        {"title": title, "approval_type": "workflow_gate", "context": {"synthetic": True}},
        approval_route,
    )
    async with approval_sessions() as reader:
        stored = await _read_approval_snapshot(reader, title)
    assert len(stored) == 1, f"HTTP={response.status_code} committed_rows={len(stored)}"
    assert stored[0]["company_id"] is None
    assert stored[0]["context"] == {"synthetic": True}
    assert stored[0]["status"] == "pending"
    assert response.status_code == 201, (
        f"HTTP={response.status_code} committed_rows={len(stored)} "
        f"serialization_errors={response_failures!r} body={response.text[:512]!r}"
    )
    body = response.json()
    assert uuid.UUID(body["id"]) == stored[0]["id"]
    assert body["status"] == "pending"
    assert body["comments"] == []
    assert body["task_links"] == []
    assert response_failures == []


async def test_http_create_returns_real_committed_task_links(approval_sessions, response_failures, approval_route):
    title = "synthetic linked gate"
    task_ids = ["synthetic:relationship-regression:one", "synthetic:relationship-regression:two"]
    response = await _post_create(
        approval_sessions,
        {"title": title, "approval_type": "workflow_gate", "task_ids": task_ids},
        approval_route,
    )
    async with approval_sessions() as reader:
        stored_ids = (await reader.execute(select(Approval.id).where(Approval.title == title))).scalars().all()
        assert len(stored_ids) == 1, f"HTTP={response.status_code} committed_rows={len(stored_ids)}"
        links = await _read_task_link_rows(reader, stored_ids[0])
    assert len(links) == 2
    assert {link["task_id"] for link in links} == set(task_ids)
    assert response.status_code == 201, (
        f"HTTP={response.status_code} committed_rows={len(stored_ids)} committed_links={len(links)} "
        f"serialization_errors={response_failures!r} body={response.text[:512]!r}"
    )
    body = response.json()
    assert uuid.UUID(body["id"]) == stored_ids[0]
    assert body["comments"] == []
    assert len(body["task_links"]) == 2
    assert all(link["approval_id"] == body["id"] for link in body["task_links"])
    assert all(link["task_type"] == "github_issue" for link in body["task_links"])
    assert {(str(link["id"]), link["task_id"]) for link in links} == {
        (link["id"], link["task_id"]) for link in body["task_links"]
    }
    assert response_failures == []


async def test_company_create_is_loaded_detached_and_still_excluded_from_general_api(approval_sessions, approval_route):
    company_id = uuid.uuid4()
    task_id = "synthetic:relationship-regression:company"
    async with approval_sessions() as creator:
        row = await ApprovalGateService(creator).create_approval(
            title="synthetic company gate", approval_type="workflow_gate", company_id=company_id, task_ids=[task_id]
        )
        approval_id = row.id
        assert {"comments", "task_links"}.isdisjoint(sqlalchemy.inspect(row).unloaded)
        creator.expunge(row)
        assert sqlalchemy.inspect(row).session is None
        response = approval_route._to_response(row)
        assert response.comments == []
        assert len(response.task_links) == 1
        assert response.task_links[0].task_id == task_id

    async with approval_sessions() as reader:
        stored = await reader.get(Approval, approval_id)
        assert stored is not None and stored.company_id == company_id
        service = ApprovalGateService(reader)
        assert await service.get(approval_id) is None
        with pytest.raises(ValueError, match="not found"):
            await service.unlink_task(approval_id, task_id)

    async with approval_sessions() as reader:
        stored = await reader.get(Approval, approval_id)
        assert stored is not None and stored.company_id == company_id
        links = await _read_task_links(reader, approval_id)
        assert len(links) == 1 and links[0].task_id == task_id
