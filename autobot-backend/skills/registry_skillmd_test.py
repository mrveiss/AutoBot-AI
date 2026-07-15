# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SKILL.md-only builtin skill discovery (Issue #10959).

Verifies that discover_builtin_skills registers the 4 declarative builtins
(web-fetch, github-search, youtube-transcript, rss-reader) that have only a
SKILL.md and no Python BaseSkill subclass.
"""

import textwrap
from unittest.mock import patch

import pytest

from skills.base_skill import BaseSkill, DeclarativeSkill, SkillManifest
from skills.registry import SkillRegistry, _parse_skill_md

# ---------------------------------------------------------------------------
# _parse_skill_md
# ---------------------------------------------------------------------------


def test_parse_skill_md_returns_manifest(tmp_path):
    """_parse_skill_md parses a minimal front-matter into a SkillManifest."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        textwrap.dedent("""\
        ---
        name: test-skill
        version: 2.0.0
        description: A test declarative skill
        author: mrveiss
        category: internet
        tools:
          - fetch_url
        triggers:
          - fetch URL
        tags:
          - web
        ---

        ## Body content here
        """),
        encoding="utf-8",
    )

    manifest = _parse_skill_md(str(skill_md))

    assert manifest is not None
    assert manifest.name == "test-skill"
    assert manifest.version == "2.0.0"
    assert manifest.description == "A test declarative skill"
    assert manifest.category == "internet"
    assert "fetch_url" in manifest.tools
    assert "fetch URL" in manifest.triggers
    assert "web" in manifest.tags


def test_parse_skill_md_missing_name_returns_none(tmp_path):
    """_parse_skill_md returns None when the 'name' field is absent."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        textwrap.dedent("""\
        ---
        version: 1.0.0
        description: No name field
        ---
        """),
        encoding="utf-8",
    )

    assert _parse_skill_md(str(skill_md)) is None


def test_parse_skill_md_no_frontmatter_returns_none(tmp_path):
    """_parse_skill_md returns None when there is no --- block."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("Just prose, no front-matter.\n", encoding="utf-8")

    assert _parse_skill_md(str(skill_md)) is None


def test_parse_skill_md_invalid_yaml_returns_none(tmp_path):
    """_parse_skill_md returns None on broken YAML."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: [broken yaml\n---\n", encoding="utf-8")

    assert _parse_skill_md(str(skill_md)) is None


def test_parse_skill_md_uses_defaults_for_optional_fields(tmp_path):
    """Optional fields default gracefully when absent from front-matter."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        textwrap.dedent("""\
        ---
        name: minimal-skill
        description: Minimal
        ---
        """),
        encoding="utf-8",
    )

    manifest = _parse_skill_md(str(skill_md))

    assert manifest is not None
    assert manifest.version == "1.0.0"
    assert manifest.author == "mrveiss"
    assert manifest.category == "general"
    assert manifest.tools == []
    assert manifest.triggers == []
    assert manifest.tags == []


# ---------------------------------------------------------------------------
# DeclarativeSkill
# ---------------------------------------------------------------------------


def test_declarative_skill_get_manifest_returns_supplied_manifest():
    """DeclarativeSkill.get_manifest() returns the manifest given at construction."""
    manifest = SkillManifest(
        name="web-fetch",
        version="1.0.0",
        description="Fetch URLs",
        tools=["fetch_url"],
    )
    skill = DeclarativeSkill(manifest)

    assert skill.get_manifest() is manifest


@pytest.mark.asyncio
async def test_declarative_skill_execute_returns_clear_error():
    """execute() on a declarative skill returns success=False with a clear message."""
    manifest = SkillManifest(name="web-fetch", version="1.0.0", description="Fetch URLs")
    skill = DeclarativeSkill(manifest)

    result = await skill.execute("fetch_url", {"url": "https://example.com"})

    assert result["success"] is False
    assert "declarative" in result["error"].lower()
    assert "web-fetch" in result["error"]


def test_declarative_skill_is_baseskill_subclass():
    """DeclarativeSkill must be a concrete subclass of BaseSkill."""
    manifest = SkillManifest(name="rss-reader", version="1.0.0", description="RSS")
    skill = DeclarativeSkill(manifest)

    assert isinstance(skill, BaseSkill)


# ---------------------------------------------------------------------------
# discover_builtin_skills — integration with real builtin package
# ---------------------------------------------------------------------------


_DECLARATIVE_SKILL_IDS = {"web-fetch", "github-search", "youtube-transcript", "rss-reader"}


def test_discover_builtin_skills_registers_declarative_skills():
    """All 4 SKILL.md-only builtins appear in the registry after discovery."""
    registry = SkillRegistry()

    # Suppress Redis publish side-effects (no Redis in unit tests)
    with patch.object(registry, "_publish_skill_promoted"):
        registry.discover_builtin_skills()

    registered_names = {info["name"] for info in registry.list_skills()}
    missing = _DECLARATIVE_SKILL_IDS - registered_names
    assert not missing, f"Declarative skills not registered: {missing}"


def test_discover_builtin_skills_declarative_manifest_fields():
    """Registered declarative skills carry the correct manifest fields from SKILL.md."""
    registry = SkillRegistry()

    with patch.object(registry, "_publish_skill_promoted"):
        registry.discover_builtin_skills()

    web_fetch = registry.get("web-fetch")
    assert web_fetch is not None
    manifest = web_fetch.get_manifest()
    assert manifest.category == "internet"
    assert "fetch_url" in manifest.tools

    rss = registry.get("rss-reader")
    assert rss is not None
    rss_manifest = rss.get_manifest()
    assert "parse_feed" in rss_manifest.tools


def test_discover_builtin_skills_declarative_are_declarativeskill_instances():
    """SKILL.md-only builtins are registered as DeclarativeSkill instances."""
    registry = SkillRegistry()

    with patch.object(registry, "_publish_skill_promoted"):
        registry.discover_builtin_skills()

    for skill_id in _DECLARATIVE_SKILL_IDS:
        skill = registry.get(skill_id)
        assert skill is not None, f"Expected skill '{skill_id}' to be registered"
        assert isinstance(
            skill, DeclarativeSkill
        ), f"Expected '{skill_id}' to be a DeclarativeSkill, got {type(skill).__name__}"


def test_discover_builtin_skills_python_skills_still_registered():
    """Python-based builtins (e.g. code-review) are still registered alongside declarative ones."""
    registry = SkillRegistry()

    with patch.object(registry, "_publish_skill_promoted"):
        registry.discover_builtin_skills()

    registered_names = {info["name"] for info in registry.list_skills()}
    assert "code-review" in registered_names
    assert "skill-researcher" in registered_names


def test_discover_builtin_skills_research_bundle_all_registered():
    """All skills referenced by the research bundle are now in the registry."""
    from skills.bundles import get_bundle

    registry = SkillRegistry()

    with patch.object(registry, "_publish_skill_promoted"):
        registry.discover_builtin_skills()

    bundle = get_bundle("research")
    registered_names = {info["name"] for info in registry.list_skills()}
    missing = set(bundle.member_skill_ids) - registered_names
    assert not missing, f"Research bundle skills not registered: {missing}"
