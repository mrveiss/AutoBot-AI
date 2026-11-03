# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Conversation-file uploads stop reading at the size cap and refuse a user past their quota (#20217)."""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

import conversation_file_quota as quota
from api import conversation_file_upload as upload
from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture
from api.conversation_files_real_manager_20225_test import _SESSION, _upload, real  # noqa: F401 -- fixture


class _CountingStream(io.BytesIO):
    """A body that records how many bytes the reader actually pulled."""

    pulled = 0

    def read(self, size=-1):
        data = super().read(size)
        self.pulled += len(data)
        return data


def _file(body: io.BytesIO, name="big.txt") -> UploadFile:
    return UploadFile(file=body, filename=name)


def test_an_oversize_body_stops_the_read_early(monkeypatch):
    monkeypatch.setattr(upload, "MAX_FILE_SIZE", 2 * upload._CHUNK_BYTES)
    body = _CountingStream(b"x" * (50 * upload._CHUNK_BYTES))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(upload.validate_and_read_upload_file(_file(body)))
    assert caught.value.status_code == 413 and caught.value.detail["code"] == quota.FILE_TOO_LARGE
    assert body.pulled == 3 * upload._CHUNK_BYTES  # cap + the one chunk that crossed it, not the whole body


def test_a_body_exactly_at_the_cap_is_read_whole(monkeypatch):
    monkeypatch.setattr(upload, "MAX_FILE_SIZE", 10)
    assert asyncio.run(upload.validate_and_read_upload_file(_file(io.BytesIO(b"x" * 10)))) == b"x" * 10


def test_the_remaining_quota_ends_the_read_with_its_own_code(real, monkeypatch):  # noqa: F811
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 5)
    body = _CountingStream(b"x" * (10 * upload._CHUNK_BYTES))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(upload.validate_and_read_upload_file(_file(body), real.real, "alice"))
    assert caught.value.status_code == 413 and caught.value.detail["code"] == quota.QUOTA_EXCEEDED
    assert body.pulled == upload._CHUNK_BYTES


def test_a_user_past_their_quota_is_refused_by_the_route_and_nothing_is_stored(real, monkeypatch):  # noqa: F811
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 20)
    assert _upload(real, body=b"x" * 15).status_code == 200
    response = _upload(real, name="two.txt", body=b"y" * 10)
    assert response.status_code == 413 and response.json()["detail"]["code"] == quota.QUOTA_EXCEEDED
    assert asyncio.run(real.real.remaining_upload_quota("alice")) == 5


def test_the_quota_is_per_user_not_shared(real, monkeypatch):  # noqa: F811
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 20)
    assert _upload(real, body=b"x" * 20).status_code == 200
    assert asyncio.run(real.real.remaining_upload_quota("alice")) == 0
    assert asyncio.run(real.real.remaining_upload_quota("bob")) == 20


def test_the_quota_limit_is_the_registered_env_default():
    from autobot_shared.env_registry import REGISTRY

    assert REGISTRY["AUTOBOT_CONVERSATION_FILE_USER_QUOTA_BYTES"].default == quota.USER_QUOTA_BYTES == 1 << 30
