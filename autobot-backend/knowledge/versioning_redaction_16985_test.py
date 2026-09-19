# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reverting a fact to a previous version redacts that version's content
before writing it back into the live Redis projection (#13708 sweep).

A version recorded before this fix -- or by any path that predates
sanitize_fact_content -- can carry a raw credential in its own history.
_apply_version_to_fact is the one place a revert pushes that content back
into the fact actually served, so it is where this has to be caught.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.versioning import VersioningMixin

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


class _VersioningFakeKB(VersioningMixin):
    def __init__(self):
        self.redis_client = MagicMock()
        self.redis_client.exists.return_value = True
        self.redis_client.hget.return_value = None  # _get_next_version_number: no prior version


@pytest.mark.asyncio
async def test_apply_version_to_fact_redacts_before_the_hset():
    kb = _VersioningFakeKB()

    ok = await kb._apply_version_to_fact("fact-1", {"content": f"your API key is {_SECRET}", "metadata": {}})

    assert ok is True
    mapping = kb.redis_client.hset.call_args.kwargs["mapping"]
    assert _SECRET not in mapping["content"]
    assert "your API key is" in mapping["content"]


@pytest.mark.asyncio
async def test_apply_version_to_fact_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    kb = _VersioningFakeKB()

    await kb._apply_version_to_fact("fact-2", {"content": "Redis listens on port 6379.", "metadata": {}})

    mapping = kb.redis_client.hset.call_args.kwargs["mapping"]
    assert mapping["content"] == "Redis listens on port 6379."


@pytest.mark.asyncio
async def test_revert_to_version_redacts_the_new_version_it_records_too():
    """Review finding: _apply_version_to_fact redacted the live Redis hset, but
    revert_to_version reads target_version["content"] a SECOND time right after,
    to record the revert itself via create_version -- a local-only redaction in
    _apply_version_to_fact left that second write pushing the raw secret straight
    back into version history, seconds after the live projection was cleaned.
    Drives the real revert_to_version end-to-end (only get_version is mocked, to
    hand it the version being reverted to), not _apply_version_to_fact alone."""
    kb = _VersioningFakeKB()
    raw = f"your API key is {_SECRET}"
    target_version = {"content": raw, "metadata": {}, "version": 1}

    lpush_calls = []
    kb.redis_client.lpush = lambda key, value: lpush_calls.append(value)

    with patch.object(
        type(kb), "get_version", new=AsyncMock(return_value={"status": "success", "version": target_version})
    ):
        result = await kb.revert_to_version("fact-1", 1)

    assert result["status"] == "success"

    # create_version's own meta_operation also calls hset (current_version/total_versions,
    # no "content" key) -- find the fact-projection hset specifically, not just the last call.
    content_hset_calls = [c for c in kb.redis_client.hset.call_args_list if "content" in c.kwargs.get("mapping", {})]
    assert len(content_hset_calls) == 1
    hset_mapping = content_hset_calls[0].kwargs["mapping"]
    assert _SECRET not in hset_mapping["content"], "live projection carries the raw secret"

    assert len(lpush_calls) == 1
    new_version_payload = json.loads(lpush_calls[0])
    assert (
        _SECRET not in new_version_payload["content"]
    ), "the new version entry created by the revert carries the raw secret"
