# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLC LabelService and label API routes (GH#8254)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.models.label import LLCLabel, LLCWorkItemLabel
from llc.services.label_service import (  # noqa: E402
    LabelNotFound,
    LLCLabelService,
    WorkItemNotFound,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_label(
    name: str = "bug",
    color: str = "#ef4444",
    company_id: uuid.UUID | None = None,
) -> MagicMock:
    label = MagicMock(spec=LLCLabel)
    label.id = uuid.uuid4()
    label.company_id = company_id or uuid.uuid4()
    label.name = name
    label.color = color
    label.description = None
    label.created_at = None
    label.created_by = None
    label.work_item_labels = []
    return label


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    return LLCLabelService()


@pytest.mark.asyncio
async def test_create_label_with_explicit_color(service):
    session = AsyncMock()
    company_id = str(uuid.uuid4())

    # count query returns 0
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=count_result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    label = MagicMock(spec=LLCLabel)
    label.id = uuid.uuid4()
    label.company_id = uuid.UUID(company_id)
    label.name = "feature"
    label.color = "#3b82f6"
    label.description = None
    label.created_at = None
    label.created_by = None
    session.refresh = AsyncMock()

    with patch("llc.services.label_service.LLCLabel", return_value=label):
        result = await service.create(
            session,
            company_id=company_id,
            name="feature",
            color="#3b82f6",
        )

    assert session.flush.called


@pytest.mark.asyncio
async def test_update_raises_not_found(service):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(LabelNotFound):
        await service.update(session, label_id=str(uuid.uuid4()), name="new-name")


@pytest.mark.asyncio
async def test_delete_raises_not_found(service):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(LabelNotFound):
        await service.delete(session, label_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_assign_labels_work_item_not_found(service):
    session = AsyncMock()
    wi_result = MagicMock()
    wi_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=wi_result)

    with pytest.raises(WorkItemNotFound):
        await service.assign_labels(
            session,
            work_item_id=str(uuid.uuid4()),
            label_ids=[str(uuid.uuid4())],
        )


@pytest.mark.asyncio
async def test_assign_labels_idempotent(service):
    """Re-assigning an existing label must not duplicate the row."""
    session = AsyncMock()
    work_item_id = uuid.uuid4()
    label_id = uuid.uuid4()

    wi = MagicMock()
    wi.company_id = uuid.uuid4()
    wi_result = MagicMock()
    wi_result.scalar_one_or_none.return_value = wi
    session.execute = AsyncMock(return_value=wi_result)

    # Simulate existing join row
    existing = MagicMock(spec=LLCWorkItemLabel)
    session.get = AsyncMock(return_value=existing)
    session.flush = AsyncMock()

    added = await service.assign_labels(
        session,
        work_item_id=str(work_item_id),
        label_ids=[str(label_id)],
    )
    assert added == []  # nothing new added


@pytest.mark.asyncio
async def test_remove_label_work_item_not_found(service):
    session = AsyncMock()
    wi_result = MagicMock()
    wi_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=wi_result)

    with pytest.raises(WorkItemNotFound):
        await service.remove_label(
            session,
            work_item_id=str(uuid.uuid4()),
            label_id=str(uuid.uuid4()),
        )


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    from llc.api.labels import get_session, router

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    company_id = str(uuid.uuid4())
    label_id = str(uuid.uuid4())

    label = _make_label()
    label.id = uuid.UUID(label_id)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_session

    return TestClient(app), company_id, label_id, label, mock_session


def test_create_label_route(app_client):
    client, company_id, label_id, label, session = app_client

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.create = AsyncMock(return_value=label)
        mock_svc.return_value = svc

        resp = client.post(
            f"/api/llc/companies/{company_id}/labels",
            json={"name": "bug", "color": "#ef4444"},
        )

    assert resp.status_code == 201


def test_list_labels_route(app_client):
    client, company_id, *_ = app_client

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.list_labels = AsyncMock(return_value=[])
        mock_svc.return_value = svc

        resp = client.get(f"/api/llc/companies/{company_id}/labels")

    assert resp.status_code == 200
    assert resp.json() == []


def test_update_label_not_found(app_client):
    client, company_id, label_id, *_ = app_client

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.update = AsyncMock(side_effect=LabelNotFound(label_id))
        mock_svc.return_value = svc

        resp = client.patch(
            f"/api/llc/companies/{company_id}/labels/{label_id}",
            json={"name": "renamed"},
        )

    assert resp.status_code == 404


def test_delete_label_not_found(app_client):
    client, company_id, label_id, *_ = app_client

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.delete = AsyncMock(side_effect=LabelNotFound(label_id))
        mock_svc.return_value = svc

        resp = client.delete(f"/api/llc/companies/{company_id}/labels/{label_id}")

    assert resp.status_code == 404


def test_assign_labels_work_item_not_found(app_client):
    client, company_id, label_id, *_ = app_client
    work_item_id = str(uuid.uuid4())

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.assign_labels = AsyncMock(side_effect=WorkItemNotFound(work_item_id))
        mock_svc.return_value = svc

        resp = client.post(
            f"/api/llc/companies/{company_id}/labels/work-items/{work_item_id}/labels",
            json={"label_ids": [label_id]},
        )

    assert resp.status_code == 404


def test_remove_label_work_item_not_found(app_client):
    client, company_id, label_id, *_ = app_client
    work_item_id = str(uuid.uuid4())

    with patch("llc.api.labels._service") as mock_svc:
        svc = AsyncMock()
        svc.remove_label = AsyncMock(side_effect=WorkItemNotFound(work_item_id))
        mock_svc.return_value = svc

        resp = client.delete(f"/api/llc/companies/{company_id}/labels/work-items/{work_item_id}/labels/{label_id}")

    assert resp.status_code == 404
