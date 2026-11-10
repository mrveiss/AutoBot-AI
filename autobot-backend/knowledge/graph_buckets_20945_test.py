# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every knowledge bucket reaches a graph section, with total vs returned reported (#20945)."""

from pathlib import Path

import pytest

from knowledge.backends.async_memory_adapter import AsyncInMemoryClient
from knowledge.graph_buckets import (
    BUCKET_SECTIONS,
    EXCLUDED_COLLECTIONS,
    FACT_VECTOR_COLLECTIONS,
    SCRATCH_COLLECTIONS,
    build_bucket_sections,
    is_accounted_for,
    section_for,
)
from knowledge.index_embedding_space import ACCELERATOR_COLLECTIONS, CODE_INDEX, PATTERN_INDEXES
from tests.fixtures.graph_buckets_fakes_20945 import client_with, manager, viewer
from tests.fixtures.graph_collection_source import backend_collection_names, names_in_source

BACKEND = Path(__file__).resolve().parent.parent
# What the backend source names today (derived, never hand-kept): the guard fails on any new collection.
SOURCE_COLLECTIONS = sorted(backend_collection_names(BACKEND))
# Live-install buckets that are created at runtime, so no source constant names them (issue #20945 table).
RUNTIME_COLLECTIONS = ("company:c1", "company:c1:agents", "project:p1", "work_item:w1", "sprint:s1", "agent:a1")


def unmapped_collections(names) -> list:
    """The collections neither mapped to a section nor explicitly excluded: what the guard fails on."""
    return sorted(n for n in names if not is_accounted_for(n))


async def _client_with(counts: dict[str, int]) -> AsyncInMemoryClient:
    return await client_with({name: [(f"{name}-{i}", {"k": "v"}) for i in range(n)] for name, n in counts.items()})


def test_the_source_scan_finds_the_known_stores():
    """Control: a scan that found nothing would pass the guard vacuously (a parser's zero is a claim)."""
    assert len(SOURCE_COLLECTIONS) > 20
    assert {"autobot_docs", "autobot_code", "trajectories", "autobot_verbatim", "autobot_memory"} <= set(
        SOURCE_COLLECTIONS
    )


@pytest.mark.parametrize("name", [*SOURCE_COLLECTIONS, *RUNTIME_COLLECTIONS])
def test_every_collection_the_source_names_is_mapped_or_explicitly_excluded(name):
    assert is_accounted_for(name), f"{name} holds knowledge but no graph section maps it (#20945)"


def test_a_planted_new_collection_fails_the_guard():
    """Planted control: a collection added in source that no section maps must be reported, not pass."""
    planted = names_in_source('NEW_THING_COLLECTION = "brand_new_bucket"\nclient.get_or_create_collection("other_new")')
    assert planted == {"brand_new_bucket", "other_new"}
    assert unmapped_collections(SOURCE_COLLECTIONS) == [], "the real source is fully accounted for"
    assert unmapped_collections([*SOURCE_COLLECTIONS, *planted]) == ["brand_new_bucket", "other_new"]


def test_every_pattern_and_accelerator_index_is_mapped():
    assert unmapped_collections([*ACCELERATOR_COLLECTIONS, *PATTERN_INDEXES, CODE_INDEX]) == []


def test_exclusions_are_exactly_the_decided_ones():
    assert set(EXCLUDED_COLLECTIONS) == {"semantic_query_cache", "topic_retrieval_cache"}
    assert set(SCRATCH_COLLECTIONS) == {"benchmark_run", "real_kb_bench", "loop_eval_bench", "autobot_memories"}
    assert FACT_VECTOR_COLLECTIONS == ("autobot_kb",)
    assert all(section_for(n) is None for n in EXCLUDED_COLLECTIONS)


@pytest.mark.asyncio
async def test_unmapped_collection_with_data_is_reported():
    client = await _client_with({"autobot_docs": 1, "brand_new_bucket": 2})
    built = await build_bucket_sections(client, viewer(admin=True), manager())
    assert built["unmapped"] == ["brand_new_bucket"]


@pytest.mark.asyncio
async def test_sections_report_total_vs_returned_and_limit():
    client = await _client_with({"autobot_docs": 5, "autobot_memory": 2, "autobot_code": 3, "code_patterns": 4})
    built = await build_bucket_sections(client, viewer(admin=True), manager(), limit=3)
    report = {s["key"]: s for s in built["sections"]}
    assert (report["docs"]["total"], report["docs"]["returned"], report["docs"]["limited"]) == (5, 3, True)
    assert (report["memory"]["total"], report["memory"]["returned"], report["memory"]["limited"]) == (2, 2, False)
    assert (report["code"]["total"], report["code"]["returned"]) == (7, 3)  # two collections share one cap
    kinds = {n["type"] for n in built["nodes"]}
    assert kinds == {"section", "bucket_record"}
    assert all(e["from"].startswith("section:") for e in built["edges"])


@pytest.mark.asyncio
async def test_caches_and_empty_collections_make_no_section():
    client = await _client_with({"semantic_query_cache": 3, "topic_retrieval_cache": 3, "autobot_docs": 0})
    built = await build_bucket_sections(client, viewer(admin=True), manager())
    assert built["nodes"] == [] and built["sections"] == [] and built["unmapped"] == []


@pytest.mark.asyncio
async def test_per_entity_buckets_are_admin_only():
    client = await _client_with({"company:c1": 2, "project:p1": 1, "work_item:w1": 1, "autobot_docs": 1})
    non_admin = {s["key"] for s in (await build_bucket_sections(client, viewer(), manager()))["sections"]}
    admin = {s["key"] for s in (await build_bucket_sections(client, viewer(superadmin=True), manager()))["sections"]}
    assert non_admin == {"docs"}
    assert admin == {"docs", "company", "project", "work_item"}


def test_section_keys_are_unique():
    keys = [s.key for s in BUCKET_SECTIONS]
    assert len(keys) == len(set(keys))
