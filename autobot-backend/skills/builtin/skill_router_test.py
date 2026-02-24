# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SkillRouterSkill (skill-router meta-skill)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from skills.base_skill import SkillManifest
from skills.builtin.skill_router import SkillRouterSkill, _score_skill, _tokenize


def _make_manifest(name, description, tags, tools):
    return SkillManifest(
        name=name,
        version="1.0.0",
        description=description,
        author="mrveiss",
        category="test",
        tags=tags,
        tools=tools,
    )


def test_tokenize_splits_on_non_word():
    assert _tokenize("analyze this PDF document") == {
        "analyze",
        "this",
        "pdf",
        "document",
    }


def test_tokenize_handles_kebab_and_underscore():
    assert "browser" in _tokenize("browser-automation")
    assert "automation" in _tokenize("browser-automation")
    assert "code" in _tokenize("code_review")


def test_score_skill_matches_tags():
    manifest = _make_manifest(
        name="document-analysis",
        description="Analyze documents",
        tags=["document", "pdf", "analysis"],
        tools=["analyze_doc"],
    )
    score = _score_skill({"pdf", "document"}, manifest)
    assert score == 9.0


def test_score_skill_tag_and_name_weighted_higher_than_description():
    manifest_good = _make_manifest(
        name="pdf-tool",
        description="General purpose tool",
        tags=["pdf"],
        tools=["process"],
    )
    manifest_weak = _make_manifest(
        name="general-tool",
        description="This tool handles pdf documents",
        tags=["general"],
        tools=["process"],
    )
    score_good = _score_skill({"pdf"}, manifest_good)
    score_weak = _score_skill({"pdf"}, manifest_weak)
    assert score_good > score_weak


def test_score_skill_zero_for_no_match():
    manifest = _make_manifest(
        name="calendar-integration",
        description="Manage calendar events",
        tags=["calendar", "events"],
        tools=["create_event"],
    )
    score = _score_skill({"browser", "scrape", "web"}, manifest)
    assert score == 0.0


def test_llm_rerank_parses_json_response():
    """_llm_rerank should parse skill name and reason from LLM JSON."""
    mock_response = MagicMock()
    mock_response.content = '{"skill": "document-analysis", "reason": "PDF task"}'
    mock_response.error = None

    candidates = [
        {
            "name": "document-analysis",
            "description": "Analyze docs",
            "tags": [],
            "tools": [],
        },
        {
            "name": "browser-automation",
            "description": "Browse web",
            "tags": [],
            "tools": [],
        },
    ]

    with patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_response)

        skill = SkillRouterSkill()
        name, reason = asyncio.run(skill._llm_rerank("analyze this pdf", candidates))

    assert name == "document-analysis"
    assert reason == "PDF task"


def test_llm_rerank_handles_markdown_code_block():
    """_llm_rerank should extract JSON from ```json ... ``` blocks."""
    mock_response = MagicMock()
    mock_response.content = (
        '```json\n{"skill": "code-review", "reason": "code task"}\n```'
    )
    mock_response.error = None

    candidates = [
        {"name": "code-review", "description": "Review code", "tags": [], "tools": []},
    ]

    with patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_response)

        skill = SkillRouterSkill()
        name, reason = asyncio.run(skill._llm_rerank("review my code", candidates))

    assert name == "code-review"
