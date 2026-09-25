# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The upload route must build the storage path from the AUTHENTICATED tenant (#17300).

The route ran a correct IDOR guard against `ctx.org_id` and then passed the
query-string `company_id` to `AttachmentService.upload`, which is what builds the
storage path. So the tenancy check and the path could disagree, and an absolute
`company_id` replaced the storage root entirely (pathlib discards everything left
of an absolute segment) — an arbitrary file write.

`_storage_path` now refuses anything that is not a UUID, which closes the write.
This file pins the other half: that the route stops *offering* an untrusted value
in the first place. Reverting `company_id=str(ctx.org_id)` back to
`company_id=company_id` passed the entire existing suite, because
`test_work_items_idor.py` mocks `upload` wholesale and never inspects its kwargs.

Lives in its own file because `test_work_items_idor.py` sits exactly on its
file-size ceiling (#5060) and may not grow.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from llc.tests.test_work_items_idor import _make_idor_app


@pytest.fixture(autouse=True)
def _stop_patches():
    """Undo every patch `_make_idor_app` starts, for each test in THIS module.

    `test_work_items_idor.py` has an identical autouse fixture, but a fixture is
    module-scoped: importing its app builder starts its patches and does NOT
    bring its teardown along. Without this, `AttachmentService.upload` stayed an
    AsyncMock for the rest of the session and `test_attachments.py::
    test_upload_too_large` stopped raising — caught by the pre-push gate, and the
    same leak #13674/#13678 already fixed once inside the other module.
    """
    yield
    patch.stopall()


def _recording_upload():
    """A stand-in for AttachmentService.upload that remembers its kwargs."""
    row = AsyncMock()
    row.id = uuid.uuid4()
    row.work_item_id = uuid.uuid4()
    row.company_id = uuid.uuid4()
    row.filename = "x.txt"
    row.content_type = "text/plain"
    row.size_bytes = 4
    row.text_extracted = None
    row.extracted_text = None
    row.uploaded_by_agent_id = None
    row.uploaded_by_user_id = None
    row.created_at = None
    return AsyncMock(return_value=row)


def _upload(client, *, company_id: str):
    return client.post(
        f"/work-items/{uuid.uuid4()}/attachments",
        params={"company_id": company_id},
        files={"file": ("x.txt", b"data", "text/plain")},
    )


def test_the_service_receives_the_authenticated_org_not_the_query_param():
    """The regression this file exists for.

    The query string carries a *different* well-formed UUID from the caller's
    org. Both are valid UUIDs, so `_storage_path`'s parse would accept either —
    only this assertion distinguishes "used the tenant" from "used the input".
    """
    org = str(uuid.uuid4())
    attacker_supplied = str(uuid.uuid4())
    recorder = _recording_upload()

    client = _make_idor_app(caller_org_id=org, item_company_id=org)
    with patch("llc.services.attachment_service.AttachmentService.upload", new=recorder):
        resp = _upload(client, company_id=attacker_supplied)

    assert resp.status_code == 201
    recorder.assert_awaited_once()
    assert recorder.await_args.kwargs["company_id"] == org
    assert recorder.await_args.kwargs["company_id"] != attacker_supplied


def test_an_absolute_company_id_never_reaches_the_service():
    """The original exploit string. It must not survive the route, whatever the
    service would later do with it — defence in depth, not defence in one place."""
    org = str(uuid.uuid4())
    recorder = _recording_upload()

    client = _make_idor_app(caller_org_id=org, item_company_id=org)
    with patch("llc.services.attachment_service.AttachmentService.upload", new=recorder):
        _upload(client, company_id="/tmp/evil")

    recorder.assert_awaited_once()
    assert recorder.await_args.kwargs["company_id"] == org


def test_a_cross_tenant_upload_is_still_refused():
    """The contrast: the IDOR guard must keep working. Without this, a route that
    ignored company_id entirely would satisfy both tests above."""
    caller_org = str(uuid.uuid4())
    other_org = str(uuid.uuid4())
    recorder = _recording_upload()

    client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
    with patch("llc.services.attachment_service.AttachmentService.upload", new=recorder):
        resp = _upload(client, company_id=caller_org)

    assert resp.status_code == 404
    recorder.assert_not_awaited()


def test_an_unstorable_filename_is_a_400_not_a_500():
    """A filename the storage layer refuses is bad input, not a server fault (#17302).

    `_storage_path` raises `ValueError` for an id that is not a UUID and for an
    extension that cannot be placed inside the storage root. Nothing caught it:
    it reached the global `Exception` handler and became a generic 500, which
    tells the caller to retry something that can never succeed.

    Deliberately split from the unit tests that prove which inputs raise. Those
    assert "this filename is refused"; this asserts "a refusal is mapped to
    400". Merging them would let either half pass for the other's reason --
    a route that 400s on everything, or a `_storage_path` that raises on
    nothing, each looks correct through a single combined test.
    """
    org = str(uuid.uuid4())
    client = _make_idor_app(caller_org_id=org, item_company_id=org)

    with patch(
        "llc.services.attachment_service.AttachmentService.upload",
        new=AsyncMock(side_effect=ValueError("attachment path escaped the storage root")),
    ):
        response = _upload(client, company_id=org)

    assert response.status_code == 400, f"expected 400, got {response.status_code}: {response.text}"
    assert "escaped" not in response.text, "the refusal must not echo the internal path detail"
