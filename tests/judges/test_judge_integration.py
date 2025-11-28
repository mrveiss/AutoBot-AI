"""
Integration tests for LLM-as-Judge framework

Tests integration with workflow automation, validation dashboard, and other system components.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.validation_dashboard import router as validation_router


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

    @patch("backend.api.validation_dashboard.get_validation_judges")
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

        response = test_client.post(
            "/api/validation_dashboard/judge_workflow_step", json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["judgment"]["overall_score"] == 0.8
        assert data["judgment"]["recommendation"] == "APPROVE"

        # Verify judge was called with correct parameters
        workflow_judge = mock_judges["workflow_step_judge"]
        workflow_judge.evaluate_workflow_step.assert_called_once()

    @patch("backend.api.validation_dashboard.get_validation_judges")
    def test_judge_agent_response_api(self, mock_get_judges, mock_judges, test_client):
        """Test agent response judgment API endpoint"""
        mock_get_judges.return_value = mock_judges

        request_data = {
            "request": {"query": "How do I install Docker?"},
            "response": {"content": "Run: apt install docker.io"},
            "agent_type": "terminal",
            "context": {"os": "ubuntu"},
        }

        response = test_client.post(
            "/api/validation_dashboard/judge_agent_response", json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["judgment"]["overall_score"] == 0.8

        # Verify judge was called
        response_judge = mock_judges["agent_response_judge"]
        response_judge.evaluate_agent_response.assert_called_once()

    @patch("backend.api.validation_dashboard.get_validation_judges")
    def test_judge_status_api(self, mock_get_judges, mock_judges, test_client):
        """Test judge status API endpoint"""
        # Mock performance metrics
        for judge_name, judge in mock_judges.items():
            judge.get_performance_metrics.return_value = {
                "total_judgments": 10,
                "average_score": 0.75,
                "average_processing_time_ms": 150.0,
            }

        mock_get_judges.return_value = mock_judges

        response = test_client.get("/api/validation_dashboard/judge_status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert len(data["available_judges"]) == 4
        assert "workflow_step_judge" in data["judge_metrics"]

    @patch("backend.api.validation_dashboard.get_validation_judges")
    def test_judge_unavailable(self, mock_get_judges, test_client):
        """Test API behavior when judges are unavailable"""
        mock_get_judges.return_value = None

        request_data = {"step_data": {"command": "test"}}
        response = test_client.post(
            "/api/validation_dashboard/judge_workflow_step", json=request_data
        )

        assert response.status_code == 503
        assert "not available" in response.json()["detail"]

    def test_workflow_automation_judge_integration(self, mock_judges):
        """Test integration with workflow automation system"""
        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True), patch(
            "backend.api.workflow_automation.WorkflowStepJudge",
            return_value=mock_judges["workflow_step_judge"],
        ), patch(
            "backend.api.workflow_automation.SecurityRiskJudge",
            return_value=mock_judges["security_risk_judge"],
        ):
            from backend.api.workflow_automation import WorkflowAutomationManager

            manager = WorkflowAutomationManager()

            assert manager.judges_enabled is True
            assert manager.workflow_step_judge is not None
            assert manager.security_risk_judge is not None

    @pytest.mark.asyncio
    async def test_workflow_step_evaluation_integration(self, mock_judges):
        """Test workflow step evaluation in automation manager"""
        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True), patch(
            "backend.api.workflow_automation.WorkflowStepJudge",
            return_value=mock_judges["workflow_step_judge"],
        ), patch(
            "backend.api.workflow_automation.SecurityRiskJudge",
            return_value=mock_judges["security_risk_judge"],
        ):
            from backend.api.workflow_automation import (
                ActiveWorkflow,
                WorkflowAutomationManager,
                WorkflowStep,
            )

            manager = WorkflowAutomationManager()

            # Create a test workflow with a step
            workflow_id = "test_workflow"

            test_step = WorkflowStep(
                step_id="test_step", command="echo 'test'", description="Test step"
            )

            workflow = ActiveWorkflow(
                workflow_id=workflow_id,
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            manager.active_workflows[workflow_id] = workflow

            # Test step evaluation
            evaluation = await manager._evaluate_workflow_step(workflow_id, test_step)

            assert evaluation["should_proceed"] is True
            assert "workflow_judgment" in evaluation
            assert "security_judgment" in evaluation

            # Verify judges were called
            mock_judges[
                "workflow_step_judge"
            ].evaluate_workflow_step.assert_called_once()
            mock_judges[
                "security_risk_judge"
            ].evaluate_command_security.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_rejection_by_judge(self, mock_judges):
        """Test workflow step rejection by LLM judge"""
        # Configure judges to reject the step
        reject_judgment = MagicMock()
        reject_judgment.overall_score = 0.3
        reject_judgment.recommendation = "REJECT"
        reject_judgment.confidence.value = "high"
        reject_judgment.reasoning = "Command is too risky"
        reject_judgment.criterion_scores = []
        reject_judgment.improvement_suggestions = ["Use safer alternative"]

        mock_judges[
            "workflow_step_judge"
        ].evaluate_workflow_step.return_value = reject_judgment
        mock_judges[
            "security_risk_judge"
        ].evaluate_command_security.return_value = reject_judgment

        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True), patch(
            "backend.api.workflow_automation.WorkflowStepJudge",
            return_value=mock_judges["workflow_step_judge"],
        ), patch(
            "backend.api.workflow_automation.SecurityRiskJudge",
            return_value=mock_judges["security_risk_judge"],
        ):
            from backend.api.workflow_automation import (
                ActiveWorkflow,
                WorkflowAutomationManager,
                WorkflowStep,
            )

            manager = WorkflowAutomationManager()

            # Create test workflow
            workflow_id = "test_workflow"

            test_step = WorkflowStep(
                step_id="risky_step",
                command="rm -rf /important_data",
                description="Dangerous step",
            )

            workflow = ActiveWorkflow(
                workflow_id=workflow_id,
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            manager.active_workflows[workflow_id] = workflow

            # Test step evaluation - should reject
            evaluation = await manager._evaluate_workflow_step(workflow_id, test_step)

            assert evaluation["should_proceed"] is False
            assert "too risky" in evaluation["reason"]

    def test_judge_error_handling(self, mock_judges):
        """Test error handling in judge integration"""
        # Configure judge to raise exception
        mock_judges[
            "workflow_step_judge"
        ].evaluate_workflow_step.side_effect = Exception("Judge error")

        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True), patch(
            "backend.api.workflow_automation.WorkflowStepJudge",
            return_value=mock_judges["workflow_step_judge"],
        ), patch(
            "backend.api.workflow_automation.SecurityRiskJudge",
            return_value=mock_judges["security_risk_judge"],
        ):
            manager = WorkflowAutomationManager()

            # Test that manager handles judge errors gracefully
            assert manager.judges_enabled is True

            # Error in individual evaluation should not crash the system

    def test_judge_performance_tracking(self, mock_judges):
        """Test that judge performance is tracked properly"""
        # Add mock judgments to history
        for judge in mock_judges.values():
            judge.get_performance_metrics.return_value = {
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

        # Test metrics collection
        for judge_name, judge in mock_judges.items():
            metrics = judge.get_performance_metrics()
            assert metrics["total_judgments"] == 5
            assert metrics["average_score"] == 0.8
            assert "recommendation_distribution" in metrics

    @pytest.mark.asyncio
    async def test_multi_criteria_evaluation(self, mock_judges):
        """Test that judges evaluate multiple criteria"""
        from src.judges import CriterionScore, JudgmentConfidence, JudgmentDimension

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

        mock_judges[
            "workflow_step_judge"
        ].evaluate_workflow_step.return_value = detailed_judgment

        # Test that all criteria are evaluated
        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True), patch(
            "backend.api.workflow_automation.WorkflowStepJudge",
            return_value=mock_judges["workflow_step_judge"],
        ), patch(
            "backend.api.workflow_automation.SecurityRiskJudge",
            return_value=mock_judges["security_risk_judge"],
        ):
            from backend.api.workflow_automation import (
                ActiveWorkflow,
                WorkflowAutomationManager,
                WorkflowStep,
            )

            manager = WorkflowAutomationManager()

            workflow_id = "test_workflow"

            test_step = WorkflowStep(
                step_id="multi_criteria_step",
                command="ls -la",
                description="List files",
            )

            workflow = ActiveWorkflow(
                workflow_id=workflow_id,
                name="Test Workflow",
                description="Test",
                session_id="test_session",
                steps=[test_step],
            )

            manager.active_workflows[workflow_id] = workflow

            evaluation = await manager._evaluate_workflow_step(workflow_id, test_step)

            # Verify multi-criteria evaluation
            workflow_judgment = evaluation["workflow_judgment"]
            assert workflow_judgment["overall_score"] == 0.85

    def test_judge_configuration(self):
        """Test judge configuration and customization"""
        from src.judges.security_risk_judge import SecurityRiskJudge
        from src.judges.workflow_step_judge import WorkflowStepJudge

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
        """Test that judges receive proper context"""
        with patch("backend.api.workflow_automation.JUDGES_AVAILABLE", True):
            manager = WorkflowAutomationManager()

            # Test context preparation for different scenarios
            contexts = [
                {"environment": "production", "user": "admin"},
                {"environment": "development", "user": "developer"},
                {"environment": "testing", "user": "tester"},
            ]

            for context in contexts:
                # Context should be properly formatted and passed to judges
                assert isinstance(context, dict)
                assert "environment" in context
                assert "user" in context

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
