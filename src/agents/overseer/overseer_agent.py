# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Overseer Agent

Decomposes user queries into sequential executable tasks.
Each task is then delegated to a StepExecutorAgent for execution.

Responsibilities:
- Analyze user queries to understand intent
- Decompose complex queries into sequential steps
- Create task plans with proper dependencies
- Orchestrate step-by-step execution
"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from backend.dependencies import global_config_manager
from src.utils.http_client import get_http_client

from .types import (
    AgentTask,
    OverseerUpdate,
    StepResult,
    StepStatus,
    TaskPlan,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class OverseerAgent:
    """
    Decomposes user queries into sequential executable tasks.

    The Overseer analyzes user intent and creates a TaskPlan containing
    ordered AgentTasks that are executed one at a time by StepExecutorAgents.
    """

    def __init__(self, session_id: str):
        """
        Initialize the OverseerAgent.

        Args:
            session_id: The chat session ID for context
        """
        self.session_id = session_id
        self.current_plan: Optional[TaskPlan] = None
        self._http_client = None

    def _get_http_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = get_http_client()
        return self._http_client

    def _get_ollama_endpoint(self) -> str:
        """Get Ollama endpoint from config."""
        try:
            endpoint = global_config_manager.get_ollama_url()
            if not endpoint.endswith("/api/generate"):
                endpoint = endpoint.rstrip("/") + "/api/generate"
            return endpoint
        except Exception as e:
            logger.error("Failed to get Ollama endpoint: %s", e)
            from src.unified_config_manager import UnifiedConfigManager

            config = UnifiedConfigManager()
            return f"http://{config.get_host('ollama')}:{config.get_port('ollama')}/api/generate"

    def _get_model(self) -> str:
        """Get LLM model from config."""
        try:
            return global_config_manager.get_selected_model()
        except Exception:
            return "qwen3:14b"

    async def analyze_query(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> TaskPlan:
        """
        Analyze a user query and create a task plan.

        Args:
            query: The user's question or request
            context: Optional context (conversation history, system state, etc.)

        Returns:
            TaskPlan with decomposed steps
        """
        logger.info("[OverseerAgent] Analyzing query: %s", query[:100])

        # Build the decomposition prompt
        prompt = self._build_decomposition_prompt(query, context)

        try:
            # Call LLM for task decomposition
            response = await self._call_llm(prompt)
            plan = self._parse_task_plan(response, query)

            self.current_plan = plan
            logger.info(
                "[OverseerAgent] Created plan with %d steps: %s",
                len(plan.steps),
                plan.plan_id,
            )

            return plan

        except Exception as e:
            logger.error("[OverseerAgent] Failed to analyze query: %s", e)
            # Create a simple single-step fallback plan
            return self._create_fallback_plan(query)

    def _build_decomposition_prompt(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build the prompt for task decomposition."""
        context_info = ""
        if context:
            if context.get("conversation_history"):
                recent = context["conversation_history"][-3:]
                context_info = "\nRecent conversation:\n"
                for msg in recent:
                    if "user" in msg:
                        context_info += f"User: {msg['user']}\n"
                    if "assistant" in msg:
                        context_info += f"Assistant: {msg['assistant']}\n"

        return f"""You are a task planning assistant. Analyze the user's query and break it down into executable steps.

User Query: {query}
{context_info}

Provide your response in this exact JSON format:
{{
  "analysis": "Brief explanation of how you'll approach this query (1-2 sentences)",
  "steps": [
    {{
      "description": "What this step accomplishes",
      "command": "The exact shell command to run (or null if not a command)",
      "expected_outcome": "What we expect to see/learn from this step"
    }}
  ]
}}

Rules:
1. Break down the query into 1-5 logical steps
2. Each step should be atomic and focused on one action
3. For system queries, use appropriate Linux commands
4. Order steps logically (dependencies first)
5. Include commands like: ip, nmap, netstat, ss, cat, ls, grep, etc.
6. For questions about the network, start with checking local interfaces
7. Keep it practical - don't overcomplicate simple queries
8. Response must be valid JSON only, no other text

Examples:
- "what devices are on my network" → Steps: 1) Check network interfaces 2) Scan for devices
- "show disk usage" → Steps: 1) Run df -h command
- "find large files" → Steps: 1) Find files over certain size"""

    async def _call_llm(self, prompt: str) -> str:
        """Make LLM API call and return response text."""
        endpoint = self._get_ollama_endpoint()
        model = self._get_model()

        http_client = self._get_http_client()
        response = await http_client.post_json(
            endpoint,
            json_data={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.4,  # Balanced for planning
                    "top_p": 0.9,
                    "num_ctx": 4096,
                },
            },
        )

        return response.get("response", "")

    def _parse_task_plan(self, response: str, original_query: str) -> TaskPlan:
        """Parse LLM response into a TaskPlan."""
        try:
            data = self._extract_json(response)

            steps = []
            raw_steps = data.get("steps", [])
            total_steps = len(raw_steps)

            for i, step_data in enumerate(raw_steps, 1):
                task = AgentTask(
                    task_id=f"task_{uuid.uuid4().hex[:8]}",
                    step_number=i,
                    total_steps=total_steps,
                    description=step_data.get("description", f"Step {i}"),
                    command=step_data.get("command"),
                    expected_outcome=step_data.get("expected_outcome"),
                    status=StepStatus.PENDING,
                )
                steps.append(task)

            return TaskPlan(
                plan_id=f"plan_{uuid.uuid4().hex[:8]}",
                original_query=original_query,
                analysis=data.get("analysis", "Executing your request step by step."),
                steps=steps,
            )

        except Exception as e:
            logger.warning("[OverseerAgent] Failed to parse plan: %s", e)
            return self._create_fallback_plan(original_query)

    def _create_fallback_plan(self, query: str) -> TaskPlan:
        """Create a simple fallback plan for unparseable queries."""
        # Try to extract a simple command from the query
        task = AgentTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            step_number=1,
            total_steps=1,
            description=f"Execute query: {query}",
            command=None,  # Will need manual intervention
            expected_outcome="Complete the requested action",
            status=StepStatus.PENDING,
        )

        return TaskPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            original_query=query,
            analysis="Processing your request directly.",
            steps=[task],
        )

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response text."""
        # Try direct parse first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON in the response
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError("Could not extract JSON from response")

    async def orchestrate_execution(
        self, plan: TaskPlan, executor
    ) -> AsyncGenerator[OverseerUpdate, None]:
        """
        Orchestrate the execution of a task plan.

        Yields updates as each step progresses through execution.

        Args:
            plan: The TaskPlan to execute
            executor: A StepExecutorAgent instance to execute steps

        Yields:
            OverseerUpdate objects for real-time progress tracking
        """
        logger.info("[OverseerAgent] Starting execution of plan: %s", plan.plan_id)

        # Yield the plan update
        yield OverseerUpdate(
            update_type="plan",
            plan_id=plan.plan_id,
            total_steps=len(plan.steps),
            content={
                "analysis": plan.analysis,
                "steps": [
                    {"step_number": s.step_number, "description": s.description}
                    for s in plan.steps
                ],
            },
        )

        # Execute each step in sequence
        # Track completed step results for dependency resolution
        completed_results: Dict[str, StepResult] = {}

        for task in plan.steps:
            # Check dependencies - ensure all required previous steps completed
            if task.dependencies:
                missing_deps = [
                    dep for dep in task.dependencies if dep not in completed_results
                ]
                if missing_deps:
                    logger.error(
                        "[OverseerAgent] Step %d has unmet dependencies: %s",
                        task.step_number, missing_deps
                    )
                    yield OverseerUpdate(
                        update_type="error",
                        plan_id=plan.plan_id,
                        task_id=task.task_id,
                        step_number=task.step_number,
                        total_steps=task.total_steps,
                        status="failed",
                        content={"error": f"Unmet dependencies: {missing_deps}"},
                    )
                    continue

            # Gather context from previous steps for this task
            previous_context = {}
            if task.step_number > 1:
                # Get outputs from all previous steps as context
                for prev_task_id, prev_result in completed_results.items():
                    if prev_result.output:
                        previous_context[prev_task_id] = {
                            "command": prev_result.command,
                            "output": prev_result.output,
                            "return_code": prev_result.return_code,
                        }

            # Yield step start with dependency context
            yield OverseerUpdate(
                update_type="step_start",
                plan_id=plan.plan_id,
                task_id=task.task_id,
                step_number=task.step_number,
                total_steps=task.total_steps,
                status="executing",
                content={
                    "description": task.description,
                    "command": task.command,
                    "previous_context": previous_context if previous_context else None,
                },
            )

            step_result: Optional[StepResult] = None

            try:
                # Execute the step through the executor
                # The executor will yield stream chunks for long-running commands
                async for update in executor.execute_step(task):
                    if isinstance(update, StepResult):
                        # Step completed - store result for dependencies
                        step_result = update
                        completed_results[task.task_id] = update

                        yield OverseerUpdate(
                            update_type="step_complete",
                            plan_id=plan.plan_id,
                            task_id=task.task_id,
                            step_number=task.step_number,
                            total_steps=task.total_steps,
                            status=update.status.value,
                            content=update.to_dict(),
                        )
                    else:
                        # Streaming update
                        yield OverseerUpdate(
                            update_type="stream",
                            plan_id=plan.plan_id,
                            task_id=task.task_id,
                            step_number=task.step_number,
                            total_steps=task.total_steps,
                            status="streaming",
                            content=update.to_dict()
                            if hasattr(update, "to_dict")
                            else update,
                        )

            except Exception as e:
                logger.error(
                    "[OverseerAgent] Step %d failed: %s", task.step_number, e
                )
                yield OverseerUpdate(
                    update_type="error",
                    plan_id=plan.plan_id,
                    task_id=task.task_id,
                    step_number=task.step_number,
                    total_steps=task.total_steps,
                    status="failed",
                    content={"error": str(e)},
                )
                # Continue to next step or abort based on error severity
                # For now, we continue

        logger.info("[OverseerAgent] Completed execution of plan: %s", plan.plan_id)

    def get_plan_summary(self) -> Optional[str]:
        """Get a summary of the current plan."""
        if not self.current_plan:
            return None

        summary_parts = [f"Plan: {self.current_plan.analysis}"]
        for step in self.current_plan.steps:
            status_icon = {
                StepStatus.PENDING: "⏳",
                StepStatus.RUNNING: "🔄",
                StepStatus.STREAMING: "📡",
                StepStatus.COMPLETED: "✅",
                StepStatus.FAILED: "❌",
            }.get(step.status, "•")

            summary_parts.append(
                f"{status_icon} Step {step.step_number}: {step.description}"
            )

        return "\n".join(summary_parts)
