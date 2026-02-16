"""
Tests for WorkflowStepJudge

Tests workflow step evaluation, approval logic, and integration with workflow systems.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from judges import JudgmentConfidence, JudgmentDimension, JudgmentResult
from backend.judges.workflow_step_judge import WorkflowStepJudge


class TestWorkflowStepJudge:
    """Test suite for WorkflowStepJudge"""

    @pytest.fixture
    def judge(self):
        """Create a WorkflowStepJudge instance for testing"""
        # Mock the LLM interface to avoid actual API calls
        mock_llm = AsyncMock()
        judge = WorkflowStepJudge(llm_interface=mock_llm)
        return judge

    @pytest.fixture
    def sample_step_data(self):
        """Sample workflow step data for testing"""
        return {
            "step_id": "test_step",
            "command": "echo 'hello world'",
            "description": "Test echo command",
            "explanation": "Simple test command for validation",
            "risk_level": "low",
            "estimated_duration": 1.0,
            "dependencies": [],
        }

    @pytest.fixture
    def sample_workflow_context(self):
        """Sample workflow context for testing"""
        return {
            "workflow_name": "Test Workflow",
            "workflow_description": "A test workflow",
            "current_step_index": 0,
            "total_steps": 3,
            "completed_steps": [],
            "automation_mode": "semi_automatic",
        }

    @pytest.fixture
    def sample_user_context(self):
        """Sample user context for testing"""
        return {
            "permissions": ["user"],
            "experience_level": "intermediate",
            "environment": "development",
        }

    @pytest.mark.asyncio
    async def test_evaluate_safe_step(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test evaluation of a safe workflow step"""
        # Mock successful LLM response
        mock_response = {
            "overall_score": 0.9,
            "recommendation": "APPROVE",
            "confidence": "high",
            "reasoning": "Safe echo command with no risks",
            "criterion_scores": [
                {
                    "dimension": "safety",
                    "score": 0.95,
                    "confidence": "high",
                    "reasoning": "Echo command is safe",
                    "evidence": ["Non-destructive command", "No system modifications"],
                },
                {
                    "dimension": "quality",
                    "score": 0.85,
                    "confidence": "high",
                    "reasoning": "Command will execute successfully",
                    "evidence": ["Standard shell command", "Simple syntax"],
                },
            ],
            "improvement_suggestions": [],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        # Test evaluation
        result = await judge.evaluate_workflow_step(
            sample_step_data, sample_workflow_context, sample_user_context
        )

        assert isinstance(result, JudgmentResult)
        assert result.overall_score == 0.9
        assert result.recommendation == "APPROVE"
        assert result.confidence == JudgmentConfidence.HIGH
        assert len(result.criterion_scores) == 2

        # Verify LLM interface was called
        judge.llm_interface.chat_completion_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_risky_step(
        self, judge, sample_workflow_context, sample_user_context
    ):
        """Test evaluation of a risky workflow step"""
        risky_step_data = {
            "step_id": "risky_step",
            "command": "sudo rm -rf /tmp/cache",
            "description": "Clear temporary cache",
            "risk_level": "high",
        }

        # Mock LLM response for risky command
        mock_response = {
            "overall_score": 0.4,
            "recommendation": "CONDITIONAL",
            "confidence": "medium",
            "reasoning": "Command has deletion risk but targets safe directory",
            "criterion_scores": [
                {
                    "dimension": "safety",
                    "score": 0.6,
                    "confidence": "medium",
                    "reasoning": "Deletion command with potential risks",
                    "evidence": ["Uses rm -rf", "Requires sudo"],
                }
            ],
            "improvement_suggestions": [
                "Consider using safer deletion methods",
                "Add confirmation before execution",
            ],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        result = await judge.evaluate_workflow_step(
            risky_step_data, sample_workflow_context, sample_user_context
        )

        assert result.overall_score == 0.4
        assert result.recommendation == "CONDITIONAL"
        assert len(result.improvement_suggestions) == 2

    @pytest.mark.asyncio
    async def test_should_approve_step_safe(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test approval logic for safe step"""
        # Mock safe evaluation response
        mock_response = {
            "overall_score": 0.9,
            "recommendation": "APPROVE",
            "confidence": "high",
            "reasoning": "Safe command",
            "criterion_scores": [
                {
                    "dimension": "safety",
                    "score": 0.9,
                    "confidence": "high",
                    "reasoning": "Safe command",
                    "evidence": [],
                },
                {
                    "dimension": "quality",
                    "score": 0.85,
                    "confidence": "high",
                    "reasoning": "Good quality",
                    "evidence": [],
                },
            ],
            "improvement_suggestions": [],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        should_approve, reason = await judge.should_approve_step(
            sample_step_data, sample_workflow_context, sample_user_context
        )

        assert should_approve is True
        assert "Approved" in reason

    @pytest.mark.asyncio
    async def test_should_approve_step_unsafe(
        self, judge, sample_workflow_context, sample_user_context
    ):
        """Test approval logic for unsafe step"""
        unsafe_step_data = {
            "step_id": "unsafe_step",
            "command": "rm -rf /",
            "description": "Dangerous command",
            "risk_level": "critical",
        }

        # Mock unsafe evaluation response
        mock_response = {
            "overall_score": 0.1,
            "recommendation": "REJECT",
            "confidence": "very_high",
            "reasoning": "Extremely dangerous command that could destroy the system",
            "criterion_scores": [
                {
                    "dimension": "safety",
                    "score": 0.05,
                    "confidence": "very_high",
                    "reasoning": "Destructive system command",
                    "evidence": [],
                },
                {
                    "dimension": "quality",
                    "score": 0.2,
                    "confidence": "high",
                    "reasoning": "Command would execute but cause damage",
                    "evidence": [],
                },
            ],
            "improvement_suggestions": [
                "Never use this command",
                "Find alternative approach",
            ],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        should_approve, reason = await judge.should_approve_step(
            unsafe_step_data, sample_workflow_context, sample_user_context
        )

        assert should_approve is False
        assert "Safety score" in reason

    @pytest.mark.asyncio
    async def test_suggest_improvements(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test improvement suggestion functionality"""
        mock_response = {
            "overall_score": 0.7,
            "recommendation": "CONDITIONAL",
            "confidence": "medium",
            "reasoning": "Command could be improved",
            "criterion_scores": [],
            "improvement_suggestions": [
                "Add error handling",
                "Include progress feedback",
                "Validate input parameters",
            ],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        suggestions = await judge.suggest_improvements(
            sample_step_data, sample_workflow_context, sample_user_context
        )

        assert len(suggestions) == 3
        assert "Add error handling" in suggestions
        assert "Include progress feedback" in suggestions

    @pytest.mark.asyncio
    async def test_compare_alternatives(
        self, judge, sample_workflow_context, sample_user_context
    ):
        """Test comparison of alternative workflow steps"""
        primary_step = {
            "step_id": "primary",
            "command": "apt install package",
            "description": "Install via apt",
        }

        alternatives = [
            {
                "step_id": "alt1",
                "command": "snap install package",
                "description": "Install via snap",
            },
            {
                "step_id": "alt2",
                "command": "pip install package",
                "description": "Install via pip",
            },
        ]

        # Mock responses for each evaluation
        def mock_response_generator(call_count=[0]):
            responses = [
                # Primary step response
                {
                    "overall_score": 0.8,
                    "recommendation": "APPROVE",
                    "confidence": "high",
                    "reasoning": "Standard package manager",
                    "criterion_scores": [],
                    "improvement_suggestions": [],
                },
                # Alternative 1 response
                {
                    "overall_score": 0.75,
                    "recommendation": "APPROVE",
                    "confidence": "medium",
                    "reasoning": "Snap package manager",
                    "criterion_scores": [],
                    "improvement_suggestions": [],
                },
                # Alternative 2 response
                {
                    "overall_score": 0.6,
                    "recommendation": "CONDITIONAL",
                    "confidence": "medium",
                    "reasoning": "Python package manager",
                    "criterion_scores": [],
                    "improvement_suggestions": [],
                },
            ]
            result = responses[call_count[0]]
            call_count[0] += 1
            return result

        judge.llm_interface.chat_completion_async.side_effect = mock_response_generator

        comparison = await judge.compare_alternatives(
            primary_step, alternatives, sample_workflow_context, sample_user_context
        )

        assert comparison["best_option"]["evaluation"].overall_score == 0.8
        assert len(comparison["all_evaluations"]) == 3
        assert comparison["recommendation"] == "APPROVE"

    @pytest.mark.asyncio
    async def test_error_handling(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test error handling in evaluation"""
        # Mock LLM interface to raise an exception
        judge.llm_interface.chat_completion_async.side_effect = Exception(
            "LLM API error"
        )

        should_approve, reason = await judge.should_approve_step(
            sample_step_data, sample_workflow_context, sample_user_context
        )

        assert should_approve is False
        assert "Evaluation error" in reason

    def test_system_prompt_generation(self, judge):
        """Test system prompt generation"""
        system_prompt = judge._get_system_prompt()

        assert "workflow step evaluation" in system_prompt.lower()
        assert "safety" in system_prompt.lower()
        assert "json" in system_prompt.lower()
        assert len(system_prompt) > 500  # Should be comprehensive

    @pytest.mark.asyncio
    async def test_judgment_logging(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test that judgments are logged correctly"""
        mock_response = {
            "overall_score": 0.8,
            "recommendation": "APPROVE",
            "confidence": "high",
            "reasoning": "Test reasoning",
            "criterion_scores": [],
            "improvement_suggestions": [],
        }

        judge.llm_interface.chat_completion_async.return_value = mock_response

        # Evaluate step
        await judge.evaluate_workflow_step(
            sample_step_data, sample_workflow_context, sample_user_context
        )

        # Check that judgment was stored
        assert len(judge.judgment_history) == 1
        assert judge.judgment_history[0].overall_score == 0.8

    def test_performance_metrics(self, judge):
        """Test performance metrics calculation"""
        # Add some mock judgments to history
        mock_judgment1 = MagicMock()
        mock_judgment1.overall_score = 0.8
        mock_judgment1.recommendation = "APPROVE"
        mock_judgment1.confidence = JudgmentConfidence.HIGH
        mock_judgment1.processing_time_ms = 150.0

        mock_judgment2 = MagicMock()
        mock_judgment2.overall_score = 0.6
        mock_judgment2.recommendation = "CONDITIONAL"
        mock_judgment2.confidence = JudgmentConfidence.MEDIUM
        mock_judgment2.processing_time_ms = 200.0

        judge.judgment_history = [mock_judgment1, mock_judgment2]

        metrics = judge.get_performance_metrics()

        assert metrics["total_judgments"] == 2
        assert metrics["average_score"] == 0.7
        assert metrics["average_processing_time_ms"] == 175.0
        assert metrics["recommendation_distribution"]["APPROVE"] == 1
        assert metrics["recommendation_distribution"]["CONDITIONAL"] == 1

    def test_confidence_levels(self, judge):
        """Test confidence level calculation"""
        # Test different confidence scenarios
        mock_judgments = []

        # Add judgments with different confidence levels
        for confidence in [
            JudgmentConfidence.HIGH,
            JudgmentConfidence.MEDIUM,
            JudgmentConfidence.HIGH,
        ]:
            mock_judgment = MagicMock()
            mock_judgment.confidence = confidence
            mock_judgment.overall_score = 0.8
            mock_judgment.recommendation = "APPROVE"
            mock_judgment.processing_time_ms = 100.0
            mock_judgments.append(mock_judgment)

        judge.judgment_history = mock_judgments

        avg_confidence = judge._average_confidence()
        assert avg_confidence in ["low", "medium", "high", "very_low", "very_high"]

    @pytest.mark.asyncio
    async def test_prompt_preparation(
        self, judge, sample_step_data, sample_workflow_context, sample_user_context
    ):
        """Test judgment prompt preparation"""
        criteria = [JudgmentDimension.SAFETY, JudgmentDimension.QUALITY]
        context = {
            "workflow_context": sample_workflow_context,
            "user_context": sample_user_context,
            "risk_tolerance": "medium",
        }

        prompt = await judge._prepare_judgment_prompt(
            sample_step_data, criteria, context
        )

        assert "workflow step" in prompt.lower()
        assert "safety" in prompt.lower()
        assert "quality" in prompt.lower()
        assert sample_step_data["command"] in prompt
        assert len(prompt) > 1000  # Should be comprehensive
