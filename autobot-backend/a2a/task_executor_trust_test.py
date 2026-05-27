# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Executor — Behavioural Trust Score Integration Tests

Issue #7358 phase 2: Verifies that execute_a2a_task feeds task outcomes back
into the TrustScoreManager so peer trust levels evolve from real interaction
history.

Test strategy: mock out Redis (TaskManager) and the TrustScoreManager to
avoid network dependencies.  Only the executor's decision logic is exercised.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from a2a.task_executor import execute_a2a_task
from a2a.types import TaskState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_manager_mock():
    mgr = MagicMock()
    mgr.update_state = MagicMock()
    mgr.publish_event = MagicMock()
    mgr.add_artifact = MagicMock()
    return mgr


def _make_eval_pass(confidence=0.9):
    result = MagicMock()
    result.passed = True
    result.confidence = confidence
    result.eval_reason = None
    return result


def _make_eval_fail(confidence=0.3, reason="low_confidence"):
    result = MagicMock()
    result.passed = False
    result.confidence = confidence
    result.eval_reason = reason
    return result


# ---------------------------------------------------------------------------
# Successful task → record_success
# ---------------------------------------------------------------------------


class TestExecutorRecordsSuccess:
    @pytest.mark.asyncio
    async def test_completed_task_records_success(self):
        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(return_value={"response": "hello world"})

        scrub_result = MagicMock()
        scrub_result.text = "hello world"
        scrub_result.redaction_count = 0

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", return_value=scrub_result),
            patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=_make_eval_pass())),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            await execute_a2a_task("task-1", "do something", peer_id="partner-agent")

        trust_mgr.record_success.assert_called_once_with("partner-agent")
        trust_mgr.record_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_peer_id_skips_trust_recording(self):
        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(return_value={"response": "hi"})

        scrub_result = MagicMock()
        scrub_result.text = "hi"
        scrub_result.redaction_count = 0

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", return_value=scrub_result),
            patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=_make_eval_pass())),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            await execute_a2a_task("task-2", "do something", peer_id=None)

        trust_mgr.record_success.assert_not_called()
        trust_mgr.record_failure.assert_not_called()


# ---------------------------------------------------------------------------
# Self-eval failure → record_failure
# ---------------------------------------------------------------------------


class TestExecutorRecordsFailure:
    @pytest.mark.asyncio
    async def test_eval_fail_records_failure(self):
        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(return_value={"response": "bad output"})

        scrub_result = MagicMock()
        scrub_result.text = "bad output"
        scrub_result.redaction_count = 0

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", return_value=scrub_result),
            patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=_make_eval_fail())),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            await execute_a2a_task("task-3", "do something", peer_id="partner-agent")

        trust_mgr.record_failure.assert_called_once_with("partner-agent")
        trust_mgr.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestrator_exception_records_failure(self):
        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(side_effect=RuntimeError("boom"))

        scrub_result = MagicMock()
        scrub_result.text = "do something"
        scrub_result.redaction_count = 0

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", return_value=scrub_result),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            await execute_a2a_task("task-4", "do something", peer_id="partner-agent")

        trust_mgr.record_failure.assert_called_once_with("partner-agent")
        trust_mgr.record_success.assert_not_called()


# ---------------------------------------------------------------------------
# PII block → record_threat_event
# ---------------------------------------------------------------------------


class TestExecutorRecordsThreatEvent:
    @pytest.mark.asyncio
    async def test_inbound_pii_block_records_threat_event(self):
        from a2a.pii_pipeline import PIIBlocked

        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", side_effect=PIIBlocked("pii found")),
        ):
            await execute_a2a_task("task-5", "ssn: 123-45-6789", peer_id="suspect-agent")

        trust_mgr.record_threat_event.assert_called_once_with("suspect-agent")
        trust_mgr.record_success.assert_not_called()
        trust_mgr.record_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_outbound_pii_block_records_threat_event(self):
        from a2a.pii_pipeline import PIIBlocked

        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(return_value={"response": "secret data"})

        call_count = 0

        def _scrub_side_effect(text, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Inbound: passes
                result = MagicMock()
                result.text = text
                result.redaction_count = 0
                return result
            # Outbound response: blocked
            raise PIIBlocked("secret in response")

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", side_effect=_scrub_side_effect),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            await execute_a2a_task("task-6", "summarise", peer_id="suspect-agent")

        trust_mgr.record_threat_event.assert_called_once_with("suspect-agent")

    @pytest.mark.asyncio
    async def test_trust_recording_error_does_not_crash_executor(self):
        """Trust recording failures must never fail the task pipeline."""
        tm = _make_task_manager_mock()
        trust_mgr = MagicMock()
        trust_mgr.record_success.side_effect = Exception("Redis down")

        orchestrator = MagicMock()
        orchestrator.process_request = AsyncMock(return_value={"response": "ok"})

        scrub_result = MagicMock()
        scrub_result.text = "ok"
        scrub_result.redaction_count = 0

        with (
            patch("a2a.task_executor.get_task_manager", return_value=tm),
            patch("a2a.task_executor.get_trust_manager", return_value=trust_mgr),
            patch("a2a.task_executor.scrub_outbound", return_value=scrub_result),
            patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=_make_eval_pass())),
            patch(
                "agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True
            ),
        ):
            # Should not raise even though trust recording throws
            await execute_a2a_task("task-7", "do something", peer_id="flaky-peer")

        # Task should still reach COMPLETED
        states = [c.args[1] for c in tm.update_state.call_args_list]
        assert TaskState.COMPLETED in states
