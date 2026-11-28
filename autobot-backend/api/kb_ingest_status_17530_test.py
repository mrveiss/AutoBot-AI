# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``_store_fact_in_kb`` reports what ``add_document`` actually did (#17530)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api import knowledge as mod
from knowledge.upload_rejections import UploadRejection, UploadRejectionCode


def _kb(result):
    return MagicMock(add_document=AsyncMock(return_value=result))


@pytest.mark.asyncio
async def test_partial_is_returned_with_its_chunk_count() -> None:
    result = {"status": "partial", "fact_id": "d1", "chunks_stored": 3, "chunks_total": 9}
    assert await mod._store_fact_in_kb(_kb(result), "t", {}) == "d1"
    note = mod.partial_note(result)
    assert (note["status"], note["chunks_stored"], note["chunks_total"]) == ("partial", 3, 9)
    assert "3 of 9" in note["message"]
    assert mod.partial_note({"status": "success"}) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,code,http",
    [
        ({"status": "error", "message": "boom"}, UploadRejectionCode.INGEST_FAILED, 500),
        ({"status": "timeout"}, UploadRejectionCode.INGEST_TIMEOUT, 504),
        ({"status": "success", "fact_id": None}, UploadRejectionCode.INGEST_FAILED, 500),
    ],
)
async def test_error_and_timeout_are_rejected_not_reported_stored(result, code, http) -> None:
    with pytest.raises(UploadRejection) as exc:
        await mod._store_fact_in_kb(_kb(result), "t", {})
    assert (exc.value.detail_code, exc.value.status_code) == (code.value, http)
