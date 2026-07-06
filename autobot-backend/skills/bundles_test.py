# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for role-curated skill bundles (Issue #10540)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from skills.bundles import SkillBundle, enable_bundle, get_bundle, list_bundles

# ---------------------------------------------------------------------------
# list_bundles
# ---------------------------------------------------------------------------


def test_list_bundles_returns_three():
    """Exactly the 3 curated bundles are seeded."""
    bundles = list_bundles()
    assert len(bundles) == 3


def test_bundle_ids():
    """Bundle ids are 'research', 'engineering', 'knowledge'."""
    ids = {b.id for b in list_bundles()}
    assert ids == {"research", "engineering", "knowledge"}


def test_each_bundle_has_members():
    """Every bundle carries at least one member skill id."""
    for bundle in list_bundles():
        assert len(bundle.member_skill_ids) >= 1, f"Bundle '{bundle.id}' has no members"


def test_bundle_member_ids_are_kebab_case():
    """All member ids follow kebab-case (matching SkillManifest.name conventions)."""
    import re

    pattern = re.compile(r"^[a-z][a-z0-9-]*$")
    for bundle in list_bundles():
        for mid in bundle.member_skill_ids:
            assert pattern.match(mid), f"'{mid}' in bundle '{bundle.id}' is not kebab-case"


def test_research_bundle_contains_expected_skills():
    """Research bundle includes web-fetch, rss-reader, youtube-transcript, github-search, skill-researcher."""
    bundle = get_bundle("research")
    expected = {"web-fetch", "rss-reader", "youtube-transcript", "github-search", "skill-researcher"}
    assert expected.issubset(set(bundle.member_skill_ids))


def test_engineering_bundle_contains_expected_skills():
    """Engineering bundle includes code-review, autonomous-skill-development, skill-router."""
    bundle = get_bundle("engineering")
    expected = {"code-review", "autonomous-skill-development", "skill-router"}
    assert expected.issubset(set(bundle.member_skill_ids))


def test_knowledge_bundle_contains_expected_skills():
    """Knowledge bundle includes document-analysis, note-taking, calendar-integration."""
    bundle = get_bundle("knowledge")
    expected = {"document-analysis", "note-taking", "calendar-integration"}
    assert expected.issubset(set(bundle.member_skill_ids))


# ---------------------------------------------------------------------------
# get_bundle
# ---------------------------------------------------------------------------


def test_get_bundle_returns_correct_bundle():
    """get_bundle('research') returns the Research bundle."""
    bundle = get_bundle("research")
    assert isinstance(bundle, SkillBundle)
    assert bundle.id == "research"
    assert bundle.name == "Research"


def test_get_bundle_unknown_raises_value_error():
    """get_bundle raises ValueError for an unknown bundle id."""
    with pytest.raises(ValueError, match="Unknown bundle id 'nonexistent'"):
        get_bundle("nonexistent")


# ---------------------------------------------------------------------------
# enable_bundle
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


def _make_registry(skill_ids: list[str], fail_ids: list[str] | None = None) -> MagicMock:
    """Build a mock registry whose enable_skill succeeds for skill_ids."""
    fail_ids = fail_ids or []
    registry = MagicMock()

    def _enable(name: str):
        if name in fail_ids:
            return {"success": False, "error": f"dependency missing for {name}"}
        if name not in skill_ids:
            return {"success": False, "error": f"Skill '{name}' not found"}
        return {"success": True}

    registry.enable_skill.side_effect = _enable
    return registry


def _make_manager() -> MagicMock:
    manager = MagicMock()
    manager.persist_skill_enabled = AsyncMock(return_value=True)
    return manager


@pytest.mark.anyio
async def test_enable_bundle_calls_enable_for_each_member():
    """enable_bundle calls registry.enable_skill once per member skill."""
    bundle = get_bundle("research")
    registry = _make_registry(bundle.member_skill_ids)
    manager = _make_manager()

    result = await enable_bundle("research", registry=registry, manager=manager)

    assert result["bundle_id"] == "research"
    assert set(result["enabled"]) == set(bundle.member_skill_ids)
    assert result["skipped"] == []
    assert result["failed"] == {}
    assert registry.enable_skill.call_count == len(bundle.member_skill_ids)


@pytest.mark.anyio
async def test_enable_bundle_persists_each_enabled_skill():
    """enable_bundle calls manager.persist_skill_enabled for every successfully enabled skill."""
    bundle = get_bundle("engineering")
    registry = _make_registry(bundle.member_skill_ids)
    manager = _make_manager()

    await enable_bundle("engineering", registry=registry, manager=manager)

    assert manager.persist_skill_enabled.call_count == len(bundle.member_skill_ids)
    persisted = {call.args[0] for call in manager.persist_skill_enabled.call_args_list}
    assert persisted == set(bundle.member_skill_ids)


@pytest.mark.anyio
async def test_enable_bundle_skips_unregistered_skills():
    """Skills absent from the registry are reported in 'skipped', not 'failed'."""
    # Only provide 2 of the 3 knowledge skills in the mock registry
    partial_ids = ["document-analysis", "note-taking"]
    registry = _make_registry(partial_ids)
    manager = _make_manager()

    result = await enable_bundle("knowledge", registry=registry, manager=manager)

    assert set(result["enabled"]) == set(partial_ids)
    assert "calendar-integration" in result["skipped"]
    assert result["failed"] == {}


@pytest.mark.anyio
async def test_enable_bundle_records_non_notfound_failures():
    """Dependency failures are reported in 'failed', not 'skipped'."""
    bundle = get_bundle("engineering")
    # code-review will fail with a dependency error (not "not found")
    registry = _make_registry(bundle.member_skill_ids, fail_ids=["code-review"])
    manager = _make_manager()

    result = await enable_bundle("engineering", registry=registry, manager=manager)

    assert "code-review" in result["failed"]
    assert "code-review" not in result["enabled"]
    assert "code-review" not in result["skipped"]


@pytest.mark.anyio
async def test_enable_bundle_unknown_id_raises():
    """enable_bundle raises ValueError for an unknown bundle id."""
    registry = _make_registry([])
    manager = _make_manager()

    with pytest.raises(ValueError, match="Unknown bundle id 'bogus'"):
        await enable_bundle("bogus", registry=registry, manager=manager)
