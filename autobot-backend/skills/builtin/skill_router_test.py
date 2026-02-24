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


def _make_skill_dict(name, description, tags, tools):
    """Build the dict format returned by registry.list_skills()."""
    return {
        "name": name,
        "description": description,
        "tags": tags,
        "tools": tools,
        "status": "available",
        "enabled": False,
    }


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
    assert reason == "code task"


def test_find_skill_enables_best_match_via_llm():
    """find_skill should enable the LLM-chosen winner and return it."""
    mock_llm_response = MagicMock()
    mock_llm_response.content = '{"skill": "document-analysis", "reason": "PDF task"}'
    mock_llm_response.error = None

    mock_registry = MagicMock()
    mock_registry.list_skills.return_value = [
        _make_skill_dict(
            "document-analysis",
            "Analyze documents",
            ["document", "pdf"],
            ["analyze_doc"],
        ),
        _make_skill_dict(
            "browser-automation", "Automate browser", ["browser", "web"], ["browse"]
        ),
    ]
    mock_registry.enable_skill.return_value = {"success": True}

    with patch(
        "skills.builtin.skill_router.get_skill_registry", return_value=mock_registry
    ), patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_llm_response)

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.run(
            skill.execute("find_skill", {"task": "analyze this pdf document"})
        )

    assert result["success"] is True
    assert result["enabled_skill"] == "document-analysis"
    assert result["method"] == "llm"
    assert "reason" in result
    assert len(result["candidates"]) > 0
    mock_registry.enable_skill.assert_called_once_with("document-analysis")


def test_find_skill_falls_back_to_keyword_on_llm_error():
    """If LLM fails, use the top keyword-scored skill."""
    mock_registry = MagicMock()
    mock_registry.list_skills.return_value = [
        _make_skill_dict(
            "document-analysis",
            "Analyze documents",
            ["document", "pdf"],
            ["analyze_doc"],
        ),
        _make_skill_dict(
            "browser-automation", "Automate browser", ["browser"], ["browse"]
        ),
    ]
    mock_registry.enable_skill.return_value = {"success": True}

    with patch(
        "skills.builtin.skill_router.get_skill_registry", return_value=mock_registry
    ), patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(side_effect=Exception("LLM timeout"))

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.run(
            skill.execute("find_skill", {"task": "analyze this pdf document"})
        )

    assert result["success"] is True
    assert result["enabled_skill"] == "document-analysis"
    assert result["method"] == "keyword_fallback"


def test_find_skill_dry_run_does_not_enable():
    """dry_run=True should return result without calling enable_skill."""
    mock_llm_response = MagicMock()
    mock_llm_response.content = '{"skill": "document-analysis", "reason": "test"}'
    mock_llm_response.error = None

    mock_registry = MagicMock()
    mock_registry.list_skills.return_value = [
        _make_skill_dict(
            "document-analysis",
            "Analyze documents",
            ["document", "pdf"],
            ["analyze_doc"],
        ),
    ]

    with patch(
        "skills.builtin.skill_router.get_skill_registry", return_value=mock_registry
    ), patch("skills.builtin.skill_router.LLMInterface") as MockLLM:
        instance = MockLLM.return_value
        instance.chat_completion = AsyncMock(return_value=mock_llm_response)

        skill = SkillRouterSkill()
        skill.apply_config({"top_k": 5, "auto_enable": True})
        result = asyncio.run(
            skill.execute("find_skill", {"task": "analyze pdf", "dry_run": True})
        )

    assert result["success"] is True
    mock_registry.enable_skill.assert_not_called()


def test_find_skill_requires_task_param():
    """find_skill with no task returns error."""
    skill = SkillRouterSkill()
    result = asyncio.run(skill.execute("find_skill", {}))
    assert result["success"] is False
    assert "task" in result["error"].lower()


def test_find_skill_no_skills_registered():
    """find_skill returns error when registry is empty."""
    mock_registry = MagicMock()
    mock_registry.list_skills.return_value = []

    with patch(
        "skills.builtin.skill_router.get_skill_registry", return_value=mock_registry
    ):
        skill = SkillRouterSkill()
        result = asyncio.run(skill.execute("find_skill", {"task": "do something"}))

    assert result["success"] is False
    assert "no skills" in result["error"].lower()
