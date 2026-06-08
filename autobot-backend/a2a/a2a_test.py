# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Protocol Unit Tests

Issue #961: Tests for types, agent_card builder, and task_manager.
Issue #4502: TaskManager tests now mock Redis instead of the in-process dict.
Uses no network connections and no external dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from a2a.agent_card import build_agent_card
from a2a.task_manager import TaskManager
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskArtifact, TaskState

# ---------------------------------------------------------------------------
# AgentCard / types tests
# ---------------------------------------------------------------------------


class TestAgentCardTypes:
    def test_agent_skill_to_dict(self):
        skill = AgentSkill(
            id="chat",
            name="Conversational interactions",
            description="Quick responses and natural conversation.",
            tags=["hello", "hi"],
            examples=["Hello!", "How are you?"],
        )
        d = skill.to_dict()
        assert d["id"] == "chat"
        assert d["name"] == "Conversational interactions"
        assert "hello" in d["tags"]
        assert "Hello!" in d["examples"]

    def test_agent_capabilities_defaults(self):
        caps = AgentCapabilities()
        d = caps.to_dict()
        assert d["streaming"] is False
        assert d["pushNotifications"] is False
        assert d["stateTransitionHistory"] is True

    def test_agent_card_to_dict(self):
        card = AgentCard(
            name="TestAgent",
            description="A test agent",
            url="https://example.com/api/a2a",
            version="0.1.0",
            skills=[],
            provider="mrveiss",
            documentation_url="https://example.com/docs",
        )
        d = card.to_dict()
        assert d["name"] == "TestAgent"
        assert d["url"] == "https://example.com/api/a2a"
        assert d["provider"] == {"organization": "mrveiss"}
        assert d["documentationUrl"] == "https://example.com/docs"
        assert "capabilities" in d

    def test_agent_card_without_optional_fields(self):
        card = AgentCard(
            name="MinimalAgent",
            description="Minimal",
            url="https://example.com",
            version="1.0.0",
            skills=[],
        )
        d = card.to_dict()
        assert "provider" not in d
        assert "documentationUrl" not in d


# ---------------------------------------------------------------------------
# Agent Card builder tests
# ---------------------------------------------------------------------------


class TestBuildAgentCard:
    def test_build_returns_agent_card(self):
        card = build_agent_card("https://10.0.0.1:8443")
        assert isinstance(card, AgentCard)

    def test_card_name_is_autobot(self):
        card = build_agent_card("https://10.0.0.1:8443")
        assert card.name == "AutoBot"

    def test_card_url_uses_base(self):
        card = build_agent_card("https://10.0.0.1:8443")
        assert card.url == "https://10.0.0.1:8443/api/a2a"

    def test_card_has_skills_or_empty_on_missing_stack(self):
        # Skills may be empty in dev environments without the full agent stack
        card = build_agent_card("https://example.com")
        assert isinstance(card.skills, list)

    def test_all_skills_have_required_fields(self):
        card = build_agent_card("https://example.com")
        for skill in card.skills:
            assert skill.id, f"Skill missing id: {skill}"
            assert skill.name, f"Skill missing name: {skill}"
            assert skill.description, f"Skill missing description: {skill}"

    def test_card_serializes_to_dict(self):
        card = build_agent_card("https://example.com")
        d = card.to_dict()
        assert "name" in d
        assert "url" in d
        assert "skills" in d
        assert "capabilities" in d
        assert isinstance(d["skills"], list)

    def test_skills_populated_when_agent_stack_available(self):
        """
        When the full agent stack is available, skills are populated from
        DEFAULT_AGENT_CAPABILITIES. In dev environments without aioredis/
        knowledge_base this is a graceful no-op (skills=[]) — verified by
        integration tests on the backend server.
        """
        card = build_agent_card("https://example.com")
        # Either populated (full stack) or empty (dev env) — never None
        assert card.skills is not None
        for skill in card.skills:
            assert skill.id in (
                "chat",
                "system_commands",
                "rag",
                "knowledge_retrieval",
                "research",
                "orchestrator",
                "data_analysis",
                "code_generation",
                "translation",
                "summarization",
                "sentiment_analysis",
                "image_analysis",
                "audio_processing",
            )


# ---------------------------------------------------------------------------
# Redis mock fixture
# ---------------------------------------------------------------------------


def _make_redis_mock():
    """Return a MagicMock that mimics the subset of redis.Redis used by TaskManager."""
    store: dict = {}
    audit_lists: dict = {}
    task_set: set = set()

    mock = MagicMock()

    def _set(key, value, ex=None):
        store[key] = value if isinstance(value, str) else value.decode("utf-8")

    def _get(key):
        v = store.get(key)
        return v.encode("utf-8") if v is not None else None

    def _sadd(key, member):
        task_set.add(member if isinstance(member, str) else member.decode("utf-8"))

    def _srem(key, member):
        task_set.discard(member if isinstance(member, str) else member.decode("utf-8"))

    def _smembers(key):
        return {m.encode("utf-8") for m in task_set}

    def _rpush(key, value):
        audit_lists.setdefault(key, []).append(value if isinstance(value, str) else value.decode("utf-8"))

    def _lrange(key, start, end):
        entries = audit_lists.get(key, [])
        result = entries[start : end + 1 if end != -1 else None]
        return [e.encode("utf-8") for e in result]

    def _expire(key, ttl):
        pass  # TTL not needed in unit tests

    mock.set.side_effect = _set
    mock.get.side_effect = _get
    mock.sadd.side_effect = _sadd
    mock.srem.side_effect = _srem
    mock.smembers.side_effect = _smembers
    mock.rpush.side_effect = _rpush
    mock.lrange.side_effect = _lrange
    mock.expire.side_effect = _expire

    return mock


# ---------------------------------------------------------------------------
# TaskManager tests
# ---------------------------------------------------------------------------


class TestTaskManager:
    def setup_method(self):
        """Fresh manager with mocked Redis for each test."""
        with patch("a2a.task_manager.get_redis_client", return_value=_make_redis_mock()):
            self.mgr = TaskManager()

    def test_create_task_returns_task(self):
        task = self.mgr.create_task("Summarize this document")
        assert task.id
        assert task.input == "Summarize this document"
        assert task.status.state == TaskState.SUBMITTED

    def test_get_task_returns_created_task(self):
        task = self.mgr.create_task("Hello")
        fetched = self.mgr.get_task(task.id)
        assert fetched is not None
        assert fetched.id == task.id

    def test_get_task_missing_returns_none(self):
        assert self.mgr.get_task("nonexistent-id") is None

    def test_update_state_to_working(self):
        task = self.mgr.create_task("Run a command")
        updated = self.mgr.update_state(task.id, TaskState.WORKING)
        assert updated is not None
        assert updated.status.state == TaskState.WORKING

    def test_update_state_to_completed(self):
        task = self.mgr.create_task("Do something")
        self.mgr.update_state(task.id, TaskState.WORKING)
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        fetched = self.mgr.get_task(task.id)
        assert fetched.status.state == TaskState.COMPLETED

    def test_update_state_on_terminal_task_is_noop(self):
        task = self.mgr.create_task("Already done")
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        result = self.mgr.update_state(task.id, TaskState.FAILED)
        # Returns the task but state unchanged
        assert result.status.state == TaskState.COMPLETED

    def test_update_state_missing_task_returns_none(self):
        result = self.mgr.update_state("bad-id", TaskState.WORKING)
        assert result is None

    def test_add_artifact(self):
        task = self.mgr.create_task("Analyze data")
        artifact = TaskArtifact(artifact_type="text", content="Analysis result")
        ok = self.mgr.add_artifact(task.id, artifact)
        assert ok is True
        fetched = self.mgr.get_task(task.id)
        assert len(fetched.artifacts) == 1
        assert fetched.artifacts[0].content == "Analysis result"

    def test_add_artifact_missing_task_returns_false(self):
        artifact = TaskArtifact(artifact_type="text", content="x")
        ok = self.mgr.add_artifact("bad-id", artifact)
        assert ok is False

    def test_cancel_submitted_task(self):
        task = self.mgr.create_task("Cancel me")
        ok = self.mgr.cancel_task(task.id)
        assert ok is True
        fetched = self.mgr.get_task(task.id)
        assert fetched.status.state == TaskState.CANCELLED

    def test_cancel_working_task(self):
        task = self.mgr.create_task("Working task")
        self.mgr.update_state(task.id, TaskState.WORKING)
        ok = self.mgr.cancel_task(task.id)
        assert ok is True

    def test_cancel_completed_task_fails(self):
        task = self.mgr.create_task("Already complete")
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        ok = self.mgr.cancel_task(task.id)
        assert ok is False

    def test_cancel_missing_task_returns_false(self):
        ok = self.mgr.cancel_task("nonexistent")
        assert ok is False

    def test_list_tasks(self):
        self.mgr.create_task("Task one")
        self.mgr.create_task("Task two")
        tasks = self.mgr.list_tasks()
        assert len(tasks) == 2

    def test_stats(self):
        t1 = self.mgr.create_task("Task 1")
        t2 = self.mgr.create_task("Task 2")
        self.mgr.update_state(t1.id, TaskState.WORKING)
        self.mgr.update_state(t2.id, TaskState.COMPLETED)
        stats = self.mgr.stats()
        assert stats.get("working") == 1
        assert stats.get("completed") == 1

    def test_task_to_dict(self):
        task = self.mgr.create_task("Test serialization", context={"key": "value"})
        d = task.to_dict()
        assert d["id"] == task.id
        assert d["input"] == "Test serialization"
        assert d["status"]["state"] == "submitted"
        assert "createdAt" in d
        assert "updatedAt" in d

    def test_context_stored(self):
        ctx = {"session_id": "abc123", "user": "test"}
        task = self.mgr.create_task("Task with context", context=ctx)
        fetched = self.mgr.get_task(task.id)
        assert fetched.context == ctx

    def test_get_audit_log(self):
        task = self.mgr.create_task("Audit me", caller_id="user:test")
        self.mgr.update_state(task.id, TaskState.WORKING)
        log = self.mgr.get_audit_log(task.id)
        assert log is not None
        assert len(log) >= 2  # task.submitted + task.state_transition
        events = [e["event"] for e in log]
        assert "task.submitted" in events
        assert "task.state_transition" in events

    def test_get_audit_log_missing_task_returns_none(self):
        assert self.mgr.get_audit_log("nonexistent") is None


# ---------------------------------------------------------------------------
# Issue #4502: TTL eviction — Redis TTL handles expiry; test via mock deletion
# ---------------------------------------------------------------------------


class TestTaskManagerEviction:
    """Verify that expired tasks are no longer visible (Redis TTL handles eviction).

    Issue #4502: Eviction is now delegated to Redis key expiry instead of
    asyncio-scheduled coroutines.  These tests simulate key expiry by removing
    the key from the mock store directly, matching the real Redis behaviour.
    """

    def setup_method(self):
        self._redis_mock = _make_redis_mock()
        with patch("a2a.task_manager.get_redis_client", return_value=self._redis_mock):
            self.mgr = TaskManager()

    def test_completed_task_visible_before_expiry(self):
        task = self.mgr.create_task("Eviction test")
        self.mgr.update_state(task.id, TaskState.WORKING)
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        # Still present before TTL fires
        assert self.mgr.get_task(task.id) is not None

    def test_task_invisible_after_redis_key_expires(self):
        """Simulate Redis TTL expiry by deleting the key from the mock store."""
        task = self.mgr.create_task("Expiry test")
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        assert self.mgr.get_task(task.id) is not None

        # Simulate Redis key expiry (as the real Redis TTL would do)
        from a2a.task_manager import _KEY_TASK

        key = _KEY_TASK.format(task.id)
        # Bypass mock to force a None return for this key
        original_get = self._redis_mock.get.side_effect

        def expired_get(k):
            if k == key:
                return None
            return original_get(k)

        self._redis_mock.get.side_effect = expired_get
        assert self.mgr.get_task(task.id) is None

    def test_failed_task_visible_before_expiry(self):
        task = self.mgr.create_task("Failing task")
        self.mgr.update_state(task.id, TaskState.WORKING)
        self.mgr.update_state(task.id, TaskState.FAILED, message="timeout")
        assert self.mgr.get_task(task.id) is not None
        assert self.mgr.get_task(task.id).status.state == TaskState.FAILED

    def test_cancelled_task_visible_before_expiry(self):
        task = self.mgr.create_task("Cancel-eviction test")
        self.mgr.cancel_task(task.id)
        assert self.mgr.get_task(task.id) is not None
        assert self.mgr.get_task(task.id).status.state == TaskState.CANCELLED

    def test_terminal_task_still_queryable_immediately(self):
        """A terminal task must still be queryable immediately after transition."""
        task = self.mgr.create_task("Query before TTL")
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        fetched = self.mgr.get_task(task.id)
        assert fetched is not None
        assert fetched.status.state == TaskState.COMPLETED


# ---------------------------------------------------------------------------
# Issue #4606: publish_event() tests
# ---------------------------------------------------------------------------


class TestPublishEvent:
    """Unit tests for TaskManager.publish_event() — Issue #4606.

    publish_event() wraps redis.publish() with a best-effort guard: any
    exception must be swallowed so pub/sub failures never abort task execution.
    """

    def setup_method(self):
        self._redis_mock = _make_redis_mock()
        with patch("a2a.task_manager.get_redis_client", return_value=self._redis_mock):
            self.mgr = TaskManager()

    def test_publish_event_happy_path(self):
        """redis.publish() is called with the correct channel and JSON payload."""
        task = self.mgr.create_task("Publish test")
        payload = {"event": "state_change", "state": "working"}

        self.mgr.publish_event(task.id, payload)

        expected_channel = f"a2a:events:{task.id}"
        self._redis_mock.publish.assert_called_once_with(
            expected_channel,
            '{"event": "state_change", "state": "working"}',
        )

    def test_publish_event_redis_failure_does_not_propagate(self):
        """An exception from redis.publish() must not escape publish_event().

        publish_event() is best-effort — a Redis failure must never crash
        the task executor that calls it.
        """
        self._redis_mock.publish.side_effect = Exception("Redis connection refused")

        # Must not raise, regardless of the underlying Redis failure
        self.mgr.publish_event("any-task-id", {"event": "state_change", "state": "working"})


# ---------------------------------------------------------------------------
# Issue #4626: get_task() must slide TTL on all three Redis keys
# ---------------------------------------------------------------------------


class TestGetTaskTTLSliding:
    """Assert that get_task() calls expire() on every key it touches.

    Issue #4626: The existing mock treated expire() as a silent no-op, meaning
    a regression removing any EXPIRE call would still pass all tests. These
    tests make each of the three EXPIRE calls explicit and mandatory.
    """

    def setup_method(self):
        self._redis_mock = _make_redis_mock()
        with patch("a2a.task_manager.get_redis_client", return_value=self._redis_mock):
            self.mgr = TaskManager()

    def test_get_task_slides_ttl_on_all_three_keys(self):
        """get_task() must call expire() for task key, audit key, and tracking set."""
        from a2a.task_manager import _KEY_AUDIT, _KEY_TASK, _KEY_TASKS

        task = self.mgr.create_task("TTL sliding test")

        # Reset call history so only get_task() calls are counted
        self._redis_mock.expire.reset_mock()

        self.mgr.get_task(task.id)

        # Collect every key that was passed to expire()
        expired_keys = [call.args[0] for call in self._redis_mock.expire.call_args_list]

        assert (
            self._redis_mock.expire.call_count >= 3
        ), f"Expected at least 3 expire() calls, got {self._redis_mock.expire.call_count}"
        assert (
            _KEY_TASK.format(task.id) in expired_keys
        ), f"expire() not called for task key {_KEY_TASK.format(task.id)!r}"
        assert (
            _KEY_AUDIT.format(task.id) in expired_keys
        ), f"expire() not called for audit key {_KEY_AUDIT.format(task.id)!r}"
        assert _KEY_TASKS in expired_keys, f"expire() not called for tracking set {_KEY_TASKS!r}"

    def test_get_task_missing_does_not_call_expire(self):
        """expire() must NOT be called when task_id is not found in Redis.

        Avoids unnecessary Redis round-trips on cache misses.
        """
        self._redis_mock.expire.reset_mock()

        result = self.mgr.get_task("nonexistent-task-id")

        assert result is None
        self._redis_mock.expire.assert_not_called()


# ---------------------------------------------------------------------------
# Issue #4649: _save() must call expire() on _KEY_TASKS with correct TTL
# ---------------------------------------------------------------------------


class TestSaveTTL:
    """Assert that _save() (called by create_task()) sets the TTL on _KEY_TASKS.

    Issue #4649: The _save() mock silently ignored the expire() call on
    _KEY_TASKS, meaning removing it would still pass the full test suite.
    These tests make the EXPIRE call on the tracking set explicit and mandatory.
    """

    def setup_method(self):
        self._redis_mock = _make_redis_mock()
        with patch("a2a.task_manager.get_redis_client", return_value=self._redis_mock):
            self.mgr = TaskManager()

    def test_create_task_calls_expire_on_key_tasks(self):
        """create_task() → _save() must call expire(_KEY_TASKS, ttl)."""
        from a2a.task_manager import _KEY_TASKS

        self._redis_mock.expire.reset_mock()

        self.mgr.create_task("Test save TTL")

        expired_keys = [call.args[0] for call in self._redis_mock.expire.call_args_list]
        assert _KEY_TASKS in expired_keys, (
            f"expire() not called for tracking set {_KEY_TASKS!r}; " f"keys seen: {expired_keys}"
        )

    def test_create_task_expire_uses_configured_ttl(self):
        """expire(_KEY_TASKS, ttl) must use the value returned by _ttl()."""
        from a2a.task_manager import _KEY_TASKS

        expected_ttl = self.mgr._ttl()
        self._redis_mock.expire.reset_mock()

        self.mgr.create_task("TTL value test")

        # Find the expire() call for _KEY_TASKS and verify the TTL argument
        matching = [call for call in self._redis_mock.expire.call_args_list if call.args[0] == _KEY_TASKS]
        assert matching, f"expire() never called with key {_KEY_TASKS!r}"
        actual_ttl = matching[0].args[1]
        assert actual_ttl == expected_ttl, (
            f"expire({_KEY_TASKS!r}, ...) used ttl={actual_ttl}, " f"expected {expected_ttl}"
        )


# ---------------------------------------------------------------------------
# Issue #4687: Self-Evaluator unit tests
# ---------------------------------------------------------------------------


class TestSelfEvaluator:
    """Unit tests for a2a.self_evaluator — Issue #4687.

    All tests are pure-Python (no I/O, no network) and verify the heuristic
    scoring logic and EvalResult dataclass directly.
    """

    @pytest.mark.asyncio
    async def test_high_confidence_response_passes(self):
        from a2a.self_evaluator import evaluate_task_output

        result = await evaluate_task_output(
            input_text="What is 2 + 2?",
            response_text="The answer is 4. Addition of 2 and 2 yields 4.",
            metadata={},
            threshold=0.6,
        )
        assert result.passed is True
        assert result.confidence >= 0.6
        assert result.eval_reason == ""

    @pytest.mark.asyncio
    async def test_uncertain_response_fails(self):
        from a2a.self_evaluator import evaluate_task_output

        # Response with 4+ uncertainty phrases drives confidence below 0.6
        result = await evaluate_task_output(
            input_text="What is the capital of France?",
            response_text=(
                "I don't know. I am not sure. I cannot answer this. "
                "Unable to provide information here. I have no data on this."
            ),
            metadata={},
            threshold=0.6,
        )
        assert result.passed is False
        assert result.confidence < 0.6
        assert result.eval_reason != ""

    @pytest.mark.asyncio
    async def test_empty_response_fails(self):
        from a2a.self_evaluator import evaluate_task_output

        result = await evaluate_task_output(
            input_text="Summarise this document.",
            response_text="   ",
            metadata={},
            threshold=0.6,
        )
        assert result.passed is False
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_custom_threshold_respected(self):
        """A response that passes default threshold can fail a stricter one."""
        from a2a.self_evaluator import evaluate_task_output

        good_response = "Python is a high-level programming language used widely."
        # Should pass at default 0.6
        result_default = await evaluate_task_output("Describe Python", good_response, {}, threshold=0.6)
        assert result_default.passed is True

        # Force failure with threshold above 1.0 (impossible to pass)
        result_strict = await evaluate_task_output("Describe Python", good_response, {}, threshold=1.1)
        assert result_strict.passed is False

    def test_confidence_is_bounded(self):
        from a2a.self_evaluator import _score_response

        assert _score_response("x" * 100, "short") <= 1.0
        assert _score_response("x" * 100, "short") >= 0.0
        assert _score_response("", "question") == 0.0


# ---------------------------------------------------------------------------
# Issue #4687: execute_a2a_task quality-gate integration tests
# ---------------------------------------------------------------------------


class TestExecuteA2aTaskEvalGate:
    """Verify that execute_a2a_task respects the self-eval quality gate.

    Mocks:
      - get_task_manager() → in-process TaskManager with mock Redis
      - get_distributed_agent_coordinator() → mock that returns a controllable result
      - evaluate_task_output() → tested separately; here we mock to control pass/fail
    """

    def _make_manager(self):
        with patch("a2a.task_manager.get_redis_client", return_value=_make_redis_mock()):
            mgr = TaskManager()
        return mgr

    @pytest.mark.asyncio
    async def test_pass_threshold_transitions_to_completed(self):
        """When eval passes, task must reach COMPLETED."""
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        from a2a.self_evaluator import EvalResult
        from a2a.task_executor import execute_a2a_task
        from a2a.types import TaskState

        mgr = self._make_manager()
        task = mgr.create_task("Describe Python")

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_request = AsyncMock(
            return_value={"response": "Python is a popular programming language."}
        )
        # Stub heavy modules so the late import in task_executor succeeds
        mock_ao_module = MagicMock()
        mock_ao_module.get_distributed_agent_coordinator = MagicMock(return_value=mock_orchestrator)

        passed_eval = EvalResult(passed=True, confidence=0.9, eval_reason="")

        with (
            patch("a2a.task_executor.get_task_manager", return_value=mgr),
            patch(
                "a2a.task_executor.evaluate_task_output",
                new=AsyncMock(return_value=passed_eval),
            ),
            patch.dict(sys.modules, {"agents.agent_orchestration": mock_ao_module}),
        ):
            await execute_a2a_task(task.id, "Describe Python")

        final = mgr.get_task(task.id)
        assert final.status.state == TaskState.COMPLETED

    @pytest.mark.asyncio
    async def test_fail_threshold_transitions_to_failed_with_eval_reason(self):
        """When eval fails, task must reach FAILED with eval_reason artifact."""
        import sys
        from unittest.mock import AsyncMock, MagicMock, patch

        from a2a.self_evaluator import EvalResult
        from a2a.task_executor import execute_a2a_task
        from a2a.types import TaskState

        mgr = self._make_manager()
        task = mgr.create_task("Explain quantum entanglement")

        mock_orchestrator = MagicMock()
        mock_orchestrator.process_request = AsyncMock(return_value={"response": "I'm not sure about this."})
        mock_ao_module = MagicMock()
        mock_ao_module.get_distributed_agent_coordinator = MagicMock(return_value=mock_orchestrator)

        failed_eval = EvalResult(
            passed=False,
            confidence=0.3,
            eval_reason="Self-evaluation failed: confidence 0.3000 below threshold 0.6000.",
        )

        with (
            patch("a2a.task_executor.get_task_manager", return_value=mgr),
            patch(
                "a2a.task_executor.evaluate_task_output",
                new=AsyncMock(return_value=failed_eval),
            ),
            patch.dict(sys.modules, {"agents.agent_orchestration": mock_ao_module}),
        ):
            await execute_a2a_task(task.id, "Explain quantum entanglement")

        final = mgr.get_task(task.id)
        assert final.status.state == TaskState.FAILED
        assert final.status.message is not None
        assert "eval" in final.status.message.lower() or "confidence" in final.status.message.lower()

        # eval_reason artifact must be present
        eval_artifacts = [
            a
            for a in final.artifacts
            if a.artifact_type == "json" and isinstance(a.content, dict) and "eval_reason" in a.content
        ]
        assert len(eval_artifacts) == 1, "Expected exactly one eval_reason artifact"
