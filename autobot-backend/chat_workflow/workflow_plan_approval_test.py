#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Workflow Plan Approval System (Issue #390).

Tests plan presentation, approval waiting, response handling,
timeout behavior, state transitions, and edge cases.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from services.workflow_automation.executor import WorkflowExecutor
from services.workflow_automation.models import (
    ActiveWorkflow,
    AutomationMode,
    PlanApprovalMode,
    PlanApprovalRequest,
    PlanApprovalResponse,
    PlanApprovalStatus,
    PlanPresentationRequest,
    WorkflowStep,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_messenger():
    """Create mock WorkflowMessenger for testing."""
    messenger = MagicMock()
    messenger.send_message = AsyncMock()
    messenger.terminal_sessions = {"test_session": MagicMock()}
    return messenger


@pytest.fixture
def executor(mock_messenger):
    """Create WorkflowExecutor with mock messenger."""
    return WorkflowExecutor(mock_messenger)


@pytest.fixture
def sample_workflow():
    """Create sample ActiveWorkflow for testing."""
    steps = [
        WorkflowStep(
            step_id="step_1",
            command="apt update",
            description="Update package lists",
            risk_level="low",
            estimated_duration=10.0,
        ),
        WorkflowStep(
            step_id="step_2",
            command="apt install docker",
            description="Install Docker",
            risk_level="medium",
            estimated_duration=30.0,
        ),
        WorkflowStep(
            step_id="step_3",
            command="docker run hello-world",
            description="Run test container",
            risk_level="low",
            estimated_duration=5.0,
        ),
    ]

    return ActiveWorkflow(
        workflow_id="test_workflow_123",
        name="Test Workflow",
        description="Install Docker and run container",
        session_id="test_session",
        steps=steps,
        automation_mode=AutomationMode.SEMI_AUTOMATIC,
    )


@pytest.fixture
def high_risk_workflow():
    """Create workflow with high risk steps for testing."""
    steps = [
        WorkflowStep(
            step_id="step_1",
            command="rm -rf /tmp/*",
            description="Clean temp files",
            risk_level="high",
            estimated_duration=5.0,
        ),
        WorkflowStep(
            step_id="step_2",
            command="sudo chmod 777 /etc",
            description="Change permissions",
            risk_level="critical",
            estimated_duration=2.0,
        ),
    ]

    return ActiveWorkflow(
        workflow_id="high_risk_workflow",
        name="High Risk Workflow",
        description="Dangerous operations",
        session_id="test_session",
        steps=steps,
        automation_mode=AutomationMode.MANUAL,
    )


# =========================================================================
# Model Tests
# =========================================================================


class TestPlanApprovalModels:
    """Tests for plan approval data models."""

    def test_plan_approval_mode_values(self):
        """Test PlanApprovalMode enum values."""
        assert PlanApprovalMode.FULL_PLAN_APPROVAL.value == "full_plan"
        assert PlanApprovalMode.PER_STEP_APPROVAL.value == "per_step"
        assert PlanApprovalMode.HYBRID_APPROVAL.value == "hybrid"
        assert PlanApprovalMode.AUTO_SAFE_STEPS.value == "auto_safe"

    def test_plan_approval_status_values(self):
        """Test PlanApprovalStatus enum values."""
        assert PlanApprovalStatus.PENDING.value == "pending"
        assert PlanApprovalStatus.PRESENTED.value == "presented"
        assert PlanApprovalStatus.AWAITING_APPROVAL.value == "awaiting_approval"
        assert PlanApprovalStatus.APPROVED.value == "approved"
        assert PlanApprovalStatus.REJECTED.value == "rejected"
        assert PlanApprovalStatus.MODIFIED.value == "modified"
        assert PlanApprovalStatus.TIMEOUT.value == "timeout"

    def test_plan_approval_request_creation(self, sample_workflow):
        """Test PlanApprovalRequest dataclass creation."""
        request = PlanApprovalRequest(
            workflow_id=sample_workflow.workflow_id,
            plan_summary="Test plan",
            total_steps=3,
            steps_preview=sample_workflow.steps,
        )

        assert request.workflow_id == "test_workflow_123"
        assert request.total_steps == 3
        assert request.status == PlanApprovalStatus.PENDING
        assert request.approval_mode == PlanApprovalMode.FULL_PLAN_APPROVAL
        assert request.timeout_seconds == 300
        assert request.created_at is not None

    def test_plan_approval_request_to_presentation_dict(self, sample_workflow):
        """Test PlanApprovalRequest.to_presentation_dict() method."""
        request = PlanApprovalRequest(
            workflow_id=sample_workflow.workflow_id,
            plan_summary="Install Docker",
            total_steps=3,
            steps_preview=sample_workflow.steps,
            risk_assessment="MEDIUM - 1 medium risk step(s)",
            estimated_total_duration=45.0,
        )

        result = request.to_presentation_dict()

        assert result["workflow_id"] == "test_workflow_123"
        assert result["plan_summary"] == "Install Docker"
        assert result["total_steps"] == 3
        assert len(result["steps"]) == 3
        assert result["steps"][0]["step_id"] == "step_1"
        assert result["steps"][0]["command"] == "apt update"
        assert result["steps"][0]["risk_level"] == "low"
        assert result["risk_assessment"] == "MEDIUM - 1 medium risk step(s)"
        assert result["estimated_total_duration"] == 45.0

    def test_plan_approval_response_model(self):
        """Test PlanApprovalResponse Pydantic model."""
        response = PlanApprovalResponse(
            workflow_id="test_123",
            approved=True,
            approval_mode="full_plan",
        )

        assert response.workflow_id == "test_123"
        assert response.approved is True
        assert response.modifications is None
        assert response.reason is None

    def test_plan_approval_response_with_rejection(self):
        """Test PlanApprovalResponse with rejection."""
        response = PlanApprovalResponse(
            workflow_id="test_123",
            approved=False,
            reason="Too risky to run now",
        )

        assert response.approved is False
        assert response.reason == "Too risky to run now"

    def test_plan_presentation_request_model(self):
        """Test PlanPresentationRequest Pydantic model."""
        request = PlanPresentationRequest(
            workflow_id="test_123",
            approval_mode="full_plan",
            include_risk_assessment=True,
            timeout_seconds=600,
        )

        assert request.workflow_id == "test_123"
        assert request.approval_mode == "full_plan"
        assert request.include_risk_assessment is True
        assert request.timeout_seconds == 600


# =========================================================================
# Executor Tests - Plan Presentation
# =========================================================================


class TestPlanPresentation:
    """Tests for plan presentation functionality."""

    @pytest.mark.asyncio
    async def test_present_plan_for_approval_success(self, executor, sample_workflow):
        """Test successful plan presentation."""
        result = await executor.present_plan_for_approval(
            sample_workflow,
            PlanApprovalMode.FULL_PLAN_APPROVAL,
            timeout_seconds=300,
        )

        assert result is not None
        assert result.workflow_id == "test_workflow_123"
        assert result.status == PlanApprovalStatus.AWAITING_APPROVAL
        assert result.total_steps == 3
        assert result.presented_at is not None

        # Verify WebSocket message was sent
        executor.messenger.send_message.assert_called_once()
        call_args = executor.messenger.send_message.call_args
        assert call_args[0][0] == "test_session"
        assert call_args[0][1]["type"] == "workflow_plan_presented"

    @pytest.mark.asyncio
    async def test_present_plan_stores_pending_approval(
        self, executor, sample_workflow
    ):
        """Test that pending approval is stored correctly."""
        await executor.present_plan_for_approval(sample_workflow)

        assert "test_workflow_123" in executor._pending_plan_approvals
        assert "test_workflow_123" in executor._plan_approval_events

    @pytest.mark.asyncio
    async def test_present_plan_unsupported_mode_raises_error(
        self, executor, sample_workflow
    ):
        """Test that unsupported approval modes raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await executor.present_plan_for_approval(
                sample_workflow,
                PlanApprovalMode.PER_STEP_APPROVAL,  # Not implemented
            )

        assert "not yet implemented" in str(exc_info.value)
        assert "full_plan" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_present_plan_invalid_timeout_raises_error(
        self, executor, sample_workflow
    ):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await executor.present_plan_for_approval(
                sample_workflow,
                timeout_seconds=0,
            )

        assert "timeout_seconds must be positive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_present_plan_timeout_capped_at_max(self, executor, sample_workflow):
        """Test that timeout is capped at maximum value."""
        result = await executor.present_plan_for_approval(
            sample_workflow,
            timeout_seconds=9999,  # Over max
        )

        assert result.timeout_seconds == 3600  # Capped at 1 hour

    @pytest.mark.asyncio
    async def test_present_plan_returns_existing_if_pending(
        self, executor, sample_workflow
    ):
        """Test that existing pending approval is returned."""
        # First presentation
        first_result = await executor.present_plan_for_approval(sample_workflow)

        # Second presentation should return existing
        second_result = await executor.present_plan_for_approval(sample_workflow)

        assert first_result.workflow_id == second_result.workflow_id
        # WebSocket should only be called once
        assert executor.messenger.send_message.call_count == 1


# =========================================================================
# Executor Tests - Risk Assessment
# =========================================================================


class TestRiskAssessment:
    """Tests for plan risk assessment."""

    def test_assess_plan_risk_low(self, executor, sample_workflow):
        """Test risk assessment for low-risk workflow."""
        # Modify all steps to low risk
        for step in sample_workflow.steps:
            step.risk_level = "low"

        result = executor._assess_plan_risk(sample_workflow)

        assert "LOW" in result
        assert "3" in result  # 3 low risk steps

    def test_assess_plan_risk_medium(self, executor, sample_workflow):
        """Test risk assessment with medium-risk steps."""
        result = executor._assess_plan_risk(sample_workflow)

        assert "MEDIUM" in result
        assert "1 medium risk" in result

    def test_assess_plan_risk_high(self, executor, high_risk_workflow):
        """Test risk assessment with high-risk steps."""
        # Remove critical step to test high
        high_risk_workflow.steps = [high_risk_workflow.steps[0]]

        result = executor._assess_plan_risk(high_risk_workflow)

        assert "HIGH" in result
        assert "1 high risk" in result

    def test_assess_plan_risk_critical(self, executor, high_risk_workflow):
        """Test risk assessment with critical-risk steps."""
        result = executor._assess_plan_risk(high_risk_workflow)

        assert "CRITICAL" in result
        assert "1 critical risk" in result


# =========================================================================
# Executor Tests - Approval Response Handling
# =========================================================================


class TestApprovalResponseHandling:
    """Tests for approval response handling."""

    @pytest.mark.asyncio
    async def test_handle_approval_response_approved(self, executor, sample_workflow):
        """Test handling approved response."""
        # Present plan first
        await executor.present_plan_for_approval(sample_workflow)

        # Handle approval
        result = executor.handle_plan_approval_response(
            workflow_id="test_workflow_123",
            approved=True,
        )

        assert result is True
        approval = executor._pending_plan_approvals["test_workflow_123"]
        assert approval.status == PlanApprovalStatus.APPROVED
        assert approval.resolved_at is not None

    @pytest.mark.asyncio
    async def test_handle_approval_response_rejected(self, executor, sample_workflow):
        """Test handling rejected response."""
        await executor.present_plan_for_approval(sample_workflow)

        result = executor.handle_plan_approval_response(
            workflow_id="test_workflow_123",
            approved=False,
            reason="Not safe now",
        )

        assert result is True
        approval = executor._pending_plan_approvals["test_workflow_123"]
        assert approval.status == PlanApprovalStatus.REJECTED
        assert approval.user_response == "Not safe now"

    @pytest.mark.asyncio
    async def test_handle_approval_response_with_modifications(
        self, executor, sample_workflow
    ):
        """Test handling response with modifications."""
        await executor.present_plan_for_approval(sample_workflow)

        result = executor.handle_plan_approval_response(
            workflow_id="test_workflow_123",
            approved=False,
            modifications=["step_2"],  # Skip step 2
        )

        assert result is True
        approval = executor._pending_plan_approvals["test_workflow_123"]
        assert approval.status == PlanApprovalStatus.MODIFIED

    def test_handle_approval_response_no_pending(self, executor):
        """Test handling response when no pending approval."""
        result = executor.handle_plan_approval_response(
            workflow_id="nonexistent",
            approved=True,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_approval_sets_event(self, executor, sample_workflow):
        """Test that handling approval sets the event."""
        await executor.present_plan_for_approval(sample_workflow)

        event = executor._plan_approval_events["test_workflow_123"]
        assert not event.is_set()

        executor.handle_plan_approval_response(
            workflow_id="test_workflow_123",
            approved=True,
        )

        assert event.is_set()


# =========================================================================
# Executor Tests - Approval Waiting
# =========================================================================


class TestApprovalWaiting:
    """Tests for approval waiting functionality."""

    @pytest.mark.asyncio
    async def test_wait_for_approval_success(self, executor, sample_workflow):
        """Test successful approval waiting."""
        await executor.present_plan_for_approval(sample_workflow)

        # Simulate approval in background
        async def approve_after_delay():
            await asyncio.sleep(0.1)
            executor.handle_plan_approval_response(
                workflow_id="test_workflow_123",
                approved=True,
            )

        # Start approval task
        asyncio.create_task(approve_after_delay())

        # Wait for approval
        result = await executor.wait_for_plan_approval(
            "test_workflow_123",
            timeout_seconds=5,
        )

        assert result.status == PlanApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self, executor, sample_workflow):
        """Test approval waiting timeout."""
        await executor.present_plan_for_approval(sample_workflow)

        # Wait with short timeout (no approval coming)
        result = await executor.wait_for_plan_approval(
            "test_workflow_123",
            timeout_seconds=0.1,
        )

        assert result.status == PlanApprovalStatus.TIMEOUT
        assert result.resolved_at is not None

    @pytest.mark.asyncio
    async def test_wait_for_approval_no_pending_raises(self, executor):
        """Test waiting for nonexistent approval raises error."""
        with pytest.raises(ValueError) as exc_info:
            await executor.wait_for_plan_approval("nonexistent")

        assert "No pending approval" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wait_for_approval_cleans_up_event(self, executor, sample_workflow):
        """Test that waiting cleans up event on completion."""
        await executor.present_plan_for_approval(sample_workflow)

        # Approve immediately
        executor.handle_plan_approval_response(
            workflow_id="test_workflow_123",
            approved=True,
        )

        await executor.wait_for_plan_approval("test_workflow_123", timeout_seconds=1)

        # Event should be cleaned up
        assert "test_workflow_123" not in executor._plan_approval_events


# =========================================================================
# Executor Tests - Cleanup
# =========================================================================


class TestApprovalCleanup:
    """Tests for approval cleanup functionality."""

    @pytest.mark.asyncio
    async def test_clear_pending_approval(self, executor, sample_workflow):
        """Test clearing pending approval."""
        await executor.present_plan_for_approval(sample_workflow)

        assert "test_workflow_123" in executor._pending_plan_approvals
        assert "test_workflow_123" in executor._plan_approval_events

        executor.clear_pending_approval("test_workflow_123")

        assert "test_workflow_123" not in executor._pending_plan_approvals
        assert "test_workflow_123" not in executor._plan_approval_events

    @pytest.mark.asyncio
    async def test_get_pending_approval(self, executor, sample_workflow):
        """Test getting pending approval."""
        await executor.present_plan_for_approval(sample_workflow)

        result = executor.get_pending_approval("test_workflow_123")

        assert result is not None
        assert result.workflow_id == "test_workflow_123"

    def test_get_pending_approval_nonexistent(self, executor):
        """Test getting nonexistent pending approval."""
        result = executor.get_pending_approval("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_workflow_clears_approval(
        self, executor, sample_workflow, mock_messenger
    ):
        """Test that cancelling workflow clears pending approval."""
        await executor.present_plan_for_approval(sample_workflow)

        assert "test_workflow_123" in executor._pending_plan_approvals

        await executor.cancel_workflow(sample_workflow, {})

        assert "test_workflow_123" not in executor._pending_plan_approvals


# =========================================================================
# Integration Tests
# =========================================================================


class TestApprovalIntegration:
    """Integration tests for complete approval flow."""

    @pytest.mark.asyncio
    async def test_full_approval_flow(self, executor, sample_workflow):
        """Test complete approval flow from presentation to execution."""
        # Step 1: Present plan
        approval_request = await executor.present_plan_for_approval(sample_workflow)
        assert approval_request.status == PlanApprovalStatus.AWAITING_APPROVAL

        # Step 2: User approves (simulated)
        async def user_approves():
            await asyncio.sleep(0.05)
            executor.handle_plan_approval_response(
                workflow_id="test_workflow_123",
                approved=True,
            )

        asyncio.create_task(user_approves())

        # Step 3: Wait for approval
        result = await executor.wait_for_plan_approval(
            "test_workflow_123",
            timeout_seconds=5,
        )

        assert result.status == PlanApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_full_rejection_flow(self, executor, sample_workflow):
        """Test complete rejection flow."""
        await executor.present_plan_for_approval(sample_workflow)

        async def user_rejects():
            await asyncio.sleep(0.05)
            executor.handle_plan_approval_response(
                workflow_id="test_workflow_123",
                approved=False,
                reason="Not ready",
            )

        asyncio.create_task(user_rejects())

        result = await executor.wait_for_plan_approval(
            "test_workflow_123",
            timeout_seconds=5,
        )

        assert result.status == PlanApprovalStatus.REJECTED
        assert result.user_response == "Not ready"

    @pytest.mark.asyncio
    async def test_websocket_message_content(self, executor, sample_workflow):
        """Test WebSocket message contains correct content."""
        await executor.present_plan_for_approval(sample_workflow)

        call_args = executor.messenger.send_message.call_args
        message = call_args[0][1]

        assert message["type"] == "workflow_plan_presented"
        assert message["workflow_id"] == "test_workflow_123"
        assert "plan" in message
        assert "approval_options" in message

        plan = message["plan"]
        assert plan["total_steps"] == 3
        assert len(plan["steps"]) == 3

        options = message["approval_options"]
        assert "approve_all" in options
        assert "reject" in options
