# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the Governance Engine and Skill Promoter (Phase 6 / Issue #951)."""
import os
import tempfile
from unittest.mock import AsyncMock, patch

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
async def test_semi_auto_persists_approval_to_db():
    """SEMI_AUTO mode should persist a SkillApproval row to DB (Issue #951)."""
    with patch(
        "skills.governance._persist_approval", new_callable=AsyncMock
    ) as mock_persist:
        with patch(
            "skills.governance.GovernanceEngine._notify_admin", new_callable=AsyncMock
        ):
            engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
            result = await engine.request_activation(
                "gap-skill", "autobot-self", "needs capability X", skill_id="skill-123"
            )
    mock_persist.assert_called_once()
    call_args = mock_persist.call_args[0]
    assert call_args[1] == "skill-123"  # resolved skill_id passed through
    assert call_args[2] == "autobot-self"
    assert result.requires_human_review is True


@pytest.mark.anyio
async def test_semi_auto_uses_skill_name_when_no_skill_id():
    """When skill_id is omitted, skill_name is used as the approval skill_id."""
    with patch(
        "skills.governance._persist_approval", new_callable=AsyncMock
    ) as mock_persist:
        with patch(
            "skills.governance.GovernanceEngine._notify_admin", new_callable=AsyncMock
        ):
            engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
            await engine.request_activation("my-skill", "autobot-self", "reason")
    call_args = mock_persist.call_args[0]
    assert call_args[1] == "my-skill"  # falls back to skill_name


@pytest.mark.anyio
async def test_full_auto_does_not_persist_approval():
    """FULL_AUTO mode skips DB persistence (no human review needed)."""
    with patch(
        "skills.governance._persist_approval", new_callable=AsyncMock
    ) as mock_persist:
        engine = GovernanceEngine(mode=GovernanceMode.FULL_AUTO)
        await engine.request_activation("auto-skill", "autobot-self", "auto")
    mock_persist.assert_not_called()


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
