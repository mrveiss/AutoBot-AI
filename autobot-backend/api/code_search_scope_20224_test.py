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


def _refusing_auth():
    from fastapi import HTTPException

    return AsyncMock(side_effect=HTTPException(status_code=404, detail="Source not found"))


@pytest.mark.asyncio
async def test_refactor_suggestions_answer_404_for_a_foreign_or_unknown_source() -> None:
    from fastapi import HTTPException

    request = CodeAnalyticsRequest(root_path="/p", source_id="src-foreign")
    with patch.object(mod, "authorize_source_access", _refusing_auth()):
        with pytest.raises(HTTPException) as refused:
            await mod.get_refactor_suggestions(request, {"u": 1})
    assert refused.value.status_code == 404


@pytest.mark.asyncio
async def test_status_and_stats_refuse_a_foreign_source_before_reading_the_index() -> None:
    from fastapi import HTTPException

    agent = AsyncMock()
    with (
        patch.object(mod, "authorize_source_access", _refusing_auth()),
        patch.object(mod, "_get_code_search_agent", return_value=agent),
    ):
        for route in (mod.get_search_status, mod.get_codebase_statistics):
            with pytest.raises(HTTPException) as refused:
                await route("src-foreign", {"u": 1})
            assert refused.value.status_code == 404
    agent.get_index_status.assert_not_called()


@pytest.mark.asyncio
async def test_status_reports_only_the_requested_source() -> None:
    agent = AsyncMock()
    agent.get_index_status.return_value = {"npu_available": False}
    with (
        patch.object(mod, "authorize_source_access", AsyncMock()),
        patch.object(mod, "_get_code_search_agent", return_value=agent),
    ):
        await mod.get_search_status("src-a", {"u": 1})
    agent.get_index_status.assert_awaited_once_with("src-a")


@pytest.mark.asyncio
async def test_stats_answer_200_for_an_indexed_source_and_404_for_an_empty_one() -> None:
    from fastapi import HTTPException

    agent = AsyncMock()
    agent.index_prefix = "autobot:code:index:"
    agent.get_index_status.return_value = {"total_files_indexed": 3, "languages": {"python": 3}, "npu_available": False}
    redis = AsyncMock()
    redis.keys = lambda pattern: ["k1", "k2"]
    with (
        patch.object(mod, "authorize_source_access", AsyncMock()),
        patch.object(mod, "_get_code_search_agent", return_value=agent),
        patch.object(mod, "get_redis_client", return_value=redis),
    ):
        response = await mod.get_codebase_statistics("src-a", {"u": 1})
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["index_statistics"]["total_files_indexed"] == 3
        assert body["redis_keys"] == 2
        agent.get_index_status.return_value = {"total_files_indexed": 0, "languages": {}}
        with pytest.raises(HTTPException) as empty:
            await mod.get_codebase_statistics("src-a", {"u": 1})
    assert empty.value.status_code == 404


@pytest.mark.asyncio
async def test_dev_speedup_status_resolves_the_search_agent_without_import_error() -> None:
    from api import development_speedup as dev

    agent = AsyncMock()
    agent.get_index_status.return_value = {"npu_available": False}
    with (
        patch.object(dev, "authorize_source_access", AsyncMock()),
        patch("agents.npu_code_search_agent.get_npu_code_search", return_value=agent),
        patch.object(
            dev,
            "get_dev_speedup_agent",
            return_value=AsyncMock(duplicate_threshold=1, min_duplicate_lines=1, complexity_threshold=1),
        ),
    ):
        response = await dev.get_development_speedup_status("src-a", {"u": 1})
    assert response.status_code == 200
    agent.get_index_status.assert_awaited_once_with("src-a")
