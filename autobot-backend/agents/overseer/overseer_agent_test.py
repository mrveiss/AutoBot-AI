# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for OverseerAgent (#690)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.overseer.overseer_agent import (
    OverseerAgent,
    _build_error_update,
    _build_previous_context,
)
from agents.overseer.types import (
    AgentTask,
    OverseerUpdate,
    StepResult,
    StepStatus,
    TaskPlan,
)


@pytest.fixture()
def agent():
    """Create an OverseerAgent instance."""
    return OverseerAgent(session_id="test-session")


class TestBuildPreviousContext:
    """Tests for _build_previous_context module-level function."""

    def test_no_context_for_step_1(self):
        task = AgentTask(
            task_id="t1", step_number=1, total_steps=2, description="first"
        )
        result = _build_previous_context(task, {})
        assert result == {}

    def test_gathers_completed_results(self):
        task = AgentTask(
            task_id="t2", step_number=2, total_steps=2, description="second"
        )
        completed = {
            "t1": StepResult(
                task_id="t1",
                step_number=1,
                total_steps=2,
                status=StepStatus.COMPLETED,
                command="ls",
                output="file1\n",
                return_code=0,
            )
        }
        result = _build_previous_context(task, completed)
        assert "t1" in result
        assert result["t1"]["command"] == "ls"
        assert result["t1"]["output"] == "file1\n"
        assert result["t1"]["return_code"] == 0

    def test_skips_results_without_output(self):
        task = AgentTask(
            task_id="t2", step_number=2, total_steps=2, description="second"
        )
        completed = {
            "t1": StepResult(
                task_id="t1",
                step_number=1,
                total_steps=2,
                status=StepStatus.COMPLETED,
                output=None,
            )
        }
        result = _build_previous_context(task, completed)
        assert "t1" not in result


class TestBuildErrorUpdate:
    """Tests for _build_error_update module-level function."""

    def test_error_update_structure(self):
        task = AgentTask(task_id="t1", step_number=1, total_steps=3, description="test")
        update = _build_error_update("plan_1", task, "something broke")
        assert update.update_type == "error"
        assert update.plan_id == "plan_1"
        assert update.task_id == "t1"
        assert update.step_number == 1
        assert update.status == "failed"
        assert update.content == {"error": "something broke"}


class TestOverseerAgentInit:
    """Tests for OverseerAgent initialization."""

    def test_init(self, agent):
        assert agent.session_id == "test-session"
        assert agent.current_plan is None
        assert agent._http_client is None


class TestOverseerAgentConfig:
    """Tests for config retrieval methods."""

    @patch("agents.overseer.overseer_agent.global_config_manager")
    def test_get_ollama_endpoint(self, mock_config, agent):
        mock_config.get_ollama_url.return_value = "http://host:11434"
        endpoint = agent._get_ollama_endpoint()
        assert endpoint == "http://host:11434/api/generate"

    @patch("agents.overseer.overseer_agent.global_config_manager")
    def test_get_ollama_endpoint_already_has_suffix(self, mock_config, agent):
        mock_config.get_ollama_url.return_value = "http://host:11434/api/generate"
        endpoint = agent._get_ollama_endpoint()
        assert endpoint == "http://host:11434/api/generate"
        assert not endpoint.endswith("/api/generate/api/generate")

    @patch("agents.overseer.overseer_agent.global_config_manager")
    def test_get_model_from_config(self, mock_config, agent):
        mock_config.get_selected_model.return_value = "llama3:8b"
        assert agent._get_model() == "llama3:8b"

    @patch("agents.overseer.overseer_agent.global_config_manager")
    def test_get_model_fallback(self, mock_config, agent):
        mock_config.get_selected_model.side_effect = Exception("no config")
        assert agent._get_model() == "qwen3:14b"


class TestAnalyzeQuery:
    """Tests for query analysis and plan creation."""

    @pytest.mark.asyncio
    async def test_creates_plan(self, agent):
        llm_response = json.dumps(
            {
                "analysis": "Check disk usage",
                "steps": [
                    {
                        "description": "Run df",
                        "command": "df -h",
                        "expected_outcome": "Disk usage shown",
                    }
                ],
            }
        )
        agent._call_llm = AsyncMock(return_value=llm_response)

        plan = await agent.analyze_query("show disk usage")
        assert isinstance(plan, TaskPlan)
        assert len(plan.steps) == 1
        assert plan.steps[0].command == "df -h"

    @pytest.mark.asyncio
    async def test_stores_current_plan(self, agent):
        llm_response = json.dumps(
            {
                "analysis": "Test",
                "steps": [{"description": "Step 1", "command": "ls"}],
            }
        )
        agent._call_llm = AsyncMock(return_value=llm_response)

        await agent.analyze_query("list files")
        assert agent.current_plan is not None

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self, agent):
        agent._call_llm = AsyncMock(side_effect=Exception("LLM error"))

        plan = await agent.analyze_query("test query")
        assert isinstance(plan, TaskPlan)
        assert len(plan.steps) == 1
        assert "test query" in plan.steps[0].description


class TestPromptBuilding:
    """Tests for decomposition prompt building."""

    def test_basic_prompt(self, agent):
        prompt = agent._build_decomposition_prompt("find large files")
        assert "find large files" in prompt
        assert "JSON" in prompt

    def test_prompt_with_context(self, agent):
        context = {
            "conversation_history": [
                {"user": "hello"},
                {"assistant": "hi there"},
            ]
        }
        prompt = agent._build_decomposition_prompt("next step", context)
        assert "hello" in prompt
        assert "hi there" in prompt


class TestParsing:
    """Tests for response parsing."""

    def test_parse_task_plan_valid(self, agent):
        response = json.dumps(
            {
                "analysis": "Scan network",
                "steps": [
                    {"description": "Check interfaces", "command": "ip addr"},
                    {"description": "Scan network", "command": "nmap -sn 10.0.0.0/24"},
                ],
            }
        )
        plan = agent._parse_task_plan(response, "scan my network")
        assert plan.analysis == "Scan network"
        assert len(plan.steps) == 2
        assert plan.steps[0].step_number == 1
        assert plan.steps[1].step_number == 2

    def test_parse_task_plan_invalid_returns_fallback(self, agent):
        plan = agent._parse_task_plan("garbage text", "original query")
        assert len(plan.steps) == 1
        assert "original query" in plan.steps[0].description

    def test_create_fallback_plan(self, agent):
        plan = agent._create_fallback_plan("do something")
        assert len(plan.steps) == 1
        assert plan.steps[0].command is None
        assert "do something" in plan.steps[0].description


class TestExtractJson:
    """Tests for JSON extraction."""

    def test_direct_json(self, agent):
        data = agent._extract_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_embedded_json(self, agent):
        text = 'Here: {"a": 1, "b": 2} end'
        data = agent._extract_json(text)
        assert data["a"] == 1

    def test_raises_on_invalid(self, agent):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            agent._extract_json("no json")


class TestDependencyValidation:
    """Tests for task dependency validation."""

    def test_no_dependencies(self, agent):
        task = AgentTask(task_id="t1", step_number=1, total_steps=1, description="test")
        valid, error = agent._validate_task_dependencies(task, {}, "plan_1")
        assert valid is True
        assert error is None

    def test_met_dependencies(self, agent):
        task = AgentTask(
            task_id="t2",
            step_number=2,
            total_steps=2,
            description="test",
            dependencies=["t1"],
        )
        completed = {
            "t1": StepResult(
                task_id="t1",
                step_number=1,
                total_steps=2,
                status=StepStatus.COMPLETED,
            )
        }
        valid, error = agent._validate_task_dependencies(task, completed, "plan_1")
        assert valid is True
        assert error is None

    def test_unmet_dependencies(self, agent):
        task = AgentTask(
            task_id="t2",
            step_number=2,
            total_steps=2,
            description="test",
            dependencies=["t1"],
        )
        valid, error = agent._validate_task_dependencies(task, {}, "plan_1")
        assert valid is False
        assert isinstance(error, OverseerUpdate)
        assert error.update_type == "error"


class TestOrchestrateExecution:
    """Tests for plan orchestration."""

    @pytest.mark.asyncio
    async def test_yields_plan_update_first(self, agent):
        step = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="test step",
            command="ls",
        )
        plan = TaskPlan(
            plan_id="plan_1",
            original_query="list files",
            analysis="Running ls",
            steps=[step],
        )

        async def mock_execute(task):
            yield StepResult(
                task_id=task.task_id,
                step_number=task.step_number,
                total_steps=task.total_steps,
                status=StepStatus.COMPLETED,
                command="ls",
            )

        mock_executor = MagicMock()
        mock_executor.execute_step = mock_execute

        updates = []
        async for update in agent.orchestrate_execution(plan, mock_executor):
            updates.append(update)

        assert updates[0].update_type == "plan"
        assert updates[0].plan_id == "plan_1"


class TestGetPlanSummary:
    """Tests for plan summary."""

    def test_no_plan_returns_none(self, agent):
        assert agent.get_plan_summary() is None

    def test_with_plan(self, agent):
        step = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="List files",
            status=StepStatus.COMPLETED,
        )
        agent.current_plan = TaskPlan(
            plan_id="plan_1",
            original_query="test",
            analysis="Test plan",
            steps=[step],
        )
        summary = agent.get_plan_summary()
        assert "Test plan" in summary
        assert "List files" in summary
