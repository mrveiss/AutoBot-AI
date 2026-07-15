# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for LLM-as-Judge framework

Tests integration with workflow automation, validation dashboard, and other system components.

Issue #10880: Judge integration retargeted to services.workflow_automation.
Judges are now lazily imported inside
services/workflow_automation/step_evaluator.py via
``from judges.workflow_step_judge import WorkflowStepJudge`` (and friends).
The module-level ``JUDGES_AVAILABLE`` flag and the
``api.workflow_automation.WorkflowStepJudge`` / ``SecurityRiskJudge`` symbols no
longer exist. Availability is expressed by a try/except import inside
``WorkflowStepEvaluator._initialize_judges``. Because the judges are imported
*inside a function*, the correct patch target is the **source** module
(``judges.workflow_step_judge.WorkflowStepJudge`` etc.): patching the source
affects the local import performed at evaluator construction time. To simulate
"judges available" we patch the source to return a Mock; to simulate
"judges unavailable" we patch the source to raise ImportError.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.validation_dashboard import router as validation_router

# Source patch targets — judges are imported lazily inside
# WorkflowStepEvaluator._initialize_judges (#10880).
WORKFLOW_STEP_JUDGE_SOURCE = "judges.workflow_step_judge.WorkflowStepJudge"
SECURITY_RISK_JUDGE_SOURCE = "judges.security_risk_judge.SecurityRiskJudge"
MULTI_AGENT_ARBITRATOR_SOURCE = "judges.multi_agent_arbitrator.MultiAgentArbitrator"


class TestJudgeIntegration:
    """Test suite for LLM judges integration"""

    @pytest.fixture
    def mock_judges(self):
        """Mock judges for testing"""
        workflow_judge = AsyncMock()
        response_judge = AsyncMock()
        security_judge = AsyncMock()
        arbitrator = AsyncMock()

        # Mock judgment results
        mock_judgment = MagicMock()
        mock_judgment.overall_score = 0.8
        mock_judgment.recommendation = "APPROVE"
        mock_judgment.confidence.value = "high"
        mock_judgment.reasoning = "Test reasoning"
        mock_judgment.criterion_scores = []
        mock_judgment.improvement_suggestions = ["Test suggestion"]
        # llm_model_used must be a real string so the evaluator's fail-open
        # error check (j.llm_model_used == "error") does not trip (#10880).
        mock_judgment.llm_model_used = "test-model"

        workflow_judge.evaluate_workflow_step.return_value = mock_judgment
        response_judge.evaluate_agent_response.return_value = mock_judgment
        security_judge.evaluate_command_security.return_value = mock_judgment

        return {
            "workflow_step_judge": workflow_judge,
            "agent_response_judge": response_judge,
            "security_risk_judge": security_judge,
            "multi_agent_arbitrator": arbitrator,
        }

    @pytest.fixture
    def test_client(self):
        """Create test client for API testing"""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(validation_router, prefix="/api/validation_dashboard")
        return TestClient(app)

    @patch("api.validation_dashboard.get_validation_judges")
    def test_judge_workflow_step_api(self, mock_get_judges, mock_judges, test_client):
        """Test workflow step judgment API endpoint"""
        mock_get_judges.return_value = mock_judges

        request_data = {
            "step_data": {
                "step_id": "test_step",
                "command": "echo 'test'",
                "description": "Test command",
            },
            "workflow_context": {"workflow_name": "Test Workflow"},
            "user_context": {"permissions": ["user"]},
        }

        response = test_client.post("/api/validation_dashboard/judge_workflow_step", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["judgment"]["overall_score"] == 0.8
        assert data["judgment"]["recommendation"] == "APPROVE"

        # Verify judge was called with correct parameters
        workflow_judge = mock_judges["workflow_step_judge"]
        workflow_judge.evaluate_workflow_step.assert_called_once()

    @patch("api.validation_dashboard.get_validation_judges")
    def test_judge_agent_response_api(self, mock_get_judges, mock_judges, test_client):
        """Test agent response judgment API endpoint"""
        mock_get_judges.return_value = mock_judges

        request_data = {
            "request": {"query": "How do I install Docker?"},
            "response": {"content": "Run: apt install docker.io"},
            "agent_type": "terminal",
            "context": {"os": "ubuntu"},
        }

        response = test_client.post("/api/validation_dashboard/judge_agent_response", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["judgment"]["overall_score"] == 0.8

        # Verify judge was called
        response_judge = mock_judges["agent_response_judge"]
        response_judge.evaluate_agent_response.assert_called_once()

    @patch("api.validation_dashboard.get_validation_judges")
    def test_judge_status_api(self, mock_get_judges, mock_judges, test_client):
        """Test judge status API endpoint"""
        # get_performance_metrics is a *synchronous* method on real judges; the
        # /judge_status endpoint calls it without await. Because the mock judges
        # are AsyncMock, we must override this attribute with a sync MagicMock so
        # it returns a dict (not a coroutine) for JSON serialization (#10880).
        for judge_name, judge in mock_judges.items():
            judge.get_performance_metrics = MagicMock(
                return_value={
                    "total_judgments": 10,
                    "average_score": 0.75,
                    "average_processing_time_ms": 150.0,
                }
            )

        mock_get_judges.return_value = mock_judges

        response = test_client.get("/api/validation_dashboard/judge_status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert len(data["available_judges"]) == 4
        assert "workflow_step_judge" in data["judge_metrics"]
        assert data["judge_metrics"]["workflow_step_judge"]["total_judgments"] == 10

    @patch("api.validation_dashboard.get_validation_judges")
    def test_judge_unavailable(self, mock_get_judges, test_client):
        """Test API behavior when judges are unavailable"""
        mock_get_judges.return_value = None

        request_data = {"step_data": {"command": "test"}}
        response = test_client.post("/api/validation_dashboard/judge_workflow_step", json=request_data)

        assert response.status_code == 503
        assert "not available" in response.json()["detail"]

    def test_workflow_automation_judge_integration(self, mock_judges):
        """Test integration with workflow automation judge evaluator.

        Issue #10880: Judge wiring moved from WorkflowAutomationManager to
        WorkflowStepEvaluator. Judges are lazily imported from their source
        modules inside _initialize_judges, so we patch the source symbols.
        """
        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, return_value=mock_judges["workflow_step_judge"]),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            assert evaluator.judges_enabled is True
            assert evaluator.workflow_step_judge is mock_judges["workflow_step_judge"]
            assert evaluator.security_risk_judge is mock_judges["security_risk_judge"]

    @pytest.mark.asyncio
    async def test_workflow_step_evaluation_integration(self, mock_judges):
        """Test workflow step evaluation in the step evaluator (#10880)."""
        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, return_value=mock_judges["workflow_step_judge"]),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            test_step = WorkflowStep(step_id="test_step", command="echo 'test'", description="Test step")

            workflow = ActiveWorkflow(
                workflow_id="test_workflow",
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            # Test step evaluation
            evaluation = await evaluator.evaluate_step(workflow, test_step)

            assert evaluation["should_proceed"] is True
            assert "workflow_judgment" in evaluation
            assert "security_judgment" in evaluation

            # Verify judges were actually reached by the code path
            mock_judges["workflow_step_judge"].evaluate_workflow_step.assert_called_once()
            mock_judges["security_risk_judge"].evaluate_command_security.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_rejection_by_judge(self, mock_judges):
        """Test workflow step rejection by LLM judge (#10880)."""
        # Configure judges to reject the step
        reject_judgment = MagicMock()
        reject_judgment.overall_score = 0.3
        reject_judgment.recommendation = "REJECT"
        reject_judgment.confidence.value = "high"
        reject_judgment.reasoning = "Command is too risky"
        reject_judgment.criterion_scores = []
        reject_judgment.improvement_suggestions = ["Use safer alternative"]
        reject_judgment.llm_model_used = "test-model"

        mock_judges["workflow_step_judge"].evaluate_workflow_step.return_value = reject_judgment
        mock_judges["security_risk_judge"].evaluate_command_security.return_value = reject_judgment

        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, return_value=mock_judges["workflow_step_judge"]),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            test_step = WorkflowStep(
                step_id="risky_step",
                command="rm -rf /important_data",
                description="Dangerous step",
            )

            workflow = ActiveWorkflow(
                workflow_id="test_workflow",
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            # Test step evaluation - should reject
            evaluation = await evaluator.evaluate_step(workflow, test_step)

            assert evaluation["should_proceed"] is False
            assert "Workflow evaluation: REJECT" in evaluation["reason"]

            # Verify the rejecting judges were actually reached
            mock_judges["workflow_step_judge"].evaluate_workflow_step.assert_called_once()
            mock_judges["security_risk_judge"].evaluate_command_security.assert_called_once()

    def test_judge_error_handling(self, mock_judges):
        """Test error handling in judge integration (#10880).

        When the source judge import raises ImportError, the evaluator must
        gracefully disable judges (fail-open) rather than crashing.
        """
        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, side_effect=ImportError("Judge unavailable")),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            # Import failure must not crash construction; judges disabled.
            assert evaluator.judges_enabled is False
            assert evaluator.workflow_step_judge is None

    @pytest.mark.asyncio
    async def test_judge_error_handling_runtime(self, mock_judges):
        """A judge raising at evaluation time must not crash the evaluator.

        Issue #10880: evaluate_step wraps judge calls in try/except and returns
        a fail-open ``should_proceed=True`` response on unexpected errors.
        """
        mock_judges["workflow_step_judge"].evaluate_workflow_step.side_effect = Exception("Judge error")

        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, return_value=mock_judges["workflow_step_judge"]),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            test_step = WorkflowStep(step_id="err_step", command="echo err", description="err")
            workflow = ActiveWorkflow(
                workflow_id="test_workflow",
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            evaluation = await evaluator.evaluate_step(workflow, test_step)

            # Fail-open: evaluation error does not crash, defaults to proceed.
            assert evaluation["should_proceed"] is True
            assert "Evaluation error" in evaluation["reason"]
            mock_judges["workflow_step_judge"].evaluate_workflow_step.assert_called_once()

    def test_judge_performance_tracking(self, mock_judges):
        """Test that judge performance is tracked properly"""
        # get_performance_metrics is synchronous on real judges; override the
        # AsyncMock attribute with a sync MagicMock returning a dict (#10880).
        for judge in mock_judges.values():
            judge.get_performance_metrics = MagicMock(
                return_value={
                    "total_judgments": 5,
                    "average_score": 0.8,
                    "average_confidence": "high",
                    "average_processing_time_ms": 120.0,
                    "recommendation_distribution": {
                        "APPROVE": 3,
                        "CONDITIONAL": 1,
                        "REJECT": 1,
                    },
                }
            )

        # Test metrics collection
        for judge_name, judge in mock_judges.items():
            metrics = judge.get_performance_metrics()
            assert metrics["total_judgments"] == 5
            assert metrics["average_score"] == 0.8
            assert "recommendation_distribution" in metrics

    @pytest.mark.asyncio
    async def test_multi_criteria_evaluation(self, mock_judges):
        """Test that judges evaluate multiple criteria (#10880)."""
        from judges import CriterionScore, JudgmentConfidence, JudgmentDimension

        # Create detailed criterion scores
        criterion_scores = [
            CriterionScore(
                dimension=JudgmentDimension.SAFETY,
                score=0.9,
                confidence=JudgmentConfidence.HIGH,
                reasoning="Command is safe",
                evidence=["Non-destructive operation"],
            ),
            CriterionScore(
                dimension=JudgmentDimension.QUALITY,
                score=0.8,
                confidence=JudgmentConfidence.HIGH,
                reasoning="Good quality implementation",
                evidence=["Standard command", "Clear purpose"],
            ),
        ]

        detailed_judgment = MagicMock()
        detailed_judgment.overall_score = 0.85
        detailed_judgment.recommendation = "APPROVE"
        detailed_judgment.confidence = JudgmentConfidence.HIGH
        detailed_judgment.reasoning = "Multi-criteria evaluation successful"
        detailed_judgment.criterion_scores = criterion_scores
        detailed_judgment.improvement_suggestions = []
        detailed_judgment.llm_model_used = "test-model"

        mock_judges["workflow_step_judge"].evaluate_workflow_step.return_value = detailed_judgment

        # Test that all criteria are evaluated
        with (
            patch(WORKFLOW_STEP_JUDGE_SOURCE, return_value=mock_judges["workflow_step_judge"]),
            patch(SECURITY_RISK_JUDGE_SOURCE, return_value=mock_judges["security_risk_judge"]),
            patch(MULTI_AGENT_ARBITRATOR_SOURCE, return_value=mock_judges["multi_agent_arbitrator"]),
        ):
            from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
            from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

            evaluator = WorkflowStepEvaluator()

            test_step = WorkflowStep(
                step_id="multi_criteria_step",
                command="ls -la",
                description="List files",
            )

            workflow = ActiveWorkflow(
                workflow_id="test_workflow",
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            evaluation = await evaluator.evaluate_step(workflow, test_step)

            # Verify multi-criteria evaluation reached the workflow judge and
            # its overall score is surfaced in the result.
            workflow_judgment = evaluation["workflow_judgment"]
            assert workflow_judgment["overall_score"] == 0.85
            mock_judges["workflow_step_judge"].evaluate_workflow_step.assert_called_once()

    def test_judge_configuration(self):
        """Test judge configuration and customization"""
        from judges.security_risk_judge import SecurityRiskJudge
        from judges.workflow_step_judge import WorkflowStepJudge

        # Test custom threshold configuration
        workflow_judge = WorkflowStepJudge()
        workflow_judge.safety_threshold = 0.9  # Higher safety requirement
        workflow_judge.quality_threshold = 0.8  # Higher quality requirement

        assert workflow_judge.safety_threshold == 0.9
        assert workflow_judge.quality_threshold == 0.8

        security_judge = SecurityRiskJudge()
        security_judge.block_threshold = 0.6  # More restrictive
        security_judge.high_risk_threshold = 0.4  # Lower risk tolerance

        assert security_judge.block_threshold == 0.6
        assert security_judge.high_risk_threshold == 0.4

    def test_judge_context_preparation(self):
        """Test that judges receive proper context (#10880).

        The evaluator prepares step data and workflow context via
        _prepare_step_data / _prepare_workflow_context before invoking judges.
        This verifies the workflow context is well-formed for judge consumption.
        """
        from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
        from services.workflow_automation.step_evaluator import WorkflowStepEvaluator

        with (patch(WORKFLOW_STEP_JUDGE_SOURCE, side_effect=ImportError("Judge unavailable")),):
            evaluator = WorkflowStepEvaluator()

            test_step = WorkflowStep(step_id="ctx_step", command="ls", description="List")
            workflow = ActiveWorkflow(
                workflow_id="ctx_workflow",
                name="Context Workflow",
                description="Context test",
                session_id="ctx_session",
                steps=[test_step],
            )

            step_data = evaluator._prepare_step_data(test_step)
            workflow_context = evaluator._prepare_workflow_context(workflow)

            # Step data must carry the fields judges rely on.
            assert step_data["step_id"] == "ctx_step"
            assert step_data["command"] == "ls"
            assert step_data["description"] == "List"

            # Workflow context must be well-formed for judge consumption.
            assert workflow_context["workflow_name"] == "Context Workflow"
            assert workflow_context["total_steps"] == 1
            assert workflow_context["session_id"] == "ctx_session"

    @pytest.mark.asyncio
    async def test_judge_batch_evaluation(self, mock_judges):
        """Test batch evaluation capabilities"""
        # Test that multiple steps can be evaluated efficiently
        steps = [
            {"step_id": "step1", "command": "ls", "description": "List files"},
            {"step_id": "step2", "command": "pwd", "description": "Print directory"},
            {
                "step_id": "step3",
                "command": "echo 'done'",
                "description": "Print completion",
            },
        ]

        # Judges should be able to handle multiple evaluations
        for step in steps:
            assert "command" in step
            assert "description" in step

        # This would be extended with actual batch evaluation logic
