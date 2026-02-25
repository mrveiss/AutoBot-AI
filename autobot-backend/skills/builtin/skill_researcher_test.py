# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SkillResearcherSkill (Issue #1182)."""

import asyncio
from unittest.mock import MagicMock, patch

from skills.builtin.skill_researcher import (
    SkillResearcherSkill,
    _build_queries,
    _empty_findings,
    _parse_synthesis,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_llm_response(content: str) -> MagicMock:
    r = MagicMock()
    r.content = content
    return r


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_name_and_category():
    m = SkillResearcherSkill.get_manifest()
    assert m.name == "skill-researcher"
    assert m.category == "meta"


def test_manifest_has_research_capability_tool():
    m = SkillResearcherSkill.get_manifest()
    assert "research_capability" in m.tools


# ---------------------------------------------------------------------------
# _build_queries
# ---------------------------------------------------------------------------


def test_build_queries_returns_three_angles():
    queries = _build_queries("voice transcription")
    labels = [q[0] for q in queries]
    assert labels == ["technical", "ecosystem", "user_experience"]


def test_build_queries_interpolates_capability():
    queries = _build_queries("pdf parsing")
    for _, prompt in queries:
        assert "pdf parsing" in prompt


# ---------------------------------------------------------------------------
# _parse_synthesis
# ---------------------------------------------------------------------------


def test_parse_synthesis_extracts_json():
    content = '{"summary": "ok", "key_libraries": ["lib1"], "best_practices": [], "common_pitfalls": [], "implementation_hints": "hint"}'
    result = _parse_synthesis(content)
    assert result["summary"] == "ok"
    assert result["key_libraries"] == ["lib1"]


def test_parse_synthesis_extracts_json_from_prose():
    content = 'Here is the result: {"summary": "brief", "key_libraries": [], "best_practices": [], "common_pitfalls": [], "implementation_hints": ""} done.'
    result = _parse_synthesis(content)
    assert result["summary"] == "brief"


def test_parse_synthesis_returns_empty_on_no_json():
    result = _parse_synthesis("no json here")
    assert result == _empty_findings()


def test_parse_synthesis_returns_empty_on_malformed_json():
    result = _parse_synthesis('{"broken": ')
    assert result == _empty_findings()


# ---------------------------------------------------------------------------
# execute dispatch
# ---------------------------------------------------------------------------


def test_execute_unknown_action_returns_error():
    skill = SkillResearcherSkill()
    result = asyncio.run(skill.execute("nonexistent", {}))
    assert result["success"] is False
    assert "Unknown action" in result["error"]


# ---------------------------------------------------------------------------
# _research — validation
# ---------------------------------------------------------------------------


def test_research_requires_capability():
    skill = SkillResearcherSkill()
    result = asyncio.run(skill.execute("research_capability", {}))
    assert result["success"] is False
    assert "capability" in result["error"].lower()


def test_research_fails_gracefully_without_llm():
    with patch("skills.builtin.skill_researcher.LLMInterface", None):
        skill = SkillResearcherSkill()
        result = asyncio.run(
            skill.execute("research_capability", {"capability": "test"})
        )
    assert result["success"] is False
    assert "LLMInterface" in result["error"]


# ---------------------------------------------------------------------------
# _research — happy path
# ---------------------------------------------------------------------------


def test_research_returns_structured_findings():
    source_response = _mock_llm_response(
        "Technical explanation of voice transcription."
    )
    synthesis_response = _mock_llm_response(
        '{"summary": "Converts speech to text", '
        '"key_libraries": ["whisper", "faster-whisper"], '
        '"best_practices": ["Use VAD"], '
        '"common_pitfalls": ["Large model memory"], '
        '"implementation_hints": "Use faster-whisper for speed"}'
    )

    call_count = 0

    async def mock_chat(messages, llm_type="task"):
        nonlocal call_count
        call_count += 1
        # First 3 calls: source queries; 4th: synthesis
        return synthesis_response if call_count > 3 else source_response

    with patch("skills.builtin.skill_researcher.LLMInterface") as MockLLM:
        MockLLM.return_value.chat_completion = mock_chat
        skill = SkillResearcherSkill()
        result = asyncio.run(
            skill.execute("research_capability", {"capability": "voice transcription"})
        )

    assert result["success"] is True
    assert result["capability"] == "voice transcription"
    assert result["sources_consulted"] == 3
    assert "whisper" in result["key_libraries"]
    assert result["summary"] == "Converts speech to text"


# ---------------------------------------------------------------------------
# _research — partial failure (some queries fail)
# ---------------------------------------------------------------------------


def test_research_continues_when_some_queries_fail():
    """One LLM failure does not abort the whole research pipeline."""
    call_count = 0

    async def mock_chat(messages, llm_type="task"):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("LLM timeout")
        if call_count > 3:
            return _mock_llm_response(
                '{"summary": "ok", "key_libraries": [], '
                '"best_practices": [], "common_pitfalls": [], '
                '"implementation_hints": ""}'
            )
        return _mock_llm_response("content")

    with patch("skills.builtin.skill_researcher.LLMInterface") as MockLLM:
        MockLLM.return_value.chat_completion = mock_chat
        skill = SkillResearcherSkill()
        result = asyncio.run(
            skill.execute("research_capability", {"capability": "voice transcription"})
        )

    assert result["success"] is True
    assert result["sources_consulted"] == 2  # one query failed, two succeeded


# ---------------------------------------------------------------------------
# _research — synthesis failure
# ---------------------------------------------------------------------------


def test_research_returns_empty_findings_when_synthesis_fails():
    """If synthesis LLM call fails, return empty findings (not an error)."""

    async def mock_chat(messages, llm_type="task"):
        raise RuntimeError("LLM down")

    with patch("skills.builtin.skill_researcher.LLMInterface") as MockLLM:
        MockLLM.return_value.chat_completion = mock_chat
        skill = SkillResearcherSkill()
        result = asyncio.run(
            skill.execute("research_capability", {"capability": "voice transcription"})
        )

    # sources_consulted == 0 means synthesis returns empty but success=True
    assert result["success"] is True
    assert result["sources_consulted"] == 0
    assert result["key_libraries"] == []
