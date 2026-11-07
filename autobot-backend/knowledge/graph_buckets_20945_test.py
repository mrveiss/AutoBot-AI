# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every knowledge bucket reaches a graph section, with total vs returned reported (#20945)."""

import pytest

from knowledge.backends.async_memory_adapter import AsyncInMemoryClient
from knowledge.graph_buckets import (
    BUCKET_SECTIONS,
    EXCLUDED_COLLECTIONS,
    FACT_VECTOR_COLLECTIONS,
    build_bucket_sections,
    is_accounted_for,
    section_for,
)

# Collections that exist on a live install (issue #20945 coverage table), one per store kind.
KNOWN_COLLECTIONS = (
    "autobot_docs",
    "autobot_code",
    "autobot_code_embeddings",
    "code_patterns",
    "cross_language_patterns",
    "autobot_memory",
    "autobot_verbatim",
    "autobot_synthesis_architecture",
    "autobot_text_embeddings",
    "autobot_image_embeddings",
    "autobot_audio_embeddings",
    "autobot_multimodal_fused",
    "trajectories",
    "autoresearch_insights",
    "company:c1",
    "company:c1:agents",
    "company:c1:decisions",
    "project:p1",
    "work_item:w1",
    "autobot_kb",
    "semantic_query_cache",
    "topic_retrieval_cache",
)


async def _client_with(counts: dict[str, int]) -> AsyncInMemoryClient:
    client = AsyncInMemoryClient()
    for name, n in counts.items():
        col = await client.get_or_create_collection(name)
        if n:
            await col.add(
                ids=[f"{name}-{i}" for i in range(n)],
                documents=[f"doc {name} {i}" for i in range(n)],
                metadatas=[{"k": "v"} for _ in range(n)],
                embeddings=[[0.1, 0.2]] * n,
            )
    return client


@pytest.mark.parametrize("name", KNOWN_COLLECTIONS)
def test_every_known_collection_is_mapped_or_explicitly_excluded(name):
    assert is_accounted_for(name), f"{name} holds knowledge but no graph section maps it (#20945)"


def test_exclusions_are_exactly_the_decided_ones():
    assert set(EXCLUDED_COLLECTIONS) == {"semantic_query_cache", "topic_retrieval_cache"}
    assert FACT_VECTOR_COLLECTIONS == ("autobot_kb",)
    assert all(section_for(n) is None for n in EXCLUDED_COLLECTIONS)


@pytest.mark.asyncio
async def test_unmapped_collection_with_data_is_reported():
    client = await _client_with({"autobot_docs": 1, "brand_new_bucket": 2})
    built = await build_bucket_sections(client, is_admin=True)
    assert built["unmapped"] == ["brand_new_bucket"]


@pytest.mark.asyncio
async def test_sections_report_total_vs_returned_and_limit():
    client = await _client_with({"autobot_docs": 5, "autobot_memory": 2, "autobot_code": 3, "code_patterns": 4})
    built = await build_bucket_sections(client, is_admin=False, limit=3)
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
    built = await build_bucket_sections(client, is_admin=True)
    assert built["nodes"] == [] and built["sections"] == [] and built["unmapped"] == []


@pytest.mark.asyncio
async def test_per_entity_buckets_are_admin_only():
    client = await _client_with({"company:c1": 2, "project:p1": 1, "work_item:w1": 1, "autobot_docs": 1})
    non_admin = {s["key"] for s in (await build_bucket_sections(client, is_admin=False))["sections"]}
    admin = {s["key"] for s in (await build_bucket_sections(client, is_admin=True))["sections"]}
    assert non_admin == {"docs"}
    assert admin == {"docs", "company", "project", "work_item"}


def test_section_keys_are_unique():
    keys = [s.key for s in BUCKET_SECTIONS]
    assert len(keys) == len(set(keys))
