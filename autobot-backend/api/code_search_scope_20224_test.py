# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20224, #20402: the code-search analytics are limited to ONE source's index and say which."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api import code_search as mod
from api.code_search import _build_declarations_summary
from api.code_search_duplicates import build_duplicates_response
from api.schemas_code import CodeAnalyticsRequest


def test_the_declarations_summary_names_its_source_and_no_longer_claims_the_whole_index() -> None:
    summary = _build_declarations_summary({}, "/project", "src-a")["summary"]
    assert summary["analysis_root"] == "/project"
    assert summary["source_id"] == "src-a"
    assert "results_scope" not in summary


def test_the_duplicates_summary_names_its_source_and_no_longer_claims_the_whole_index() -> None:
    summary = build_duplicates_response(0, [], "/project", "src-a")["summary"]
    assert summary["analysis_root"] == "/project"
    assert summary["source_id"] == "src-a"
    assert "results_scope" not in summary


def _patched(search):
    allowed = AsyncMock()
    indexed = AsyncMock(return_value={"status": "success"})
    return (
        (
            patch.object(mod, "authorize_source_access", allowed),
            patch.object(mod, "index_project", indexed),
            patch.object(mod, "search_codebase", search),
        ),
        indexed,
        allowed,
    )


@pytest.mark.asyncio
async def test_declarations_index_and_search_only_the_requests_source() -> None:
    search = AsyncMock(return_value=[])
    patches, indexed, allowed = _patched(search)
    with patches[0], patches[1], patches[2]:
        response = await mod.analyze_declarations(CodeAnalyticsRequest(root_path="/p", source_id="src-a"), {"u": 1})

    allowed.assert_awaited_once_with("src-a", {"u": 1})
    assert indexed.await_args.kwargs["source_id"] == "src-a"
    assert search.await_count > 0
    assert {call.kwargs["source_id"] for call in search.await_args_list} == {"src-a"}
    assert json.loads(response.body)["summary"]["source_id"] == "src-a"


@pytest.mark.asyncio
async def test_duplicates_index_and_search_only_the_requests_source() -> None:
    search = AsyncMock(return_value=[])
    patches, indexed, allowed = _patched(search)
    with patches[0], patches[1], patches[2]:
        response = await mod.find_code_duplicates(CodeAnalyticsRequest(root_path="/p", source_id="src-b"), {"u": 1})

    allowed.assert_awaited_once_with("src-b", {"u": 1})
    assert indexed.await_args.kwargs["source_id"] == "src-b"
    assert search.await_count > 0
    assert {call.kwargs["source_id"] for call in search.await_args_list} == {"src-b"}
    assert json.loads(response.body)["summary"]["source_id"] == "src-b"


def test_a_request_without_a_source_is_refused() -> None:
    with pytest.raises(Exception):
        CodeAnalyticsRequest(root_path="/p")
    with pytest.raises(Exception):
        CodeAnalyticsRequest(root_path="/p", source_id="*")
