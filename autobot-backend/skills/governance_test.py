# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the Governance Engine and Skill Promoter (Phase 6)."""
import os
import tempfile

import pytest
from skills.governance import GovernanceEngine
from skills.models import GovernanceMode
from skills.promoter import SkillPromoter

VALID_SKILL_MD = (
    "---\nname: test-skill\nversion: 1.0.0\n"
    "description: Test skill\ntools: [do_x]\n---\n# Test\n"
)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


@pytest.mark.anyio
async def test_full_auto_skips_approval():
    """FULL_AUTO mode approves immediately without human review."""
    engine = GovernanceEngine(mode=GovernanceMode.FULL_AUTO)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert result.approved
    assert result.requires_human_review is False


@pytest.mark.anyio
async def test_semi_auto_requires_review():
    """SEMI_AUTO mode creates a pending approval requiring human review."""
    engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert not result.approved
    assert result.requires_human_review is True
    assert result.approval_id is not None


@pytest.mark.anyio
async def test_locked_blocks_self_generation():
    """LOCKED mode blocks all self-generated skill activations."""
    engine = GovernanceEngine(mode=GovernanceMode.LOCKED)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert not result.approved
    assert result.requires_human_review is False
    assert "locked" in result.reason.lower()


@pytest.mark.anyio
async def test_approve_returns_approved_result():
    """GovernanceEngine.approve() returns an approved ActivationResult."""
    engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
    result = await engine.approve("appr-123", "admin@example.com")
    assert result.approved
    assert "admin@example.com" in result.reason


@pytest.mark.anyio
async def test_promoter_writes_skill_files():
    """SkillPromoter writes SKILL.md and skill.py to the destination directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        promoter = SkillPromoter(skills_base_dir=tmpdir)
        dest = await promoter.promote(
            name="test-skill",
            skill_md=VALID_SKILL_MD,
            skill_py="# placeholder",
            auto_commit=False,
        )
        assert os.path.exists(os.path.join(dest, "SKILL.md"))
        assert os.path.exists(os.path.join(dest, "skill.py"))
        with open(os.path.join(dest, "SKILL.md"), encoding="utf-8") as f:
            assert "test-skill" in f.read()
