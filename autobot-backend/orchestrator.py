# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Orchestrator for AutoBot - Single Conductor

This module is the single authoritative orchestrator, consolidating all orchestrator
implementations:
- src/orchestrator.py (main orchestrator)
- src/enhanced_orchestrator.py (enhanced features, merged in #3393)
- chat_workflow/graph.py (LangGraph StateGraph — Issue #1043, replaces legacy LangChain)
- enhanced_orchestration/EnhancedMultiAgentOrchestrator (merged in #5040)

Refactored in #5058: god-class decomposed into collaborators.
  - WorkflowRunner  (orchestration/workflow_runner.py) — execution engine (#10666 B3 moved)
  - PerformanceTracker (orchestration/performance_tracker.py) — metrics
  - Three execution entry points unified: process_user_request → run_workflow
    → create_workflow_plan + WorkflowRunner.execute_workflow

Primitives extracted in #5060:
  - retry_with_backoff  (orchestration/primitives/retry.py)
  - publish_event       (orchestration/primitives/events.py)
  Supporting modules:   orchestration/orchestrator_config.py
                        orchestration/orchestrator_stubs.py
                        orchestration/orchestrator_legacy_api.py
                        orchestration/orchestrator_prompts.py

Issue #10666 B3: enhanced_orchestration package fully merged into orchestration.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Set, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.workflow import ExecutionStrategy
from config.manager import get_config_manager as _get_config_manager
from constants.threshold_constants import LLMDefaults, TimingConstants
from memory import LongTermMemoryManager

# Issue #5040 / #10666 B3: multi-agent imports (consolidated into orchestration)
from orchestration import (
    FALLBACK_TIERS,
    AgentCapability,
    AgentInteraction,
    AgentPerformance,
    AgentProfile,
    AgentRegistry,
    AgentRouter,
    AgentTask,
    CausalErrorRecovery,
    CollaborationCoordinator,
    DocumentationType,
    StrategyPlanner,
    WorkflowDocumentation,
    WorkflowDocumenter,
    WorkflowMemory,
    WorkflowPlan,
    WorkflowPlanner,
    WorkflowRunner,
    get_default_agents,
    get_recovery_recommender,
)
from orchestration.causal_error_analyzer import (  # noqa: F401 (GH #6816)
    CausalErrorAnalyzer,
)
from orchestration.causal_validator import CausalValidator  # noqa: F401 (GH #6816)
from orchestration.orchestrator_config import OrchestratorConfig
from orchestration.orchestrator_legacy_api import _DeprecatedRequestMixin
from orchestration.orchestrator_prompts import build_planning_prompt
from orchestration.orchestrator_stubs import (
    CLASSIFICATION_AVAILABLE,
    WORKFLOW_TYPES_AVAILABLE,
    AgentManager,
    GemmaClassificationAgent,
    WorkflowStep,
)
from orchestration.performance_tracker import PerformanceTracker
from orchestration.primitives.events import PersistStrategy
from orchestration.primitives.events import publish_event as _publish_event
from orchestration.primitives.retry import (  # noqa: F401 — re-exported
    retry_with_backoff,
)
from services.llm_service import get_llm_service

# Shared agent selection utilities (Issue #292)
from utils.agent_selection import find_best_agent_for_task as _find_best_agent
from utils.agent_selection import release_agent as _release_agent
from utils.agent_selection import reserve_agent as _reserve_agent

logger = get_logger("orchestrator")

# Canonical singleton; avoids routing through config/__init__ lazy alias (Issue #3829)
config_manager = _get_config_manager()

# Import KnowledgeBase for enhanced features
try:
    from knowledge_base import KnowledgeBase

    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False
    logger.warning("KnowledgeBase not available - auto-documentation features disabled")

from agents.agent_client import AgentRegistry as _AgentClientRegistry
from autobot_shared.status_enums import Priority as TaskPriority  # #7504 consolidation
from autobot_shared.status_enums import WorkflowStatus  # #6973 consolidation
from autobot_types import TaskComplexity


class OrchestrationMode(Enum):
    SIMPLE = "simple"
    ENHANCED = "enhanced"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class Orchestrator(_DeprecatedRequestMixin):
    """
    Orchestrator for AutoBot — single conductor.

    Issue #5040: Merged all orchestrator implementations into one class.
    Issue #5058: Decomposed into collaborators; one workflow execution path via
    WorkflowRunner; one PerformanceTracker; no _ma_ prefixes.
    Issue #5060: Deprecated request API extracted to _DeprecatedRequestMixin;
    retry/event primitives extracted to orchestration/primitives/.
    """

    # ------------------------------------------------------------------ init

    def _init_core_components(self, config_mgr) -> None:
        self.config_manager = config_mgr or _get_config_manager()
        self.config = OrchestratorConfig(self.config_manager)
        # #6983: migrated from LLMInterface to LLMService (#3185 missed this caller)
        self.llm_service = get_llm_service()
        self.memory_manager = LongTermMemoryManager()
        self.agent_manager = AgentManager()

    def _init_task_state(self) -> None:
        self.active_tasks: Dict[str, Any] = {}
        self.task_queue: List[Any] = []
        self.completed_tasks: Dict[str, Any] = {}
        self.is_running = False
        self.session_id = str(uuid.uuid4())
        self.start_time = None
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0,
            "average_response_time": 0,
        }

    def _init_components(self) -> None:
        self.agent_registry: Dict[str, AgentProfile] = {}
        # GH #6820: AgentRegistry — structured profile store with capability-based lookup.
        # Runs alongside the plain-dict self.agent_registry for structured queries.
        self._profile_registry = AgentRegistry(initialize_defaults=True)
        self.workflow_documentation: Dict[str, WorkflowDocumentation] = {}
        self.agent_interactions: List[AgentInteraction] = []
        self.knowledge_base = KnowledgeBase() if KNOWLEDGE_BASE_AVAILABLE else None
        self.knowledge_extraction_enabled = KNOWLEDGE_BASE_AVAILABLE
        self.auto_doc_enabled = True
        self.workflow_metrics = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "average_execution_time": 0.0,
        }

    def _init_classification_agent(self) -> None:
        self.classification_agent = None
        if CLASSIFICATION_AVAILABLE:
            try:
                self.classification_agent = GemmaClassificationAgent()
                logger.info("Classification agent initialized successfully")
            except Exception as e:
                logger.warning("Failed to initialize classification agent: %s", e)

    def _init_strategy_components(self) -> None:
        """Initialize multi-agent strategy components. Renamed from _init_multi_agent_state (#5058)."""
        # Agent capabilities registry (task-routing layer distinct from agent_registry)
        self.agent_capabilities: Dict[str, Set] = {
            "research_agent": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            "classification_agent": {
                AgentCapability.ANALYSIS,
                AgentCapability.VALIDATION,
            },
            "kb_librarian": {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
            "system_commands": {AgentCapability.EXECUTION, AgentCapability.MONITORING},
            "security_scanner": {AgentCapability.SECURITY, AgentCapability.VALIDATION},
            "npu_code_search": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
            "development_speedup": {
                AgentCapability.ANALYSIS,
                AgentCapability.OPTIMIZATION,
            },
            "json_formatter": {AgentCapability.VALIDATION, AgentCapability.SYNTHESIS},
            "llm_failsafe": {AgentCapability.SYNTHESIS},
        }
        # GH#11139: the registered agent profiles are the capability manifest SSOT.
        # Overlay their capabilities onto the routing map so any agent that also has
        # a profile has ONE source of truth for its capabilities (no drift between
        # this literal and the profile registry). Only overlays existing keys, so
        # the routing candidate set is unchanged.
        for agent_id, profile in self._profile_registry.get_all().items():
            if agent_id in self.agent_capabilities:
                self.agent_capabilities[agent_id] = set(profile.capabilities)

        # Workflow tracking
        self.active_workflows: Dict[str, WorkflowPlan] = {}

        # Coordination prefixes
        self.coordination_prefix = "autobot:orchestrator:coord:"
        self.result_prefix = "autobot:orchestrator:results:"

        # Strategy planner (was _ma_planner)
        self._strategy_planner = StrategyPlanner(self.agent_capabilities)

        # Unified performance tracker — replaces the three separate update methods (#5058)
        self._perf = PerformanceTracker(self.agent_capabilities)

        # Agent router — selection, resolution, capability coverage (#6393/#6392)
        self._agent_router = AgentRouter(
            agent_capabilities=self.agent_capabilities,
            performance_tracker=self._perf,
            agent_registry=_AgentClientRegistry(),
        )

        # Step planner — capability-to-agent mapping for single-workflow steps (GH #6820).
        # Populated after _initialize_default_agents so agent_registry is non-empty.
        self._step_planner = WorkflowPlanner(
            base_orchestrator=self,
            agent_registry=self.agent_registry,
            find_best_agent_callback=self.find_best_agent_for_task,
        )

        # Causal error recovery — opt-in analysis on workflow ABORT (GH #6816).
        self._causal_recovery: CausalErrorRecovery = get_recovery_recommender()

        # Collaboration coordinator — Redis pub/sub between agents (#6393)
        self._collab = CollaborationCoordinator()

        # Execution engine collaborator
        self._runner = WorkflowRunner(
            strategy_planner=self._strategy_planner,
            performance_tracker=self._perf,
            active_workflows=self.active_workflows,
            collaboration=self._collab,
            agent_router=self._agent_router,
            max_parallel_tasks=self.config.max_parallel_tasks,
        )

    def __init__(self, config_mgr=None):
        self._init_core_components(config_mgr)
        self._init_task_state()
        self._init_components()
        self._init_classification_agent()
        self._initialize_default_agents()
        self._init_strategy_components()
        logger.info("Orchestrator initialized with session: %s", self.session_id)

    # ------------------------------------------------------- agent registration

    def _initialize_default_agents(self) -> None:
        # GH#11139: single source — the same default profiles (incl. the
        # allowed_work/forbidden_work manifest) that seed self._profile_registry.
        # Previously duplicated inline here, which let the two populations drift.
        profiles = get_default_agents()
        for profile in profiles:
            self.agent_registry[profile.agent_id] = profile
            self._profile_registry.register(profile)
        logger.info("Initialized %d default agent profiles", len(profiles))

    def get_agent_work_boundary(self, agent_id: str) -> "tuple[list[str], list[str]]":
        """Return ``(allowed_work, forbidden_work)`` for *agent_id* (GH#11139).

        Single accessor onto the declarative capability manifest carried by the
        agent profile — routing and tool enforcement both derive from here rather
        than re-deriving the boundary from separate RBAC/sensitive-tool state.
        """
        return self._profile_registry.work_boundary(agent_id)

    async def register_agent(self, agent_profile: AgentProfile) -> bool:
        try:
            if agent_profile.agent_id in self.agent_registry:
                logger.warning(
                    "Agent %s already registered, updating profile",
                    agent_profile.agent_id,
                )
            self.agent_registry[agent_profile.agent_id] = agent_profile
            logger.info(
                "Agent %s registered with capabilities: %s",
                agent_profile.agent_id,
                agent_profile.capabilities,
            )
            return True
        except Exception as e:
            logger.error("Failed to register agent %s: %s", agent_profile.agent_id, e)
            return False

    def find_best_agent_for_task(
        self, task_type: str, required_capabilities: Set[AgentCapability] = None
    ) -> str | None:
        """Find the best agent for a task. Uses shared utility (Issue #292)."""
        return _find_best_agent(
            agent_registry=self.agent_registry,
            task_type=task_type,
            required_capabilities=required_capabilities,
        )

    def _reserve_agent(self, agent_id: str) -> None:
        _reserve_agent(self.agent_registry, agent_id)

    def _release_agent(self, agent_id: str) -> None:
        _release_agent(self.agent_registry, agent_id)

    # -------------------------------------------------------- LLM / init / shutdown

    async def _validate_llm_model(self, model_name: str) -> bool:
        try:
            # #6983: migrated to LLMService.chat() — returns LLMResponse with .content/.error attrs
            response = await self.llm_service.chat(
                [{"role": "user", "content": "Test connection"}],
                model_name=model_name,
                max_tokens=LLMDefaults.MINIMAL_MAX_TOKENS,
            )
            return not response.error and bool(response.content)
        except Exception as e:
            logger.debug("Model test failed for %s: %s", model_name, e)
            return False

    async def _ensure_working_llm_model(self) -> None:
        if await self._validate_llm_model(self.config.orchestrator_llm_model):
            logger.info(
                "✅ Orchestrator model '%s' is working",
                self.config.orchestrator_llm_model,
            )
            return
        logger.warning("⚠️ Orchestrator model '%s' test failed", self.config.orchestrator_llm_model)
        fallback_model = config_manager.get_default_llm_model()
        if await self._validate_llm_model(fallback_model):
            logger.info("✅ Using fallback model: %s", fallback_model)
            self.config.orchestrator_llm_model = fallback_model
            return
        logger.error("❌ Fallback model '%s' also failed", fallback_model)
        raise Exception("No working LLM models available")

    async def initialize(self) -> None:
        logger.info("Initializing Consolidated Orchestrator...")
        try:
            await asyncio.gather(
                self.memory_manager.initialize(),
                self.agent_manager.initialize(),
            )
            # is_provider_healthy returns (is_healthy, error_message_or_None);
            # tuple is always truthy, so the prior `if not <tuple>:` guard
            # never fired and ollama-down failures fell through to the
            # less-specific model validation step.
            ollama_connected, ollama_error = await self.llm_service.is_provider_healthy(provider_name="ollama")
            if not ollama_connected:
                raise Exception(f"Failed to connect to Ollama: {ollama_error or 'unknown error'}")
            logger.info("✅ Ollama connection established")
            await self._ensure_working_llm_model()
            # #7431 ADR-006 §Q1: start the BlockedPlanResumer so plans
            # blocked on Phase 3 skill generation auto-resume when the
            # generated skill is promoted (skill_promoted Redis pub-sub).
            # Best-effort — failures here log but do not block startup
            # (manual try_resume_blocked_plan still works without the
            # auto-subscriber).
            try:
                await self._runner.get_blocked_plan_resumer().start()
                logger.info("✅ Blocked-plan resumer subscribed")
            except Exception as resumer_exc:
                logger.warning("Blocked-plan resumer failed to start: %s", resumer_exc)
            self.is_running = True
            self.start_time = datetime.now(tz=timezone.utc)
            logger.info("✅ Consolidated Orchestrator initialization complete")
        except Exception as e:
            logger.error("❌ Orchestrator initialization failed: %s", e)
            raise

    async def shutdown(self) -> None:
        logger.info("Shutting down Consolidated Orchestrator...")
        self.is_running = False
        if self.active_tasks:
            logger.info("Waiting for %d active tasks to complete...", len(self.active_tasks))
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)
        # #7431 ADR-006 §Q1: cancel the BlockedPlanResumer subscriber.
        # Best-effort — never block shutdown on resumer plumbing.
        try:
            await self._runner.get_blocked_plan_resumer().stop()
        except Exception as resumer_exc:
            logger.debug("Blocked-plan resumer stop warning: %s", resumer_exc)
        try:
            # #6983: LLMService has no cleanup() (provider lifecycle managed elsewhere); drop the call
            await asyncio.gather(
                self.memory_manager.cleanup(),
                self.agent_manager.cleanup(),
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning("Cleanup warning: %s", e)
        uptime = datetime.now(tz=timezone.utc) - self.start_time if self.start_time else 0
        logger.info("Orchestrator session %s completed (uptime %s)", self.session_id, uptime)
        logger.info(
            "  Tasks completed: %s  failed: %s",
            self.metrics["tasks_completed"],
            self.metrics["tasks_failed"],
        )

    # process_user_request and its helpers (_start_request_tracking,
    # _update_success_metrics, _classify_task, _select_model_for_task,
    # _process_simple_request) are inherited from _DeprecatedRequestMixin (#5060).

    # ------------------------------------------------- run_workflow

    def _get_documenter(self) -> WorkflowDocumenter:
        if not hasattr(self, "_documenter") or self._documenter is None:
            self._documenter = WorkflowDocumenter(
                knowledge_base=self.knowledge_base,
                llm_service=self.llm_service,
            )
        return self._documenter

    async def run_workflow(
        self,
        user_request: str,
        context: Dict[str, Any] | None = None,
        auto_document: bool = True,
        require_plan_approval: bool = False,
        plan_approval_callback=None,
    ) -> Dict[str, Any]:
        """Execute workflow via create_workflow_plan + WorkflowRunner.execute_workflow.

        Issue #3393: merged from enhanced_orchestrator.py.
        Issue #5058: unified — delegates to the canonical WorkflowPlan/execute_workflow path;
        the old orchestration.WorkflowPlanner/WorkflowExecutor path has been removed.
        The require_plan_approval parameter is retained for API compatibility but is not
        implemented (no callers pass True).
        """
        start_time = time.time()
        context = context or {}
        workflow_id = str(uuid.uuid4())
        logger.info("Starting workflow %s: %s", workflow_id, user_request[:80])

        # GH #6820: WorkflowMemory — shared KV store for cross-step coordination.
        shared_memory = WorkflowMemory(workflow_id=workflow_id)
        try:
            shared_memory.set("request", user_request[:500])
            shared_memory.set("context_keys", list(context.keys()))
        except Exception as _mem_exc:
            logger.debug("WorkflowMemory init store skipped: %s", _mem_exc)

        if auto_document:
            documenter = self._get_documenter()
            doc = documenter.create_workflow_doc(
                workflow_id=workflow_id,
                title=f"Workflow: {user_request[:50]}...",
                description=user_request,
            )
            doc.content.update({"request": user_request, "context": context, "start_time": start_time})
            self.workflow_documentation[workflow_id] = doc

        try:
            plan = await self.create_workflow_plan(user_request, context)
            exec_result = await self._runner.execute_workflow(plan)

            succeeded = exec_result.get("success", False)
            status = "completed" if succeeded else "failed"
            self.workflow_metrics["total_workflows"] += 1
            if succeeded:
                self.workflow_metrics["successful_workflows"] += 1
            total = self.workflow_metrics["total_workflows"]
            elapsed = time.time() - start_time
            cur_avg = self.workflow_metrics["average_execution_time"]
            self.workflow_metrics["average_execution_time"] = ((cur_avg * (total - 1)) + elapsed) / total

            if auto_document:
                documenter = self._get_documenter()
                await documenter.generate_workflow_documentation(workflow_id, exec_result)
                doc = documenter.get_doc(workflow_id)
                if doc:
                    self.workflow_documentation[workflow_id] = doc

            if self.knowledge_extraction_enabled:
                documenter = self._get_documenter()
                await documenter.extract_workflow_knowledge(workflow_id, user_request, exec_result, self.agent_registry)

            return {
                "workflow_id": workflow_id,
                "status": status,
                "result": exec_result,
                "execution_time": elapsed,
                "agents_involved": list(exec_result.get("results", {}).keys()),
                "documentation_generated": auto_document,
                "knowledge_extracted": self.knowledge_extraction_enabled,
            }

        except Exception as e:
            logger.error("Workflow %s failed: %s", workflow_id, e)
            if auto_document:
                documenter = self._get_documenter()
                await documenter.document_workflow_failure(workflow_id, str(e))
                doc = documenter.get_doc(workflow_id)
                if doc:
                    self.workflow_documentation[workflow_id] = doc
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
                "execution_time": time.time() - start_time,
            }

    # --------------------------------- backward-compat: WorkflowStep-based planning API

    async def classify_request_complexity(self, user_request: str) -> TaskComplexity:
        """Classify request complexity.

        Retained for callers in orchestration/workflow_planner.py,
        services/workflow_automation/, services/advanced_workflow/, and tests.
        """
        if not CLASSIFICATION_AVAILABLE:
            return TaskComplexity.COMPLEX
        try:
            if self.classification_agent:
                result = await self.classification_agent.classify_user_request(user_request)
                return result.complexity
        except Exception as e:
            logger.error("Classification failed: %s, defaulting to COMPLEX", e)
        return TaskComplexity.COMPLEX

    async def plan_workflow_steps(self, user_request: str, complexity: TaskComplexity) -> List[WorkflowStep]:
        """Plan WorkflowStep objects based on complexity.

        Retained for callers in orchestration/workflow_planner.py,
        services/workflow_automation/, services/advanced_workflow/, and tests.
        """
        if not WORKFLOW_TYPES_AVAILABLE:
            return []
        try:
            if complexity == TaskComplexity.SIMPLE:
                return [
                    WorkflowStep(
                        id="step_1",
                        agent_type="llm",
                        action="generate_response",
                        description="Generate direct response to user query",
                        requires_approval=False,
                        dependencies=[],
                        inputs={"query": user_request},
                        expected_duration_ms=2000,
                    )
                ]
            return [
                WorkflowStep(
                    id="step_1",
                    agent_type="analyzer",
                    action="analyze_request",
                    description="Analyze user request",
                    requires_approval=False,
                    dependencies=[],
                    inputs={"query": user_request},
                    expected_duration_ms=3000,
                ),
                WorkflowStep(
                    id="step_2",
                    agent_type="executor",
                    action="execute_plan",
                    description="Execute the planned actions",
                    requires_approval=True,
                    dependencies=["step_1"],
                    inputs={"query": user_request},
                    expected_duration_ms=10000,
                ),
                WorkflowStep(
                    id="step_3",
                    agent_type="synthesizer",
                    action="synthesize_results",
                    description="Synthesize results",
                    requires_approval=False,
                    dependencies=["step_2"],
                    inputs={"query": user_request},
                    expected_duration_ms=2000,
                ),
            ]
        except Exception as e:
            logger.error("Failed to plan workflow steps: %s", e)
            return []

    # ------------------------------------------ workflow planning (canonical path)

    def _build_planning_prompt(
        self,
        goal: str,
        *,
        learned_prompt_template: str | None = None,
        similar_trajectories: List[Any] | None = None,
    ) -> str:
        """Render the planning prompt.

        #10580: passes ``learned_prompt_template`` from a high-confidence
        LearnedStrategy so the planner benefits from proven approaches.
        #10581: passes ``similar_trajectories`` as few-shot priors so the planner
        can reuse proven decompositions from past high-reward executions.
        """
        capabilities_json = json.dumps(
            {agent: [cap.value for cap in caps] for agent, caps in self.agent_capabilities.items()},
            indent=2,
        )
        return build_planning_prompt(
            goal,
            capabilities_json,
            learned_prompt_template=learned_prompt_template,
            similar_trajectories=similar_trajectories,
        )

    def _parse_planning_response(self, response: Any, goal: str) -> Dict[str, Any]:
        if response.tier_used.value in FALLBACK_TIERS:
            return self._strategy_planner.create_fallback_plan(goal)
        from agents.json_formatter_agent import json_formatter

        parse_result = json_formatter.parse_llm_response(response.content)
        if parse_result.success:
            return parse_result.data
        return self._strategy_planner.create_fallback_plan(goal)

    async def _fetch_planning_context(self, goal: str, context: Dict[str, Any] | None) -> Dict[str, Any]:
        """Gather learned template and similar trajectories for #10580/#10581.

        Non-fatal: always returns a dict (possibly empty) so planning continues
        even when Redis or ChromaDB is unavailable.
        """
        result: Dict[str, Any] = {}
        ctx = context or {}

        # #11015 kill-switch: skip all planning-context I/O when disabled.
        from autobot_shared.ssot_config import PLANNING_CONTEXT_ENABLED  # noqa: PLC0415

        if not PLANNING_CONTEXT_ENABLED:
            return result

        # #11015: isolate trajectory retrieval to the caller's tenant so one org's
        # history can never bias/inject into another's plan. Absent → un-scoped.
        tenant_id = str(ctx.get("tenant_id") or "")

        # #10580 — learned prompt template from TaskPatternLearner
        try:
            from agents.task_pattern_learner import (
                LEARNED_STRATEGY_CONFIDENCE,
                TaskPatternLearner,
            )

            task_type = ctx.get("task_type", "")
            if task_type:
                learner = TaskPatternLearner()
                task_type = learner.normalize_task_type(task_type)
                strategy = await learner.get_learned_strategy(task_type)
                if strategy and strategy.confidence > LEARNED_STRATEGY_CONFIDENCE and strategy.best_prompt_template:
                    result["learned_prompt_template"] = strategy.best_prompt_template
                    logger.info(
                        "used learned prompt template for %s (confidence=%.2f)",
                        task_type,
                        strategy.confidence,
                    )
        except Exception as exc:
            logger.debug("Learned prompt template lookup failed (non-fatal): %s", exc)

        # #10581 — similar trajectories from TrajectoryStore
        try:
            from memory.trajectory_store import get_trajectory_store

            store = await get_trajectory_store()
            similar = await store.find_similar_trajectories(goal, top_k=5, min_reward=0.7, tenant_id=tenant_id or None)
            if similar:
                result["similar_trajectories"] = similar
        except Exception as exc:
            logger.debug("Similar trajectory lookup failed (non-fatal): %s", exc)

        return result

    async def _generate_single_plan(
        self,
        goal: str,
        context: Dict[str, Any] | None,
        planning_ctx: Dict[str, Any],
    ) -> WorkflowPlan:
        """Generate one candidate plan from the LLM."""
        from agents.llm_failsafe_agent import get_robust_llm_response

        prompt = self._build_planning_prompt(
            goal,
            learned_prompt_template=planning_ctx.get("learned_prompt_template"),
            similar_trajectories=planning_ctx.get("similar_trajectories"),
        )
        response = await get_robust_llm_response(prompt, context)
        plan_data = self._parse_planning_response(response, goal)
        return await self._strategy_planner.build_workflow_plan(goal, plan_data)

    async def _score_plan(self, plan: WorkflowPlan, goal: str) -> float:
        """Score a candidate plan with TaskOutcomeJudge (#10583)."""
        try:
            from judges.task_outcome_judge import TaskOutcomeJudge

            judge = TaskOutcomeJudge()
            result = await judge.evaluate_task_outcome(
                task_type="planning",
                goal=goal,
                output=str(plan.tasks),
                strategy_used=str(plan.execution_strategy),
            )
            return result.overall_score
        except Exception as exc:
            logger.debug("Plan scoring failed (non-fatal): %s", exc)
            return 0.0

    async def _select_best_plan(
        self,
        goal: str,
        context: Dict[str, Any] | None,
        planning_ctx: Dict[str, Any],
        n: int,
    ) -> WorkflowPlan:
        """Sample N candidate plans, score each, return the top-ranked (#10583).

        Rejected candidates and their scores are recorded in the trajectory
        context for explainability.  Scoring uses TaskOutcomeJudge directly —
        no parallel scorer is introduced.
        """
        candidates: List[WorkflowPlan] = []
        for i in range(n):
            try:
                plan = await self._generate_single_plan(goal, context, planning_ctx)
                candidates.append(plan)
            except Exception as exc:
                logger.warning("Candidate plan %d/%d generation failed: %s", i + 1, n, exc)

        if not candidates:
            return self._strategy_planner.create_simple_workflow_plan(goal)

        scored: List[tuple[float, WorkflowPlan]] = []
        for plan in candidates:
            score = await self._score_plan(plan, goal)
            scored.append((score, plan))
        scored.sort(key=lambda t: t[0], reverse=True)

        best_score, best = scored[0]
        rejected = [{"plan_id": p.plan_id, "score": s} for s, p in scored[1:]]
        logger.info(
            "best-of-%d plan selection: best_plan=%s score=%.3f rejected=%s",
            n,
            best.plan_id,
            best_score,
            rejected,
        )
        # Record rejected candidates on context for trajectory explainability.
        if context is not None:
            context.setdefault("plan_selection", {}).update({"best_score": best_score, "rejected_candidates": rejected})
        return best

    async def create_workflow_plan(self, goal: str, context: Dict[str, Any] | None = None) -> WorkflowPlan:
        """Create an intelligent workflow plan for a goal via LLM planning.

        Issue #5040: merged from EnhancedMultiAgentOrchestrator.
        #10580/#10581: injects learned prompt template and similar-trajectory priors.
        #10583: when AUTOBOT_PLAN_BEST_OF_N_ENABLED=true, samples N candidate plans
        and executes the top-ranked; flag OFF (default) = exactly one plan, zero
        extra judge calls, cost/behaviour unchanged.
        """
        from autobot_shared.ssot_config import PLAN_BEST_OF_N_COUNT, PLAN_BEST_OF_N_ENABLED

        logger.info("Creating workflow plan for: %s", goal)
        try:
            planning_ctx = await self._fetch_planning_context(goal, context)

            if PLAN_BEST_OF_N_ENABLED:
                plan = await self._select_best_plan(goal, context, planning_ctx, PLAN_BEST_OF_N_COUNT)
            else:
                plan = await self._generate_single_plan(goal, context, planning_ctx)

            # #11015: stamp caller identity so the trajectory captured after
            # execution is tagged with the tenant that owns it, keeping future
            # retrieval isolated. Stored in the existing metadata dict (no schema
            # change). Absent context → empty (untenanted), same as before.
            ctx = context or {}
            plan.metadata.setdefault("tenant_id", str(ctx.get("tenant_id") or ""))
            plan.metadata.setdefault("user_id", str(ctx.get("user_id") or ""))

            self.active_workflows[plan.plan_id] = plan
            return plan
        except Exception as e:
            logger.error("Failed to create workflow plan: %s", e)
            return self._strategy_planner.create_simple_workflow_plan(goal)

    # ---------------------------------------------- delegation to WorkflowRunner

    async def execute_workflow(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute a WorkflowPlan. Delegates to WorkflowRunner (#5058)."""
        return await self._runner.execute_workflow(plan)

    async def get_agent_recommendations(self, capabilities_needed: Set) -> List[str]:
        """Get recommended agents for a task. Delegates to WorkflowRunner (#5058)."""
        return await self._runner.get_agent_recommendations(capabilities_needed)

    async def get_agent_recommendations_scored(self, capabilities_needed: Set) -> List[Tuple[str, float]]:
        """Get (agent, score) recommendations. Delegates to WorkflowRunner (#10660)."""
        return await self._runner.get_agent_recommendations_scored(capabilities_needed)

    def get_performance_report(self) -> Dict[str, Any]:
        """Performance report. Delegates to WorkflowRunner (#5058)."""
        return self._runner.get_performance_report()

    # ----------------------------------------------------------------- status / config

    def set_phi2_enabled(self, enabled: bool) -> None:
        self.config.phi2_enabled = enabled
        logger.info("Phi-2 enabled status set to: %s", self.config.phi2_enabled)
        try:
            asyncio.get_running_loop().create_task(
                _publish_event(
                    "global",
                    "settings_update",
                    {"phi2_enabled": enabled},
                    persist=PersistStrategy.NONE,
                )
            )
        except RuntimeError:
            logger.debug("No running event loop; settings_update event not published")
        except Exception:
            logger.debug("Event bus not available for settings update")

    async def get_status(self) -> Dict[str, Any]:
        uptime = datetime.now(tz=timezone.utc) - self.start_time if self.start_time else 0
        return {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "uptime": str(uptime),
            "active_tasks": len(self.active_tasks),
            "queued_tasks": len(self.task_queue),
            "metrics": self.metrics,
            "workflow_metrics": self.workflow_metrics,
            "capabilities_coverage": self._runner.get_performance_report()["capabilities_coverage"],
            "configuration": {
                "orchestrator_model": self.config.orchestrator_llm_model,
                "task_model": self.config.task_llm_model,
                "max_parallel_tasks": self.config.max_parallel_tasks,
                "classification_enabled": self.classification_agent is not None,
                "knowledge_extraction_enabled": self.knowledge_extraction_enabled,
                "auto_doc_enabled": self.auto_doc_enabled,
            },
            "agent_registry": {
                agent_id: {
                    "agent_type": agent.agent_type,
                    "capabilities": [cap.value for cap in agent.capabilities],
                    "availability_status": agent.availability_status,
                    "current_workload": agent.current_workload,
                    "max_concurrent_tasks": agent.max_concurrent_tasks,
                    "success_rate": agent.success_rate,
                    "average_completion_time": agent.average_completion_time,
                }
                for agent_id, agent in self.agent_registry.items()
            },
            "active_workflows": len(self.active_workflows),
            "total_documentation": len(self.workflow_documentation),
            "total_interactions": len(self.agent_interactions),
        }

    async def update_configuration(self, new_config: Dict[str, Any]) -> bool:
        try:
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.info("Updated configuration: %s = %s", key, value)
            return True
        except Exception as e:
            logger.error("Failed to update configuration: %s", e)
            return False


# ============================================================================
# Module-level helpers
# ============================================================================


async def create_and_execute_workflow(goal: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create and execute a multi-agent workflow plan.

    Issue #5040: Replaces enhanced_orchestration.create_and_execute_workflow.
    """
    orch = get_orchestrator_sync()
    plan = await orch.create_workflow_plan(goal, context)
    return await orch.execute_workflow(plan)


_orchestrator_instance = None
_orchestrator_lock = asyncio.Lock()


async def get_orchestrator() -> Orchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        async with _orchestrator_lock:
            if _orchestrator_instance is None:
                _orchestrator_instance = Orchestrator()
                await _orchestrator_instance.initialize()
    return _orchestrator_instance


async def shutdown_orchestrator():
    global _orchestrator_instance
    async with _orchestrator_lock:
        if _orchestrator_instance:
            await _orchestrator_instance.shutdown()
            _orchestrator_instance = None


_sync_instance_lock = __import__("threading").Lock()


def get_orchestrator_sync() -> Orchestrator:
    """Return the shared Orchestrator singleton (sync-safe).

    Issue #3393: sync accessor.  Use async get_orchestrator() when inside an
    async context and the fully-initialised instance is needed.
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        with _sync_instance_lock:
            if _orchestrator_instance is None:
                logger.info("Creating shared Orchestrator singleton (sync)")
                _orchestrator_instance = Orchestrator()
    return _orchestrator_instance


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    "Orchestrator",
    "OrchestratorConfig",
    "TaskPriority",
    "OrchestrationMode",
    "TaskComplexity",
    "WorkflowStatus",
    "AgentCapability",
    "DocumentationType",
    "WorkflowStep",
    "AgentProfile",
    "WorkflowDocumentation",
    "AgentInteraction",
    "WorkflowPlan",
    "AgentTask",
    "AgentPerformance",
    "ExecutionStrategy",
    "get_orchestrator",
    "get_orchestrator_sync",
    "shutdown_orchestrator",
    "create_and_execute_workflow",
]
