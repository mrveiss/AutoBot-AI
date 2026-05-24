# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
  - WorkflowRunner  (enhanced_orchestration/workflow_runner.py) — execution engine
  - PerformanceTracker (orchestration/performance_tracker.py) — metrics
  - Three execution entry points unified: process_user_request → execute_enhanced_workflow
    → create_workflow_plan + WorkflowRunner.execute_workflow

Primitives extracted in #5060:
  - retry_with_backoff  (orchestration/primitives/retry.py)
  - publish_event       (orchestration/primitives/events.py)
  Supporting modules:   orchestration/orchestrator_config.py
                        orchestration/orchestrator_stubs.py
                        orchestration/orchestrator_legacy_api.py
                        orchestration/orchestrator_prompts.py
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Set

from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager as _get_config_manager
from constants.threshold_constants import TimingConstants
from enhanced_orchestration.agent_router import AgentRouter
from enhanced_orchestration.collaboration_coordinator import CollaborationCoordinator

# Issue #5040: multi-agent imports
from enhanced_orchestration.types import (
    FALLBACK_TIERS,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from enhanced_orchestration.workflow_planning import StrategyPlanner
from enhanced_orchestration.workflow_runner import WorkflowRunner
from memory import LongTermMemoryManager

# Issue #381: shared orchestration types
# GH #6820: wire-in AgentRegistry, WorkflowMemory, WorkflowPlanner (previously orphaned)
# GH #6816: wire-in CausalExecutor, CausalErrorRecovery (previously orphaned)
from orchestration import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    AgentRegistry,
    CausalErrorRecovery,
    CausalExecutor,
    DocumentationType,
    WorkflowDocumentation,
    WorkflowDocumenter,
    WorkflowMemory,
    WorkflowPlanner,
    get_recovery_recommender,
)
from orchestration.causal_error_analyzer import CausalErrorAnalyzer  # noqa: F401 (GH #6816)
from orchestration.causal_validator import CausalValidator  # noqa: F401 (GH #6816)
from orchestration.orchestrator_config import OrchestratorConfig
from orchestration.orchestrator_legacy_api import _DeprecatedRequestMixin
from orchestration.orchestrator_prompts import build_planning_prompt
from orchestration.orchestrator_stubs import (
    AGENT_MANAGER_AVAILABLE,
    CLASSIFICATION_AVAILABLE,
    WORKFLOW_TYPES_AVAILABLE,
    AgentManager,
    GemmaClassificationAgent,
    WorkflowStep,
)
from orchestration.performance_tracker import PerformanceTracker
from orchestration.primitives.events import PersistStrategy
from orchestration.primitives.events import publish_event as _publish_event
from orchestration.primitives.retry import retry_with_backoff  # noqa: F401 — re-exported
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

    def _init_enhanced_components(self) -> None:
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
            "classification_agent": {AgentCapability.ANALYSIS, AgentCapability.VALIDATION},
            "kb_librarian": {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
            "system_commands": {AgentCapability.EXECUTION, AgentCapability.MONITORING},
            "security_scanner": {AgentCapability.SECURITY, AgentCapability.VALIDATION},
            "npu_code_search": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
            "development_speedup": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
            "json_formatter": {AgentCapability.VALIDATION, AgentCapability.SYNTHESIS},
            "llm_failsafe": {AgentCapability.SYNTHESIS},
        }

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
        self._init_enhanced_components()
        self._init_classification_agent()
        self._initialize_default_agents()
        self._init_strategy_components()
        logger.info("Orchestrator initialized with session: %s", self.session_id)

    # ------------------------------------------------------- agent registration

    def _initialize_default_agents(self) -> None:
        profiles = [
            AgentProfile(
                agent_id="research_agent",
                agent_type="research",
                capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
                specializations=["web_search", "data_analysis", "information_synthesis"],
                max_concurrent_tasks=5,
                preferred_task_types=["research", "information_gathering", "analysis"],
            ),
            AgentProfile(
                agent_id="documentation_agent",
                agent_type="librarian",
                capabilities={AgentCapability.DOCUMENTATION, AgentCapability.KNOWLEDGE_MANAGEMENT},
                specializations=["auto_documentation", "knowledge_extraction", "content_organization"],
                max_concurrent_tasks=3,
                preferred_task_types=["documentation", "knowledge_management"],
            ),
            AgentProfile(
                agent_id="system_agent",
                agent_type="system_commands",
                capabilities={AgentCapability.SYSTEM_OPERATIONS, AgentCapability.CODE_GENERATION},
                specializations=["command_execution", "system_administration", "automation"],
                max_concurrent_tasks=2,
                preferred_task_types=["system_operations", "command_execution"],
            ),
            AgentProfile(
                agent_id="coordination_agent",
                agent_type="orchestrator",
                capabilities={AgentCapability.WORKFLOW_COORDINATION, AgentCapability.ANALYSIS},
                specializations=["workflow_management", "resource_allocation", "decision_making"],
                max_concurrent_tasks=10,
                preferred_task_types=["coordination", "planning", "optimization"],
            ),
        ]
        for profile in profiles:
            self.agent_registry[profile.agent_id] = profile
            self._profile_registry.register(profile)
        logger.info("Initialized %d default agent profiles", len(profiles))

    async def register_agent(self, agent_profile: AgentProfile) -> bool:
        try:
            if agent_profile.agent_id in self.agent_registry:
                logger.warning("Agent %s already registered, updating profile", agent_profile.agent_id)
            self.agent_registry[agent_profile.agent_id] = agent_profile
            logger.info("Agent %s registered with capabilities: %s", agent_profile.agent_id, agent_profile.capabilities)
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
            logger.info("✅ Orchestrator model '%s' is working", self.config.orchestrator_llm_model)
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
        logger.info("  Tasks completed: %s  failed: %s", self.metrics["tasks_completed"], self.metrics["tasks_failed"])

    # process_user_request and its helpers (_start_request_tracking,
    # _update_success_metrics, _classify_task, _select_model_for_task,
    # _process_simple_request) are inherited from _DeprecatedRequestMixin (#5060).

    # ------------------------------------------------- execute_enhanced_workflow

    def _get_enhanced_documenter(self) -> WorkflowDocumenter:
        if not hasattr(self, "_enh_documenter") or self._enh_documenter is None:
            self._enh_documenter = WorkflowDocumenter(
                knowledge_base=self.knowledge_base,
                llm_service=self.llm_service,
            )
        return self._enh_documenter

    async def execute_enhanced_workflow(
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
        logger.info("Starting enhanced workflow %s: %s", workflow_id, user_request[:80])

        # GH #6820: WorkflowMemory — shared KV store for cross-step coordination.
        shared_memory = WorkflowMemory(workflow_id=workflow_id)
        try:
            shared_memory.set("request", user_request[:500])
            shared_memory.set("context_keys", list(context.keys()))
        except Exception as _mem_exc:
            logger.debug("WorkflowMemory init store skipped: %s", _mem_exc)

        if auto_document:
            documenter = self._get_enhanced_documenter()
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
                documenter = self._get_enhanced_documenter()
                await documenter.generate_workflow_documentation(workflow_id, exec_result)
                doc = documenter.get_doc(workflow_id)
                if doc:
                    self.workflow_documentation[workflow_id] = doc

            if self.knowledge_extraction_enabled:
                documenter = self._get_enhanced_documenter()
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
            logger.error("Enhanced workflow %s failed: %s", workflow_id, e)
            if auto_document:
                documenter = self._get_enhanced_documenter()
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

    def _build_planning_prompt(self, goal: str) -> str:
        capabilities_json = json.dumps(
            {agent: [cap.value for cap in caps] for agent, caps in self.agent_capabilities.items()},
            indent=2,
        )
        return build_planning_prompt(goal, capabilities_json)

    def _parse_planning_response(self, response: Any, goal: str) -> Dict[str, Any]:
        if response.tier_used.value in FALLBACK_TIERS:
            return self._strategy_planner.create_fallback_plan(goal)
        from agents.json_formatter_agent import json_formatter

        parse_result = json_formatter.parse_llm_response(response.content)
        if parse_result.success:
            return parse_result.data
        return self._strategy_planner.create_fallback_plan(goal)

    async def create_workflow_plan(self, goal: str, context: Dict[str, Any] | None = None) -> WorkflowPlan:
        """Create an intelligent workflow plan for a goal via LLM planning.

        Issue #5040: merged from EnhancedMultiAgentOrchestrator.
        """
        logger.info("Creating workflow plan for: %s", goal)
        try:
            from agents.llm_failsafe_agent import get_robust_llm_response

            planning_prompt = self._build_planning_prompt(goal)
            response = await get_robust_llm_response(planning_prompt, context)
            plan_data = self._parse_planning_response(response, goal)
            plan = await self._strategy_planner.build_workflow_plan(goal, plan_data)
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

    def get_performance_report(self) -> Dict[str, Any]:
        """Performance report. Delegates to WorkflowRunner (#5058)."""
        return self._runner.get_performance_report()

    # ----------------------------------------------------------------- status / config

    def set_phi2_enabled(self, enabled: bool) -> None:
        self.config.phi2_enabled = enabled
        logger.info("Phi-2 enabled status set to: %s", self.config.phi2_enabled)
        try:
            asyncio.get_running_loop().create_task(
                _publish_event("global", "settings_update", {"phi2_enabled": enabled}, persist=PersistStrategy.NONE)
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
