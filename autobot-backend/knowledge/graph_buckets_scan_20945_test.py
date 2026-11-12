# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bucket scans cap what the caller may read, and say so when a read failed or the budget ran out (#20945)."""

from unittest.mock import AsyncMock, patch

import pytest

from api.knowledge_graph_sections import bucket_sections_for_graph
from api.schemas_knowledge_graph import GraphRequest, GraphSection
from knowledge.graph_buckets import build_bucket_sections
from tests.fixtures.graph_buckets_fakes_20945 import ALICE, client_with, manager, viewer

_HIDDEN = {"user_id": "bob"}
_MINE = {"user_id": ALICE}


def _ids(built):
    return [n["id"].rsplit(":", 1)[1] for n in built["nodes"] if n["type"] == "bucket_record"]


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", (1, 2, 3, 5, 6, 7))
async def test_a_hidden_window_does_not_hide_the_readable_record_behind_it(monkeypatch, hidden):
    monkeypatch.setattr("knowledge.graph_buckets.SCAN_BATCH", 2)
    monkeypatch.setattr("knowledge.graph_buckets.GRAPH_SCAN_LIMIT", 2)
    rows = [(f"a{i}", _HIDDEN) for i in range(hidden)] + [("z1", _MINE), ("z2", _MINE), ("z3", _MINE)]
    built = await build_bucket_sections(await client_with({"trajectories": rows}), viewer(), manager(), limit=5)
    (section,) = built["sections"]
    assert _ids(built) == ["z1", "z2"], "the cap counts readable records, not the raw ones before them"
    assert (section["total"], section["truncated"], section["budget_exhausted"]) == (2, True, False)


@pytest.mark.asyncio
async def test_a_spent_raw_budget_is_reported_apart_from_the_end_of_data(monkeypatch):
    monkeypatch.setattr("knowledge.graph_buckets.GRAPH_RAW_SCAN_BUDGET", 3)
    rows = [(f"a{i}", _HIDDEN) for i in range(5)] + [("z", _MINE)]
    built = await build_bucket_sections(await client_with({"trajectories": rows}), viewer(), manager())
    (section,) = built["sections"]
    assert (section["total"], section["budget_exhausted"], section["truncated"], section["limited"]) == (
        0,
        True,
        False,
        True,
    )


@pytest.mark.asyncio
async def test_a_collection_that_ends_inside_the_budget_is_not_reported_exhausted(monkeypatch):
    monkeypatch.setattr("knowledge.graph_buckets.GRAPH_RAW_SCAN_BUDGET", 3)
    built = await build_bucket_sections(await client_with({"trajectories": [("a", _MINE)] * 1}), viewer(), manager())
    (section,) = built["sections"]
    assert (section["budget_exhausted"], section["truncated"], section["failed"]) == (False, False, False)


@pytest.mark.asyncio
async def test_one_unreadable_collection_marks_its_section_failed_and_keeps_the_others():
    client = await client_with(
        {"trajectories": [("t", _MINE)], "autobot_memory": [("m", _MINE)], "security_findings": [("s", _MINE)]}
    )
    real = client.get_collection

    async def get_collection(name, *args, **kwargs):
        if name == "security_findings":
            raise RuntimeError("store down")
        return await real(name, *args, **kwargs)

    client.get_collection = get_collection
    built = await build_bucket_sections(client, viewer(), manager())
    by_key = {s["key"]: s for s in built["sections"]}
    assert by_key["research"]["failed"] is True and by_key["research"]["total"] is None
    assert by_key["memory"]["failed"] is False and by_key["memory"]["total"] == 1
    GraphSection(**by_key["research"])  # the response model carries the new fields


@pytest.mark.asyncio
async def test_a_failed_bucket_build_is_a_failed_section_not_an_empty_list():
    with (
        patch("api.knowledge_graph_sections.viewer_for", return_value=viewer()),
        patch("api.knowledge_graph_sections.build_bucket_sections", new=AsyncMock(side_effect=RuntimeError("down"))),
    ):
        kb = type("KB", (), {"_async_chroma_client": object(), "ownership_manager": None})()
        sections = await bucket_sections_for_graph(kb, GraphRequest(), [], [], object(), None)
    assert [(s["key"], s["failed"], s["total"], s["limited"]) for s in sections] == [("buckets", True, None, True)]
