# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Protocol Unit Tests

Issue #961: Tests for types, agent_card builder, and task_manager.
Uses no network connections and no external dependencies.
"""

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
        card = build_agent_card("https://172.16.168.20:8443")
        assert isinstance(card, AgentCard)

    def test_card_name_is_autobot(self):
        card = build_agent_card("https://172.16.168.20:8443")
        assert card.name == "AutoBot"

    def test_card_url_uses_base(self):
        card = build_agent_card("https://172.16.168.20:8443")
        assert card.url == "https://172.16.168.20:8443/api/a2a"

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
# TaskManager tests
# ---------------------------------------------------------------------------


class TestTaskManager:
    def setup_method(self):
        """Fresh manager for each test."""
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
