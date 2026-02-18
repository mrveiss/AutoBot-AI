# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the Skill Gap Detector (Phase 4)."""
from skills.gap_detector import GapTrigger, SkillGapDetector


def test_explicit_trigger_from_agent_output():
    """Explicit gap pattern in agent output returns GapResult with EXPLICIT trigger."""
    detector = SkillGapDetector(available_tools=["web_search", "scrape_url"])
    result = detector.analyze_agent_output(
        "I don't have a tool to parse PDF files. I cannot complete this task."
    )
    assert result is not None
    assert result.trigger == GapTrigger.EXPLICIT
    assert "pdf" in result.capability.lower()


def test_no_gap_when_tool_available():
    """No gap detected when agent text has no gap signals."""
    detector = SkillGapDetector(available_tools=["parse_pdf"])
    result = detector.analyze_agent_output("Let me parse that PDF for you.")
    assert result is None


def test_failed_call_trigger():
    """Tool call for unknown tool returns GapResult with FAILED_CALL trigger."""
    detector = SkillGapDetector(available_tools=["web_search"])
    result = detector.analyze_failed_tool_call("parse_pdf", {"path": "doc.pdf"})
    assert result is not None
    assert result.trigger == GapTrigger.FAILED_CALL
    assert "parse_pdf" in result.capability


def test_failed_call_no_gap_when_tool_exists():
    """Failed call for a known tool does not produce a gap result."""
    detector = SkillGapDetector(available_tools=["web_search"])
    result = detector.analyze_failed_tool_call("web_search", {"query": "test"})
    assert result is None


def test_user_hint_trigger():
    """User message requesting an unrecognized capability returns USER_HINT gap."""
    detector = SkillGapDetector(available_tools=["web_search"])
    result = detector.analyze_user_message("Can you translate this document to French?")
    assert result is not None
    assert result.trigger == GapTrigger.USER_HINT


def test_gap_result_has_context():
    """GapResult context dict contains relevant source data."""
    detector = SkillGapDetector(available_tools=[])
    result = detector.analyze_failed_tool_call("render_chart", {"data": [1, 2, 3]})
    assert "tool_name" in result.context
    assert result.context["tool_name"] == "render_chart"
