# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SkillRouterSkill (skill-router meta-skill)."""


from skills.base_skill import SkillManifest
from skills.builtin.skill_router import _score_skill, _tokenize


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
