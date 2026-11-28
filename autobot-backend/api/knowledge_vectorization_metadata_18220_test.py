# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Vectorization reads fact metadata through the canonical parse; a bad fact fails its own job only (#18220)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import knowledge_vectorization as mod

BAD = ["[1, 2]", '"owner"', "42", "null", "{not json"]


def _kb(metadata):
    kb = MagicMock()
    kb.redis_client.hgetall = MagicMock(return_value={"content": "text", "metadata": metadata})
    return kb


@pytest.mark.asyncio
async def test_a_good_fact_still_returns_its_content_and_metadata():
    assert await mod._get_fact_content(_kb('{"a": 1}'), "f1") == ("text", {"a": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", BAD)
async def test_a_bad_fact_is_a_clean_value_error_naming_the_id(bad):
    with pytest.raises(ValueError, match="f1"):
        await mod._get_fact_content(_kb(bad), "f1")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", BAD)
async def test_the_background_job_for_a_bad_fact_fails_without_raising_and_the_next_job_runs(bad):
    statuses = []

    async def record(kb, job_id, data):
        statuses.append((job_id, data["status"]))

    good_kb = _kb('{"a": 1}')
    with (
        patch.object(mod, "_update_job_status", record),
        patch.object(mod, "_check_already_vectorized", AsyncMock(return_value=True)),
        patch.object(mod, "_handle_already_vectorized", AsyncMock()),
    ):
        await mod._vectorize_fact_background(_kb(bad), "f-bad", "job-bad")
        await mod._vectorize_fact_background(good_kb, "f-good", "job-good")
    assert ("job-bad", "failed") in statuses
    assert good_kb.redis_client.hgetall.called
