# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the Autonomous Skill Development builtin skill (Issue #951)."""
from unittest.mock import AsyncMock, patch

import pytest
from skills.builtin.autonomous_skill_development import (
    AutonomousSkillDevelopmentSkill,
    _get_governance_mode,
    _run_development_pipeline,
)


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only."""
    return "asyncio"


class TestManifest:
    def test_name_and_category(self):
        manifest = AutonomousSkillDevelopmentSkill.get_manifest()
        assert manifest.name == "autonomous-skill-development"
        assert manifest.category == "self-improvement"

    def test_has_tools_and_triggers(self):
        manifest = AutonomousSkillDevelopmentSkill.get_manifest()
        assert "trigger_gap_development" in manifest.tools
        assert "agent_capability_gap" in manifest.triggers

    def test_self_improvement_tags(self):
        manifest = AutonomousSkillDevelopmentSkill.get_manifest()
        assert "governance" in manifest.tags


class TestExecute:
    @pytest.mark.anyio
    async def test_empty_capability_returns_error(self):
        skill = AutonomousSkillDevelopmentSkill()
        result = await skill.execute({"capability": ""})
        assert result["success"] is False
        assert "required" in result["message"]

    @pytest.mark.anyio
    async def test_locked_mode_returns_locked_state(self):
        skill = AutonomousSkillDevelopmentSkill()
        with patch(
            "skills.builtin.autonomous_skill_development._get_governance_mode",
            new=AsyncMock(return_value="locked"),
        ):
            result = await skill.execute({"capability": "process audio"})
        assert result["success"] is False
        assert result["state"] == "locked"

    @pytest.mark.anyio
    async def test_semi_auto_returns_pending_state(self):
        skill = AutonomousSkillDevelopmentSkill()
        fake_pkg = {
            "name": "audio-processor",
            "skill_md": "---\nname: audio-processor\n---\n",
            "skill_py": "# stub",
            "manifest": {"name": "audio-processor"},
            "gap_description": "process audio",
        }
        with patch(
            "skills.builtin.autonomous_skill_development._get_governance_mode",
            new=AsyncMock(return_value="semi_auto"),
        ):
            with patch(
                "skills.builtin.autonomous_skill_development._run_development_pipeline",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "state": "pending_approval",
                        "skill_name": "audio-processor",
                        "skill_id": "abc",
                        "approval_id": "appr-123",
                        "message": "queued",
                    }
                ),
            ):
                result = await skill.execute({"capability": "process audio"})
        assert result["success"] is True
        assert result["state"] == "pending_approval"

    @pytest.mark.anyio
    async def test_full_auto_returns_promoted_state(self):
        skill = AutonomousSkillDevelopmentSkill()
        with patch(
            "skills.builtin.autonomous_skill_development._get_governance_mode",
            new=AsyncMock(return_value="full_auto"),
        ):
            with patch(
                "skills.builtin.autonomous_skill_development._run_development_pipeline",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "state": "promoted",
                        "skill_name": "audio-processor",
                        "skill_id": "abc",
                        "message": "activated",
                    }
                ),
            ):
                result = await skill.execute({"capability": "process audio"})
        assert result["success"] is True
        assert result["state"] == "promoted"


class TestGetGovernanceMode:
    @pytest.mark.anyio
    async def test_returns_semi_auto_on_db_failure(self):
        # get_skills_engine is imported locally; patch at source module level
        with patch("skills.db.get_skills_engine", side_effect=RuntimeError("no db")):
            mode = await _get_governance_mode()
        assert mode == "semi_auto"


class TestRunDevelopmentPipeline:
    @pytest.mark.anyio
    async def test_returns_error_on_generation_failure(self):
        # SkillGenerator imported locally in _run_development_pipeline
        with patch("skills.generator.SkillGenerator") as MockGen:
            MockGen.return_value.generate = AsyncMock(
                side_effect=RuntimeError("LLM down")
            )
            result = await _run_development_pipeline(
                "some capability", "bot", "semi_auto"
            )
        assert result["success"] is False
        assert result["state"] == "generation_failed"

    @pytest.mark.anyio
    async def test_semi_auto_does_not_call_promote(self):
        fake_pkg = {
            "name": "new-skill",
            "skill_md": "---\nname: new-skill\n---\n",
            "skill_py": None,
            "manifest": {},
            "gap_description": "cap",
        }
        with patch("skills.generator.SkillGenerator") as MockGen:
            MockGen.return_value.generate = AsyncMock(return_value=fake_pkg)
            with patch(
                "skills.builtin.autonomous_skill_development._save_draft",
                new=AsyncMock(return_value="draft-id"),
            ):
                with patch(
                    "skills.builtin.autonomous_skill_development._request_governance",
                    new=AsyncMock(return_value="appr-1"),
                ):
                    with patch(
                        "skills.builtin.autonomous_skill_development._promote_and_reload",
                        new=AsyncMock(return_value=True),
                    ) as mock_promote:
                        result = await _run_development_pipeline(
                            "capability", "bot", "semi_auto"
                        )
        mock_promote.assert_not_called()
        assert result["state"] == "pending_approval"
