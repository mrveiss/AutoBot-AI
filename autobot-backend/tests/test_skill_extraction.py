# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for autonomous skill extraction from conversations.

Test coverage:
- Pattern detection (workflow, multi-step)
- LLM extraction with confidence filtering
- Skill validation and syntax checks
- SLM proposal API integration
- Post-completion hook integration

Related Issue: #4338
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conversation_context import ConversationContextAnalyzer
from services.skill_management.skill_extractor import (
    ExtractedSkill,
    SkillExtractor,
)
from services.skill_management.skill_proposer import SkillProposer

# Sample conversation with multi-step workflow
SAMPLE_WORKFLOW_CONVERSATION = [
    {
        "role": "user",
        "content": "I need to create a backup script that runs daily",
    },
    {
        "role": "assistant",
        "content": ("I'll help you create a daily backup script. " "First, I'll create the script file."),
    },
    {
        "role": "assistant",
        "content": "Script created at /opt/backup.sh. Next, I'll set up the cron job.",
    },
    {
        "role": "assistant",
        "content": ("Cron job configured for 2 AM daily. " "Finally, let me verify the setup."),
    },
    {
        "role": "assistant",
        "content": "Done! Backup is now scheduled for 2 AM daily.",
    },
]

# Short conversation without workflow patterns
SHORT_CONVERSATION = [
    {"role": "user", "content": "Hi, how are you?"},
    {"role": "assistant", "content": "I'm doing well, thanks for asking!"},
]

# LLM extraction response
MOCK_EXTRACTION_RESPONSE = {
    "content": json.dumps(
        [
            {
                "name": "create_daily_backup",
                "description": "Create and schedule a daily backup job",
                "inputs": [
                    {"name": "source_path", "type": "string"},
                    {"name": "backup_time", "type": "string"},
                ],
                "outputs": [
                    {"name": "success", "type": "boolean"},
                    {"name": "cron_job_id", "type": "string"},
                ],
                "procedure": "1. Create backup script\n2. Set up cron job\n3. Verify setup",
                "preconditions": ["Root access", "cron installed"],
                "edge_cases": [
                    "If cron fails, check permissions",
                    "If script not writable, fix ownership",
                ],
                "confidence": 0.95,
            },
            {
                "name": "low_confidence_skill",
                "description": "A low confidence skill",
                "inputs": [],
                "outputs": [],
                "procedure": "Do something",
                "preconditions": [],
                "edge_cases": [],
                "confidence": 0.3,  # Below threshold
            },
        ]
    )
}


class TestSkillExtractor:
    """Tests for SkillExtractor class."""

    def test_has_workflow_patterns_detects_multi_step(self):
        """Test detection of multi-step workflow patterns."""
        extractor = SkillExtractor()

        has_patterns = extractor._has_workflow_patterns(SAMPLE_WORKFLOW_CONVERSATION)
        assert has_patterns is True

    def test_has_workflow_patterns_rejects_simple_chat(self):
        """Test that simple chat doesn't trigger workflow detection."""
        extractor = SkillExtractor()

        has_patterns = extractor._has_workflow_patterns(SHORT_CONVERSATION)
        assert has_patterns is False

    @pytest.mark.asyncio
    async def test_extract_skills_insufficient_history(self):
        """Test that extraction skips short conversations."""
        extractor = SkillExtractor()

        skills = await extractor.extract_skills(SHORT_CONVERSATION)
        assert skills == []

    @pytest.mark.asyncio
    async def test_extract_skills_no_patterns(self):
        """Test that extraction skips conversations without workflow patterns."""
        extractor = SkillExtractor()

        no_pattern_conversation = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
            {"role": "user", "content": "Tell me more."},
            {"role": "assistant", "content": "It's used for scripting and web development."},
        ]

        skills = await extractor.extract_skills(no_pattern_conversation)
        assert skills == []

    @pytest.mark.asyncio
    async def test_extract_skills_success(self):
        """Test successful skill extraction from conversation."""
        with patch("services.skill_management.skill_extractor.AIStackClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance
            mock_instance.call = AsyncMock(return_value=MOCK_EXTRACTION_RESPONSE)

            extractor = SkillExtractor(ai_stack_client=mock_instance)
            skills = await extractor.extract_skills(SAMPLE_WORKFLOW_CONVERSATION)

            # Should have 1 skill (high confidence only)
            assert len(skills) == 1
            assert skills[0].name == "create_daily_backup"
            assert skills[0].confidence == 0.95

    def test_build_extraction_prompt_includes_history(self):
        """Test that prompt building includes conversation context."""
        extractor = SkillExtractor()

        prompt = extractor._build_extraction_prompt(SAMPLE_WORKFLOW_CONVERSATION)

        assert "create a backup script" in prompt
        assert "cron job" in prompt
        assert "confidence" in prompt.lower()

    def test_parse_extraction_response_valid(self):
        """Test parsing valid LLM response."""
        extractor = SkillExtractor()

        skill_data = json.loads(MOCK_EXTRACTION_RESPONSE["content"])
        skills = extractor._parse_extraction_response(skill_data)

        assert len(skills) == 2
        assert skills[0].name == "create_daily_backup"
        assert skills[0].confidence == 0.95
        assert len(skills[0].inputs) == 2
        assert len(skills[0].outputs) == 2

    def test_parse_extraction_response_malformed(self):
        """Test handling of malformed LLM response."""
        extractor = SkillExtractor()

        # Missing required fields
        malformed = [
            {"name": "skill_name"},  # Missing description, procedure, etc.
        ]

        skills = extractor._parse_extraction_response(malformed)
        assert len(skills) == 0

    def test_parse_extraction_response_with_array_wrapper(self):
        """Test parsing response wrapped in object."""
        extractor = SkillExtractor()

        wrapped_response = {
            "skills": [
                {
                    "name": "test_skill",
                    "description": "Test skill",
                    "inputs": [],
                    "outputs": [],
                    "procedure": "Do something",
                    "preconditions": [],
                    "edge_cases": [],
                    "confidence": 0.8,
                }
            ]
        }

        skills = extractor._parse_extraction_response(wrapped_response)
        assert len(skills) == 1
        assert skills[0].name == "test_skill"


class TestExtractedSkill:
    """Tests for ExtractedSkill dataclass."""

    def test_extracted_skill_to_dict(self):
        """Test skill serialization to dict."""
        skill = ExtractedSkill(
            name="test_skill",
            description="A test skill",
            inputs=[{"name": "x", "type": "int"}],
            outputs=[{"name": "y", "type": "int"}],
            procedure="Double the input",
            preconditions=["Input must be positive"],
            edge_cases=["If negative, return error"],
            confidence=0.9,
        )

        skill_dict = skill.to_dict()

        assert skill_dict["name"] == "test_skill"
        assert skill_dict["description"] == "A test skill"
        assert skill_dict["confidence"] == 0.9
        assert len(skill_dict["inputs"]) == 1


class TestSkillProposer:
    """Tests for SkillProposer class."""

    @pytest.mark.asyncio
    async def test_propose_skills_empty_list(self):
        """Test proposing empty skill list."""
        proposer = SkillProposer()

        result = await proposer.propose_skills([], "session_123")

        assert result == {"proposed": []}

    @pytest.mark.asyncio
    async def test_propose_skills_success(self):
        """Test successful skill proposal."""
        skill = ExtractedSkill(
            name="test_skill",
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test procedure",
            preconditions=[],
            edge_cases=[],
            confidence=0.9,
        )

        with patch.object(SkillProposer, "_propose_single_skill") as mock_propose:
            mock_propose.return_value = True

            proposer = SkillProposer()
            result = await proposer.propose_skills([skill], "session_123")

            assert result == {"proposed": ["test_skill"]}

    @pytest.mark.asyncio
    async def test_propose_single_skill_accepted(self):
        """Test proposal acceptance."""
        skill = ExtractedSkill(
            name="test_skill",
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test",
            preconditions=[],
            edge_cases=[],
            confidence=0.9,
        )

        with patch.object(SkillProposer, "_send_proposal_to_slm") as mock_send:
            mock_send.return_value = {"status": "accepted"}

            proposer = SkillProposer()
            result = await proposer._propose_single_skill(skill, "session_123")

            assert result is True

    @pytest.mark.asyncio
    async def test_propose_single_skill_rejected(self):
        """Test proposal rejection."""
        skill = ExtractedSkill(
            name="test_skill",
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test",
            preconditions=[],
            edge_cases=[],
            confidence=0.9,
        )

        with patch.object(SkillProposer, "_send_proposal_to_slm") as mock_send:
            mock_send.return_value = {"status": "rejected", "reason": "Invalid syntax"}

            proposer = SkillProposer()
            result = await proposer._propose_single_skill(skill, "session_123")

            assert result is False

    @pytest.mark.asyncio
    async def test_validate_skill_syntax_valid(self):
        """Test validation of valid skill."""
        skill = ExtractedSkill(
            name="valid_skill",
            description="Valid test skill",
            inputs=[{"name": "x", "type": "string"}],
            outputs=[{"name": "y", "type": "string"}],
            procedure="Do something with x",
            preconditions=["Input not empty"],
            edge_cases=["If empty, skip"],
            confidence=0.85,
        )

        proposer = SkillProposer()
        result = await proposer.validate_skill_syntax(skill)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_skill_syntax_missing_name(self):
        """Test validation rejects skill with missing name."""
        skill = ExtractedSkill(
            name="",
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test",
            preconditions=[],
            edge_cases=[],
            confidence=0.9,
        )

        proposer = SkillProposer()
        result = await proposer.validate_skill_syntax(skill)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_skill_syntax_invalid_name(self):
        """Test validation rejects invalid skill name."""
        skill = ExtractedSkill(
            name="invalid-skill-name!",  # Invalid identifier
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test",
            preconditions=[],
            edge_cases=[],
            confidence=0.9,
        )

        proposer = SkillProposer()
        result = await proposer.validate_skill_syntax(skill)

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_skill_syntax_invalid_confidence(self):
        """Test validation rejects invalid confidence."""
        skill = ExtractedSkill(
            name="test_skill",
            description="Test",
            inputs=[],
            outputs=[],
            procedure="Test",
            preconditions=[],
            edge_cases=[],
            confidence=1.5,  # Invalid
        )

        proposer = SkillProposer()
        result = await proposer.validate_skill_syntax(skill)

        assert result is False


class TestConversationContextAnalyzer:
    """Tests for ConversationContextAnalyzer skill extraction integration."""

    def test_analyzer_with_completion_hook(self):
        """Test analyzer initialization with completion hook."""
        callback = MagicMock()

        analyzer = ConversationContextAnalyzer(on_conversation_complete=callback)

        assert analyzer.on_conversation_complete is callback

    @pytest.mark.asyncio
    async def test_trigger_skill_extraction_async(self):
        """Test triggering async skill extraction."""
        callback = AsyncMock()

        analyzer = ConversationContextAnalyzer(on_conversation_complete=callback)
        analyzer.trigger_skill_extraction_async("session_123", SAMPLE_WORKFLOW_CONVERSATION)

        # Give event loop time to process
        await asyncio.sleep(0.1)

        # Callback should be enqueued (but not awaited)
        # In real usage, the callback would execute asynchronously

    def test_trigger_skill_extraction_no_callback(self):
        """Test that trigger silently succeeds without callback."""
        analyzer = ConversationContextAnalyzer()

        # Should not raise
        analyzer.trigger_skill_extraction_async("session_123", SAMPLE_WORKFLOW_CONVERSATION)


class TestSkillIntegration:
    """Integration tests for full extraction → proposal workflow."""

    @pytest.mark.asyncio
    async def test_full_extraction_proposal_flow(self):
        """Test complete extraction and proposal flow."""
        with (
            patch("services.skill_management.skill_extractor.AIStackClient") as mock_ai,
            patch("services.skill_management.skill_proposer.SkillProposer._send_proposal_to_slm") as mock_slm,
        ):

            # Mock AI stack extraction
            mock_ai_instance = AsyncMock()
            mock_ai.return_value = mock_ai_instance
            mock_ai_instance.call = AsyncMock(return_value=MOCK_EXTRACTION_RESPONSE)

            # Mock SLM proposal
            mock_slm.return_value = {"status": "accepted"}

            # Extract skills
            extractor = SkillExtractor(ai_stack_client=mock_ai_instance)
            skills = await extractor.extract_skills(SAMPLE_WORKFLOW_CONVERSATION)

            assert len(skills) == 1

            # Propose skills
            proposer = SkillProposer()
            result = await proposer.propose_skills(skills, "session_123")

            assert len(result["proposed"]) == 1
            assert result["proposed"][0] == "create_daily_backup"
