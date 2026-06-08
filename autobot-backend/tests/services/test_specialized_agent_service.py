# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for SpecializedAgentService (#1821).

Tests cover the three module-level helpers and the three public methods
of SpecializedAgentService, using tmp_path for filesystem isolation.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from autobot_shared.logging_manager import get_logger
from services.specialized_agent_service import (
    SpecializedAgentService,
    _categorize_agent,
    _extract_system_prompt_excerpt,
    _parse_frontmatter,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

FULL_AGENT_MD = """\
---
name: Senior Backend Engineer
description: Expert Python backend developer
model: claude-sonnet-4-20250514
color: blue
tools: Bash, Read, Write, Glob, Grep
---

You are a senior backend engineer specializing in Python.
"""

MINIMAL_AGENT_MD = """\
---
name: Quick Helper
description: A minimal agent
---

Does simple things.
"""

NO_FRONTMATTER_MD = """\
This file has no YAML frontmatter at all.
Just raw markdown content.
"""


@pytest.fixture()
def agents_dir(tmp_path: Path) -> Path:
    """Create a temporary agents directory with sample .md files."""
    d = tmp_path / "agents"
    d.mkdir()
    (d / "senior-backend-engineer.md").write_text(FULL_AGENT_MD, encoding="utf-8")
    (d / "quick-helper.md").write_text(MINIMAL_AGENT_MD, encoding="utf-8")
    return d


@pytest.fixture()
def service(agents_dir: Path) -> SpecializedAgentService:
    """SpecializedAgentService pointing at the tmp agents dir."""
    return SpecializedAgentService(agents_dir=agents_dir)


# ---------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------


class TestParseFrontmatter:
    """Tests for _parse_frontmatter helper (#1821)."""

    def test_full_frontmatter(self):
        """All supported fields are extracted correctly."""
        result = _parse_frontmatter(FULL_AGENT_MD)
        assert result["name"] == "Senior Backend Engineer"
        assert result["description"] == "Expert Python backend developer"
        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["color"] == "blue"
        assert result["tools"] == ["Bash", "Read", "Write", "Glob", "Grep"]

    def test_missing_frontmatter(self):
        """Content without --- delimiters returns defaults."""
        result = _parse_frontmatter(NO_FRONTMATTER_MD)
        assert result["name"] == ""
        assert result["description"] == ""
        assert result["tools"] == []
        assert result["color"] == "gray"
        assert result["model"] is None

    def test_partial_fields(self):
        """Only specified fields are populated; others keep defaults."""
        result = _parse_frontmatter(MINIMAL_AGENT_MD)
        assert result["name"] == "Quick Helper"
        assert result["description"] == "A minimal agent"
        assert result["tools"] == []
        assert result["color"] == "gray"
        assert result["model"] is None

    def test_empty_tools_field(self):
        """An empty tools value produces an empty list."""
        md = "---\nname: Test\ntools: \n---\nBody"
        result = _parse_frontmatter(md)
        assert result["tools"] == []

    def test_single_tool(self):
        """A single tool without commas is parsed correctly."""
        md = "---\ntools: Bash\n---\nBody"
        result = _parse_frontmatter(md)
        assert result["tools"] == ["Bash"]

    def test_tools_whitespace_trimmed(self):
        """Whitespace around tool names is stripped."""
        md = "---\ntools:  Bash , Read , Write \n---\nBody"
        result = _parse_frontmatter(md)
        assert result["tools"] == ["Bash", "Read", "Write"]

    def test_unknown_keys_ignored(self):
        """Keys not in the schema are silently ignored."""
        md = "---\nname: X\nunknown_key: whatever\n---\nBody"
        result = _parse_frontmatter(md)
        assert result["name"] == "X"
        assert "unknown_key" not in result

    def test_colon_in_value(self):
        """Values containing colons are preserved (split on first only)."""
        md = "---\ndescription: Handles http://example.com URLs\n---\n"
        result = _parse_frontmatter(md)
        assert result["description"] == "Handles http://example.com URLs"


# ---------------------------------------------------------------
# _categorize_agent
# ---------------------------------------------------------------


class TestCategorizeAgent:
    """Tests for _categorize_agent helper (#1821)."""

    @pytest.mark.parametrize(
        "name,description,expected",
        [
            ("Senior Backend Engineer", "Python dev", "implementation"),
            ("Frontend Engineer", "Vue.js expert", "implementation"),
            ("DevOps Engineer", "Infrastructure", "implementation"),
            ("Testing Engineer", "QA specialist", "implementation"),
        ],
    )
    def test_implementation_keywords(self, name, description, expected):
        """Names with engineer/developer/backend etc map to implementation."""
        assert _categorize_agent(name, description) == expected

    @pytest.mark.parametrize(
        "name,description,expected",
        [
            ("Code Skeptic", "Risk analysis", "analysis"),
            ("Systems Architect", "Design review", "analysis"),
            ("Security Auditor", "Vulnerability audit", "analysis"),
            ("Performance Analyst", "Bottleneck review", "analysis"),
        ],
    )
    def test_analysis_keywords(self, name, description, expected):
        """Names with skeptic/architect/security etc map to analysis."""
        assert _categorize_agent(name, description) == expected

    def test_analysis_checked_before_implementation(self):
        """Analysis keywords checked first — 'security' matches before 'testing'."""
        # "Security Auditor" + "Pen testing" -> "security" matches
        # analysis first (#1844), even though "testing" is in the text.
        result = _categorize_agent("Security Auditor", "Pen testing")
        assert result == "analysis"

    @pytest.mark.parametrize(
        "name,description,expected",
        [
            ("Project Manager", "Scheduling", "planning"),
            ("Task Planner", "Sprint planning", "planning"),
            ("PRD Writer", "Product requirements", "planning"),
        ],
    )
    def test_planning_keywords(self, name, description, expected):
        """Names with project/manager/planner etc map to planning."""
        assert _categorize_agent(name, description) == expected

    @pytest.mark.parametrize(
        "name,description,expected",
        [
            ("Content Writer", "Technical writing", "specialized"),
            ("Memory Compacter", "Context reduction", "specialized"),
            ("Code Refactor Agent", "Cleanup duty", "specialized"),
        ],
    )
    def test_specialized_keywords(self, name, description, expected):
        """Names with writer/memory/refactor etc map to specialized."""
        assert _categorize_agent(name, description) == expected

    def test_reviewer_override_to_analysis(self):
        """An 'engineer' with 'review' in text maps to analysis."""
        result = _categorize_agent("Code Review Engineer", "Detailed code review")
        assert result == "analysis"

    def test_analysis_keyword_in_description_overrides(self):
        """'analysis' in description overrides implementation category."""
        result = _categorize_agent("Senior Engineer", "Does analysis of codebases")
        assert result == "analysis"

    def test_fallback_general(self):
        """Unknown agent names/descriptions fall back to 'general'."""
        assert _categorize_agent("Mystery Bot", "Does stuff") == "general"

    def test_case_insensitive(self):
        """Categorization is case-insensitive."""
        assert _categorize_agent("BACKEND Dev", "") == "implementation"
        assert _categorize_agent("SECURITY check", "") == "analysis"


# ---------------------------------------------------------------
# _extract_system_prompt_excerpt
# ---------------------------------------------------------------


class TestExtractSystemPromptExcerpt:
    """Tests for _extract_system_prompt_excerpt helper (#1821)."""

    def test_truncation_with_ellipsis(self):
        """Long body is truncated at max_chars with ellipsis appended."""
        result = _extract_system_prompt_excerpt(FULL_AGENT_MD, max_chars=10)
        assert len(result) == 11  # 10 chars + ellipsis character
        assert result.endswith("\u2026")

    def test_short_content_no_truncation(self):
        """Short body is returned in full without ellipsis."""
        result = _extract_system_prompt_excerpt(FULL_AGENT_MD, max_chars=5000)
        assert "\u2026" not in result
        assert "senior backend engineer" in result.lower()

    def test_no_frontmatter(self):
        """Content without frontmatter uses the whole text as body."""
        result = _extract_system_prompt_excerpt(NO_FRONTMATTER_MD, max_chars=5000)
        assert "no YAML frontmatter" in result

    def test_default_max_chars(self):
        """Default max_chars is 300."""
        long_body = "---\nname: X\n---\n" + "A" * 500
        result = _extract_system_prompt_excerpt(long_body)
        # 300 chars + ellipsis
        assert len(result) == 301

    def test_body_whitespace_stripped(self):
        """Leading/trailing whitespace after frontmatter is stripped."""
        md = "---\nname: X\n---\n\n\n   Body text   \n\n"
        result = _extract_system_prompt_excerpt(md, max_chars=5000)
        assert result == "Body text"


# ---------------------------------------------------------------
# SpecializedAgentService.list_agents
# ---------------------------------------------------------------


class TestListAgents:
    """Tests for SpecializedAgentService.list_agents (#1821)."""

    def test_happy_path(self, service, agents_dir):
        """Returns all parseable .md files in sorted order."""
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            agents = service.list_agents()
        assert len(agents) == 2
        ids = [a["id"] for a in agents]
        assert ids == ["quick-helper", "senior-backend-engineer"]

    def test_missing_directory(self, tmp_path):
        """Returns empty list when agents directory does not exist."""
        svc = SpecializedAgentService(agents_dir=tmp_path / "nonexistent")
        assert svc.list_agents() == []

    def test_unreadable_file_skipped(self, agents_dir):
        """Unreadable files are skipped without crashing (#1821)."""
        bad_file = agents_dir / "broken.md"
        bad_file.write_text("---\nname: B\n---\nBody", encoding="utf-8")
        bad_file.chmod(0o000)

        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            svc = SpecializedAgentService(agents_dir=agents_dir)
            agents = svc.list_agents()

        # Restore permissions for tmp_path cleanup
        bad_file.chmod(0o644)
        # broken.md is skipped; the other two remain
        assert len(agents) == 2

    def test_non_md_files_ignored(self, agents_dir):
        """Non-.md files in the directory are ignored."""
        (agents_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            agents = SpecializedAgentService(agents_dir=agents_dir).list_agents()
        assert len(agents) == 2

    def test_agent_fields_populated(self, service, agents_dir):
        """Each agent dict contains all expected keys."""
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            agents = service.list_agents()
        expected_keys = {
            "id",
            "name",
            "description",
            "model",
            "color",
            "tools",
            "category",
            "source_file",
            "type",
            "excerpt",
        }
        for agent in agents:
            assert set(agent.keys()) == expected_keys

    def test_no_frontmatter_uses_stem_as_name(self, agents_dir):
        """Agent file without frontmatter uses filename stem as name."""
        (agents_dir / "plain-agent.md").write_text(NO_FRONTMATTER_MD, encoding="utf-8")
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            svc = SpecializedAgentService(agents_dir=agents_dir)
            agents = svc.list_agents()
        plain = [a for a in agents if a["id"] == "plain-agent"][0]
        assert plain["name"] == "plain-agent"


# ---------------------------------------------------------------
# SpecializedAgentService.get_agent
# ---------------------------------------------------------------


class TestGetAgent:
    """Tests for SpecializedAgentService.get_agent (#1821)."""

    def test_existing_agent(self, service, agents_dir):
        """Returns agent dict with system_prompt for valid ID."""
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            agent = service.get_agent("senior-backend-engineer")
        assert agent is not None
        assert agent["id"] == "senior-backend-engineer"
        assert agent["name"] == "Senior Backend Engineer"
        assert "system_prompt" in agent

    def test_system_prompt_included(self, service, agents_dir):
        """get_agent includes full system_prompt (not just excerpt)."""
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            agent = service.get_agent("senior-backend-engineer")
        prompt = agent["system_prompt"]
        assert "senior backend engineer" in prompt.lower()

    def test_nonexistent_agent(self, service):
        """Returns None for an agent ID that does not exist."""
        assert service.get_agent("does-not-exist") is None

    def test_missing_directory(self, tmp_path):
        """Returns None when agents directory does not exist."""
        svc = SpecializedAgentService(agents_dir=tmp_path / "nonexistent")
        assert svc.get_agent("anything") is None


# ---------------------------------------------------------------
# SpecializedAgentService.get_categories_summary
# ---------------------------------------------------------------


class TestGetCategoriesSummary:
    """Tests for SpecializedAgentService.get_categories_summary (#1821)."""

    def test_counts_from_agents_list(self):
        """Counts categories correctly from a provided agents list."""
        agents = [
            {"category": "implementation"},
            {"category": "implementation"},
            {"category": "analysis"},
            {"category": "planning"},
        ]
        svc = SpecializedAgentService(agents_dir=Path("/nonexistent"))
        result = svc.get_categories_summary(agents=agents)
        assert result == {
            "implementation": 2,
            "analysis": 1,
            "planning": 1,
        }

    def test_empty_agents_list(self):
        """Empty agents list returns empty dict."""
        svc = SpecializedAgentService(agents_dir=Path("/nonexistent"))
        assert svc.get_categories_summary(agents=[]) == {}

    def test_delegates_to_list_agents(self, service, agents_dir):
        """When agents=None, delegates to list_agents()."""
        with patch(
            "services.specialized_agent_service._REPO_ROOT",
            agents_dir.parent,
        ):
            result = service.get_categories_summary()
        # Two agents: one implementation, one general
        assert sum(result.values()) == 2

    def test_missing_category_defaults_general(self):
        """Agents without category key count as 'general'."""
        agents = [{"category": "analysis"}, {}]
        svc = SpecializedAgentService(agents_dir=Path("/nonexistent"))
        result = svc.get_categories_summary(agents=agents)
        assert result == {"analysis": 1, "general": 1}
