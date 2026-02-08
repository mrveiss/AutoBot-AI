# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #657 - Subordinate Agent Delegation.

Tests verify:
1. AgentContext hierarchy management
2. HierarchicalAgent delegation functionality
3. Max depth enforcement
4. Parallel delegation
5. DelegateTool integration
"""

import asyncio

import pytest
from agents.hierarchical_agent import HierarchicalAgent
from chat_workflow.models import AgentContext
from tools.delegate_tool import DelegateTool
from utils.errors import RepairableException


class TestAgentContext:
    """Test AgentContext dataclass functionality."""

    def test_default_creation(self):
        """Test default context creation."""
        ctx = AgentContext(agent_id="test-agent")
        assert ctx.agent_id == "test-agent"
        assert ctx.level == 0
        assert ctx.parent_id is None
        assert ctx.max_depth == 3
        assert ctx.can_delegate() is True

    def test_root_can_delegate(self):
        """Root agent should be able to delegate."""
        ctx = AgentContext(agent_id="root", level=0)
        assert ctx.can_delegate() is True

    def test_at_max_depth_cannot_delegate(self):
        """Agent at max depth should not be able to delegate."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)
        assert ctx.can_delegate() is False

    def test_create_subordinate_context(self):
        """create_subordinate_context should create proper child context."""
        parent = AgentContext(agent_id="parent", level=0, session_id="session-123")
        child = parent.create_subordinate_context("child-id")

        assert child.agent_id == "child-id"
        assert child.level == 1
        assert child.parent_id == "parent"
        assert child.session_id == "session-123"
        assert child.max_depth == 3  # Inherited

    def test_create_subordinate_at_max_depth_raises(self):
        """Creating subordinate at max depth should raise ValueError."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)

        with pytest.raises(ValueError, match="Cannot delegate"):
            ctx.create_subordinate_context("child")

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        ctx = AgentContext(
            agent_id="test",
            level=1,
            parent_id="parent",
            max_depth=5,
            session_id="session",
        )
        d = ctx.to_dict()

        assert d["agent_id"] == "test"
        assert d["level"] == 1
        assert d["parent_id"] == "parent"
        assert d["max_depth"] == 5
        assert d["session_id"] == "session"
        assert d["can_delegate"] is True


class TestHierarchicalAgent:
    """Test HierarchicalAgent delegation functionality."""

    def test_agent_creation(self):
        """Test agent initialization."""
        ctx = AgentContext(agent_id="test", level=0)
        agent = HierarchicalAgent(context=ctx)

        assert agent.context == ctx
        assert len(agent.subordinates) == 0
        assert len(agent.history) == 0

    @pytest.mark.asyncio
    async def test_delegate_creates_subordinate(self):
        """delegate() should create a subordinate agent."""
        ctx = AgentContext(agent_id="root", level=0)

        # Mock task callback
        async def mock_callback(task, agent):
            return f"Executed: {task}"

        agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)

        result = await agent.delegate(
            task="Test subtask",
            reason="Testing",
        )

        assert result.success is True
        assert "Executed: Test subtask" in result.result
        assert len(agent.subordinates) == 1

    @pytest.mark.asyncio
    async def test_delegate_increments_level(self):
        """Subordinates should have incremented level."""
        ctx = AgentContext(agent_id="root", level=0)

        async def mock_callback(task, agent):
            return f"Level: {agent.context.level}"

        agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)
        result = await agent.delegate(task="Check level", reason="Test")

        assert result.success is True
        assert "Level: 1" in result.result

    @pytest.mark.asyncio
    async def test_delegate_at_max_depth_raises(self):
        """Delegation at max depth should raise RepairableException."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)
        agent = HierarchicalAgent(context=ctx)

        with pytest.raises(RepairableException, match="Maximum delegation depth"):
            await agent.delegate(task="Too deep", reason="Test")

    @pytest.mark.asyncio
    async def test_delegate_records_history(self):
        """Delegation should be recorded in history."""
        ctx = AgentContext(agent_id="root", level=0)

        async def mock_callback(task, agent):
            return "Done"

        agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)
        await agent.delegate(task="Record me", reason="History test")

        assert len(agent.history) >= 1
        delegation_entry = next(
            (h for h in agent.history if h["action"] == "delegate"), None
        )
        assert delegation_entry is not None
        assert delegation_entry["task"] == "Record me"
        assert delegation_entry["reason"] == "History test"

    @pytest.mark.asyncio
    async def test_execute_with_callback(self):
        """execute() should call the task callback."""
        ctx = AgentContext(agent_id="test", level=0)

        async def mock_callback(task, agent):
            return f"Processed: {task}"

        agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)
        result = await agent.execute("My task")

        assert result == "Processed: My task"

    @pytest.mark.asyncio
    async def test_execute_without_callback(self):
        """execute() without callback should return acknowledgment."""
        ctx = AgentContext(agent_id="test", level=0)
        agent = HierarchicalAgent(context=ctx)

        result = await agent.execute("My task")

        assert "Task received" in result
        assert "level 0" in result

    @pytest.mark.asyncio
    async def test_delegate_parallel(self):
        """delegate_parallel() should execute tasks concurrently."""
        ctx = AgentContext(agent_id="root", level=0)

        execution_order = []

        async def mock_callback(task, agent):
            execution_order.append(task)
            await asyncio.sleep(0.01)  # Small delay to test concurrency
            return f"Done: {task}"

        agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)

        tasks = [
            {"task": "Task A", "reason": "Parallel test"},
            {"task": "Task B", "reason": "Parallel test"},
            {"task": "Task C", "reason": "Parallel test"},
        ]

        results = await agent.delegate_parallel(tasks)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(agent.subordinates) == 3

    @pytest.mark.asyncio
    async def test_delegate_parallel_at_max_depth(self):
        """delegate_parallel() at max depth should raise."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)
        agent = HierarchicalAgent(context=ctx)

        with pytest.raises(RepairableException):
            await agent.delegate_parallel([{"task": "A", "reason": "Test"}])

    def test_get_statistics(self):
        """get_statistics() should return correct counts."""
        ctx = AgentContext(agent_id="test", level=0)
        agent = HierarchicalAgent(context=ctx)

        # Add some history entries
        agent.history = [
            {"action": "delegate", "task": "Task 1"},
            {"action": "delegate", "task": "Task 2"},
            {"action": "execute", "task": "Task 3"},
        ]

        stats = agent.get_statistics()

        assert stats["delegation_count"] == 2
        assert stats["execution_count"] == 1
        assert stats["level"] == 0

    def test_to_dict(self):
        """to_dict() should serialize agent state."""
        ctx = AgentContext(agent_id="test", level=1, parent_id="parent")
        agent = HierarchicalAgent(context=ctx)

        d = agent.to_dict()

        assert d["context"]["agent_id"] == "test"
        assert d["context"]["level"] == 1
        assert d["subordinate_ids"] == []


class TestDelegateTool:
    """Test DelegateTool functionality."""

    def test_tool_definition(self):
        """get_tool_definition() should return proper structure."""
        tool = DelegateTool()
        definition = tool.get_tool_definition()

        assert definition["name"] == "delegate"
        assert "parameters" in definition
        assert "task" in definition["parameters"]
        assert "reason" in definition["parameters"]

    def test_format_for_prompt(self):
        """format_for_prompt() should include syntax example."""
        tool = DelegateTool()
        prompt = tool.format_for_prompt()

        assert "TOOL_CALL" in prompt
        assert "delegate" in prompt
        assert "task" in prompt

    @pytest.mark.asyncio
    async def test_execute_without_agent(self):
        """execute() without hierarchical agent should fail gracefully."""
        tool = DelegateTool()

        response = await tool.execute(
            task="Test task",
            reason="Test reason",
        )

        assert response.success is False
        assert "not available" in response.message

    @pytest.mark.asyncio
    async def test_execute_with_agent(self):
        """execute() with hierarchical agent should delegate."""
        ctx = AgentContext(agent_id="test", level=0)

        async def mock_callback(task, agent):
            return f"Completed: {task}"

        hierarchical_agent = HierarchicalAgent(context=ctx, task_callback=mock_callback)
        tool = DelegateTool(hierarchical_agent=hierarchical_agent)

        response = await tool.execute(
            task="Delegated task",
            reason="Integration test",
        )

        assert response.success is True
        assert "Completed: Delegated task" in response.message
        assert response.subordinate_id is not None

    @pytest.mark.asyncio
    async def test_execute_at_max_depth(self):
        """execute() at max depth should return failure."""
        ctx = AgentContext(agent_id="deep", level=3, max_depth=3)
        hierarchical_agent = HierarchicalAgent(context=ctx)
        tool = DelegateTool(hierarchical_agent=hierarchical_agent)

        response = await tool.execute(
            task="Too deep",
            reason="Test",
        )

        assert response.success is False
        assert (
            "Maximum delegation depth" in response.message
            or "depth" in response.message.lower()
        )


class TestDelegationChain:
    """Test multi-level delegation chains."""

    @pytest.mark.asyncio
    async def test_two_level_delegation(self):
        """Test delegation from root to level 1 to level 2."""
        root_ctx = AgentContext(agent_id="root", level=0, max_depth=3)

        async def callback_with_subdelegation(task, agent):
            if agent.context.level < 2 and "sub" not in task:
                # Delegate further
                result = await agent.delegate(task=f"Sub-{task}", reason="Chain test")
                return f"Delegated and got: {result.result}"
            else:
                return f"Leaf executed: {task}"

        root = HierarchicalAgent(
            context=root_ctx, task_callback=callback_with_subdelegation
        )
        result = await root.delegate(task="Top task", reason="Chain test")

        assert result.success is True
        assert "Leaf executed" in result.result

    @pytest.mark.asyncio
    async def test_max_depth_enforced_in_chain(self):
        """Delegation chain should be limited by max_depth."""
        root_ctx = AgentContext(agent_id="root", level=0, max_depth=2)

        depth_reached = []

        async def recursive_delegate(task, agent):
            depth_reached.append(agent.context.level)
            if agent.context.can_delegate():
                result = await agent.delegate(
                    task=f"Level {agent.context.level + 1}", reason="Depth test"
                )
                return result.result
            else:
                return f"Max at level {agent.context.level}"

        root = HierarchicalAgent(context=root_ctx, task_callback=recursive_delegate)
        result = await root.delegate(task="Start", reason="Depth test")

        # With max_depth=2, should reach levels 1 and 2
        assert 1 in depth_reached
        assert 2 in depth_reached
        assert "Max at level 2" in result.result


class TestDelegationFailures:
    """Test delegation failure handling."""

    @pytest.mark.asyncio
    async def test_subordinate_failure_captured(self):
        """Failures in subordinates should be captured."""
        ctx = AgentContext(agent_id="root", level=0)

        async def failing_callback(task, agent):
            raise ValueError("Subordinate failed!")

        agent = HierarchicalAgent(context=ctx, task_callback=failing_callback)
        result = await agent.delegate(task="Will fail", reason="Failure test")

        assert result.success is False
        assert result.error is not None
        assert "Subordinate failed!" in result.error

    @pytest.mark.asyncio
    async def test_parallel_partial_failure(self):
        """Some tasks failing shouldn't prevent others from completing."""
        ctx = AgentContext(agent_id="root", level=0)

        async def sometimes_failing_callback(task, agent):
            if "fail" in task.lower():
                raise ValueError("Intentional failure")
            return f"Success: {task}"

        agent = HierarchicalAgent(context=ctx, task_callback=sometimes_failing_callback)

        tasks = [
            {"task": "Good task 1", "reason": "Test"},
            {"task": "This will fail", "reason": "Test"},
            {"task": "Good task 2", "reason": "Test"},
        ]

        results = await agent.delegate_parallel(tasks)

        # Should have 3 results
        assert len(results) == 3

        # First and third should succeed
        assert results[0].success is True
        assert results[2].success is True

        # Second should fail
        assert results[1].success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
