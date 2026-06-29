# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the prepared-runtime-facts module (GH#7370)."""

from unittest.mock import MagicMock

import pytest

from prepared_facts import ProviderRuntimeFact, SkillRoutingIndex, SkillTokenFact

# ---------------------------------------------------------------------------
# SkillTokenFact
# ---------------------------------------------------------------------------


def test_skill_token_fact_build_tokenizes_name():
    fact = SkillTokenFact.build_at_startup(
        name="pdf-analyzer",
        tags=[],
        tools=[],
        description="",
    )
    assert "pdf" in fact.name_tokens
    assert "analyzer" in fact.name_tokens


def test_skill_token_fact_build_tokenizes_tags():
    fact = SkillTokenFact.build_at_startup(
        name="x",
        tags=["document", "pdf-analysis"],
        tools=[],
        description="",
    )
    assert "document" in fact.tag_tokens
    assert "pdf" in fact.tag_tokens
    assert "analysis" in fact.tag_tokens


def test_skill_token_fact_build_tokenizes_tools():
    fact = SkillTokenFact.build_at_startup(
        name="x",
        tags=[],
        tools=["analyze_document", "extract_text"],
        description="",
    )
    assert "analyze" in fact.tool_tokens
    assert "document" in fact.tool_tokens
    assert "extract" in fact.tool_tokens
    assert "text" in fact.tool_tokens


def test_skill_token_fact_build_tokenizes_description():
    fact = SkillTokenFact.build_at_startup(
        name="x",
        tags=[],
        tools=[],
        description="Converts audio to text transcription",
    )
    assert "audio" in fact.desc_tokens
    assert "transcription" in fact.desc_tokens


def test_skill_token_fact_score_name_weight():
    fact = SkillTokenFact.build_at_startup(
        name="pdf-tool",
        tags=[],
        tools=[],
        description="",
    )
    # name match only → _W_NAME = 3.0
    assert fact.score(frozenset({"pdf"})) == 3.0


def test_skill_token_fact_score_tag_weight():
    fact = SkillTokenFact.build_at_startup(
        name="unrelated",
        tags=["pdf"],
        tools=[],
        description="",
    )
    # tag match only → _W_TAGS = 3.0
    assert fact.score(frozenset({"pdf"})) == 3.0


def test_skill_token_fact_score_tool_weight():
    fact = SkillTokenFact.build_at_startup(
        name="unrelated",
        tags=[],
        tools=["pdf_reader"],
        description="",
    )
    # tool match → _W_TOOLS = 2.0
    assert fact.score(frozenset({"pdf"})) == 2.0


def test_skill_token_fact_score_desc_weight():
    fact = SkillTokenFact.build_at_startup(
        name="unrelated",
        tags=[],
        tools=[],
        description="handles pdf documents",
    )
    # description match → _W_DESC = 1.0
    assert fact.score(frozenset({"pdf"})) == 1.0


def test_skill_token_fact_score_zero_no_overlap():
    fact = SkillTokenFact.build_at_startup(
        name="calendar-tool",
        tags=["calendar"],
        tools=["create_event"],
        description="manage calendar events",
    )
    assert fact.score(frozenset({"browser", "scrape"})) == 0.0


def test_skill_token_fact_is_frozen():
    fact = SkillTokenFact.build_at_startup("test", [], [], "")
    with pytest.raises(Exception):
        fact.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SkillRoutingIndex
# ---------------------------------------------------------------------------

_SKILLS = [
    {
        "name": "pdf-analyzer",
        "description": "Analyze PDF documents",
        "tags": ["pdf", "document"],
        "tools": ["analyze_pdf"],
    },
    {
        "name": "browser-automation",
        "description": "Automate web browsing",
        "tags": ["browser", "web"],
        "tools": ["browse"],
    },
    {
        "name": "calendar-integration",
        "description": "Manage calendar events",
        "tags": ["calendar", "events"],
        "tools": ["create_event"],
    },
]


def test_routing_index_len():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    assert len(index) == 3


def test_routing_index_score_candidates_returns_top_k():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    results = index.score_candidates("analyze this pdf document", top_k=2)
    assert len(results) <= 2


def test_routing_index_score_candidates_correct_winner():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    results = index.score_candidates("analyze pdf document", top_k=5)
    assert results[0]["name"] == "pdf-analyzer"


def test_routing_index_score_candidates_excludes_zero_scores():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    results = index.score_candidates("completely unrelated xyz query", top_k=5)
    assert results == []


def test_routing_index_score_candidates_result_shape():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    results = index.score_candidates("pdf", top_k=5)
    assert len(results) >= 1
    row = results[0]
    assert "name" in row
    assert "description" in row
    assert "tags" in row
    assert "tools" in row
    assert "score" in row
    assert isinstance(row["score"], float)


def test_routing_index_score_candidates_sorted_desc():
    index = SkillRoutingIndex.build_at_startup(_SKILLS)
    results = index.score_candidates("pdf browser", top_k=5)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_routing_index_empty_registry():
    index = SkillRoutingIndex.build_at_startup([])
    assert len(index) == 0
    assert index.score_candidates("anything", top_k=5) == []


# ---------------------------------------------------------------------------
# ProviderRuntimeFact
# ---------------------------------------------------------------------------


def _provider_with(**settings):
    p = MagicMock()
    p.settings = settings
    return p


def test_provider_fact_auth_configured_via_api_key():
    fact = ProviderRuntimeFact.build_at_startup("openai", _provider_with(api_key="val"))
    assert fact.auth_configured is True


def test_provider_fact_auth_configured_via_api_token():
    fact = ProviderRuntimeFact.build_at_startup("hf", _provider_with(api_token="val"))
    assert fact.auth_configured is True


def test_provider_fact_auth_configured_via_base_url():
    fact = ProviderRuntimeFact.build_at_startup("ollama", _provider_with(base_url="http://localhost:11434"))  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
    assert fact.auth_configured is True


def test_provider_fact_auth_not_configured():
    fact = ProviderRuntimeFact.build_at_startup("unknown", _provider_with())
    assert fact.auth_configured is False


def test_provider_fact_is_local_ollama():
    fact = ProviderRuntimeFact.build_at_startup("ollama", _provider_with(base_url="http://localhost:11434"))  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
    assert fact.is_local is True


def test_provider_fact_is_local_vllm():
    fact = ProviderRuntimeFact.build_at_startup("vllm", _provider_with(base_url="http://localhost:8000"))  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
    assert fact.is_local is True


def test_provider_fact_is_not_local_openai():
    fact = ProviderRuntimeFact.build_at_startup("openai", _provider_with(api_key="val"))
    assert fact.is_local is False


def test_provider_fact_no_settings_attribute():
    provider = MagicMock(spec=[])  # no .settings
    fact = ProviderRuntimeFact.build_at_startup("minimal", provider)
    assert fact.auth_configured is False
    assert fact.is_local is False


def test_provider_fact_is_frozen():
    fact = ProviderRuntimeFact.build_at_startup("openai", _provider_with(api_key="x"))
    with pytest.raises(Exception):
        fact.name = "mutated"  # type: ignore[misc]
