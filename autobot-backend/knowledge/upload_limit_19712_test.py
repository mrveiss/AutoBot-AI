# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19712: past the middleware's cap, the upload route refuses an oversize file before reading it."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import FormData, Headers, UploadFile

from api import knowledge as routes
from knowledge.upload_limit import MAX_FILE_SIZE_BYTES, reject_oversize_file, reject_oversize_request
from knowledge.upload_rejections import UploadRejection

_OVER = MAX_FILE_SIZE_BYTES + 1


def _request(file: UploadFile, content_length: int) -> MagicMock:
    req = MagicMock(headers=Headers({"content-length": str(content_length)}))
    req.form = AsyncMock(return_value=FormData([("file", file)]))
    return req


async def _upload(req: MagicMock):
    with patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=MagicMock())):
        return await routes.upload_file_to_knowledge(admin_check=True, req=req)


async def test_a_declared_oversize_body_is_refused_before_the_form_is_parsed() -> None:
    file = UploadFile(io.BytesIO(b"x"), size=1, filename="a.txt")
    req = _request(file, MAX_FILE_SIZE_BYTES * 2)
    with pytest.raises(UploadRejection) as refused:
        await _upload(req)
    assert refused.value.detail_code == "upload.too_large"
    req.form.assert_not_awaited()


async def test_an_oversize_file_is_refused_before_its_content_is_read() -> None:
    """Content-Length can be absent or wrong; the parsed size still stops it."""
    file = UploadFile(io.BytesIO(b"x"), size=_OVER, filename="a.txt")
    with patch.object(UploadFile, "read", AsyncMock()) as read, pytest.raises(UploadRejection):
        await _upload(_request(file, 1))
    read.assert_not_awaited()


@pytest.mark.parametrize(
    "headers", [{}, {"content-length": "not-a-number"}, {"content-length": str(MAX_FILE_SIZE_BYTES)}]
)
def test_contrast_these_headers_are_not_refused(headers: dict) -> None:
    reject_oversize_request(Headers(headers))


def test_a_full_size_file_with_its_multipart_overhead_passes() -> None:
    reject_oversize_request(Headers({"content-length": str(MAX_FILE_SIZE_BYTES + 4096)}))


@pytest.mark.parametrize("size", [None, 0, MAX_FILE_SIZE_BYTES])
def test_contrast_these_sizes_are_not_refused(size) -> None:
    reject_oversize_file(size)
