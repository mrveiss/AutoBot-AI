# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The acting identity is the session's, never a field of the request (#20521).

Each route below recorded a requester, creator, author or uploader taken from the request body or
query. A forged value is now ignored: the model no longer carries the field, and the stored actor is the
authenticated caller's. Called as functions with their collaborators replaced, so the assertion is on
the value the route hands the service -- the effect, not the status code.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import approvals as approvals_api
from llc.api import labels as labels_api
from llc.api import work_items as work_items_api
from llc.models.enums import ApprovalType, WorkItemType

_ORG = uuid.uuid4()
_ME = uuid.uuid4()
_FORGED = str(uuid.uuid4())


def _ctx(user_id: uuid.UUID | None = _ME) -> SimpleNamespace:
    return SimpleNamespace(org_id=_ORG, user_id=user_id, is_platform_admin=False)


def _user() -> dict:
    return {"id": str(_ME), "username": "me", "auth_method": "session"}


def _approval() -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=_ORG,
        approval_type="strategy",
        status="pending",
        requested_by_agent=str(_ME),  # the column is a String(255)
        context={},
        decided_by_user=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def _session() -> AsyncMock:
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [ApprovalType.STRATEGY, ApprovalType.BUDGET_OVERRIDE])
async def test_an_approval_is_requested_by_the_verified_caller_whatever_the_body_names(kind) -> None:  # noqa: ANN001
    body = approvals_api.ApprovalRequest(
        company_id=_ORG, type=kind, requested_by_agent_id=_FORGED, payload={"agent_id": "a1", "budget_limit": "5"}
    )
    svc = MagicMock(request_approval=AsyncMock(return_value=_approval()), publish_requested=AsyncMock())

    await approvals_api.request_approval(body, _session(), svc, _user(), _ctx())

    assert svc.request_approval.await_args.kwargs["requested_by"] == _ME
    assert "requested_by_agent_id" not in approvals_api.ApprovalRequest.model_fields


@pytest.mark.asyncio
async def test_a_credential_with_no_user_cannot_name_a_requester() -> None:
    body = approvals_api.ApprovalRequest(company_id=_ORG, type=ApprovalType.STRATEGY, payload={})
    svc = MagicMock(request_approval=AsyncMock(), publish_requested=AsyncMock())

    with pytest.raises(HTTPException) as refused:
        await approvals_api.request_approval(body, _session(), svc, {"auth_method": "run_jwt"}, _ctx(None))

    assert refused.value.status_code == 401
    svc.request_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_work_item_is_created_by_the_session_user_not_the_body() -> None:
    body = work_items_api.WorkItemCreate(
        company_id=str(_ORG), type=WorkItemType.TASK, title="t", created_by_agent_id=_FORGED
    )
    svc = MagicMock(create=AsyncMock(return_value=SimpleNamespace()))

    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "_item_to_dict", AsyncMock(return_value={})),
    ):
        await work_items_api.create_work_item(body, _session(), _user(), _ctx())

    kwargs = svc.create.await_args.kwargs
    assert kwargs["created_by_user_id"] == str(_ME)
    assert kwargs.get("created_by_agent_id") is None
    assert "created_by_agent_id" not in work_items_api.WorkItemCreate.model_fields


@pytest.mark.asyncio
async def test_a_comment_is_authored_by_the_session_user_not_the_body() -> None:
    body = work_items_api.CommentCreate(
        company_id=str(_ORG), body="hi", author_user_id=_FORGED, author_agent_id=_FORGED
    )
    item = SimpleNamespace(company_id=_ORG)
    svc = MagicMock(get=AsyncMock(return_value=item), add_comment=AsyncMock(return_value=SimpleNamespace()))

    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "serialize_comment", return_value={}),
    ):
        await work_items_api.add_comment(str(uuid.uuid4()), body, _session(), _user(), _ctx())

    kwargs = svc.add_comment.await_args.kwargs
    assert (kwargs["author_user_id"], kwargs["author_agent_id"]) == (str(_ME), None)
    assert not {"author_user_id", "author_agent_id"} & set(work_items_api.CommentCreate.model_fields)


@pytest.mark.asyncio
async def test_an_attachment_is_uploaded_by_the_session_user_not_the_query() -> None:
    upload = MagicMock(filename="a.txt", content_type="text/plain", read=AsyncMock(return_value=b"x"))
    existing = SimpleNamespace(company_id=_ORG)
    svc = MagicMock(get=AsyncMock(return_value=existing))
    attachments = MagicMock(upload=AsyncMock(return_value=SimpleNamespace()))

    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "_attachment_service", return_value=attachments),
        patch.object(work_items_api, "_attachment_to_dict", return_value={}),
        patch.object(work_items_api, "require_safe_upload", return_value="a.txt"),
    ):
        await work_items_api.upload_attachment("w", str(_ORG), upload, _session(), _user(), _ctx())

    kwargs = attachments.upload.await_args.kwargs
    assert (kwargs["uploaded_by_user_id"], kwargs.get("uploaded_by_agent_id")) == (str(_ME), None)
    assert not {"uploaded_by_agent_id", "uploaded_by_user_id"} & set(
        inspect.signature(work_items_api.upload_attachment).parameters
    )


@pytest.mark.asyncio
async def test_a_label_is_created_and_assigned_by_the_session_user_not_the_body() -> None:
    created = labels_api.LabelCreate(name="n", created_by=_FORGED)
    assigned = labels_api.LabelAssign(label_ids=[], assigned_by=_FORGED)
    svc = MagicMock(create=AsyncMock(return_value=SimpleNamespace()), assign_labels=AsyncMock(return_value=[]))

    with (
        patch.object(labels_api, "_service", return_value=svc),
        patch.object(labels_api, "_label_to_dict", return_value={}),
        patch.object(labels_api, "_assert_work_item_in_company", AsyncMock()),
        patch.object(labels_api, "_assert_labels_in_company", AsyncMock()),
    ):
        await labels_api.create_label(str(_ORG), created, _session(), _user(), _ctx())
        await labels_api.assign_labels(str(_ORG), "w", assigned, _session(), _user(), _ctx())

    assert svc.create.await_args.kwargs["created_by"] == str(_ME)
    assert svc.assign_labels.await_args.kwargs["assigned_by"] == str(_ME)
    assert "created_by" not in labels_api.LabelCreate.model_fields
    assert "assigned_by" not in labels_api.LabelAssign.model_fields


@pytest.mark.asyncio
async def test_a_credential_that_is_not_a_person_is_refused_like_every_other_attributed_write() -> None:
    svc = MagicMock(create=AsyncMock(return_value=SimpleNamespace()))

    with (
        patch.object(labels_api, "_service", return_value=svc),
        patch.object(labels_api, "_label_to_dict", return_value={}),
        pytest.raises(HTTPException) as refused,
    ):
        await labels_api.create_label(
            str(_ORG), labels_api.LabelCreate(name="n", created_by=_FORGED), _session(), {"username": "svc"}, _ctx(None)
        )

    assert refused.value.status_code == 401
    svc.create.assert_not_awaited()
