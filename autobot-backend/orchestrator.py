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
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager as _get_config_manager
from constants.threshold_constants import LLMDefaults, TimingConstants
from llm_interface import LLMInterface
from memory import LongTermMemoryManager

# Issue #381: shared orchestration types
from orchestration import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    DocumentationType,
    WorkflowDocumentation,
    WorkflowDocumenter,
)
from orchestration.performance_tracker import PerformanceTracker
from task_execution_tracker import Priority, TaskType, get_task_tracker

# Shared agent selection utilities (Issue #292)
from utils.agent_selection import find_best_agent_for_task as _find_best_agent
from utils.agent_selection import release_agent as _release_agent
from utils.agent_selection import reserve_agent as _reserve_agent

# Issue #5040: multi-agent imports
from enhanced_orchestration.types import (
    FALLBACK_TIERS,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from enhanced_orchestration.agent_router import AgentRouter
from enhanced_orchestration.collaboration_coordinator import CollaborationCoordinator
from enhanced_orchestration.workflow_planning import (
    WorkflowPlanner as StrategyPlanner,
)
from enhanced_orchestration.workflow_runner import WorkflowRunner

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

from autobot_types import TaskComplexity
from agents.agent_client import AgentRegistry as _AgentClientRegistry

try:
    from agents.gemma_classification_agent import GemmaClassificationAgent

    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False

try:
    from agents.agent_manager import AgentManager

    AGENT_MANAGER_AVAILABLE = True
except ImportError:
    AGENT_MANAGER_AVAILABLE = False

    class AgentManager:
        async def initialize(self):
            """Initialize placeholder - no operation when unavailable."""

        async def cleanup(self):
            """Cleanup placeholder - no operation when unavailable."""

        async def execute_agent_task(self, agent_name, task, context=None):
            return {"error": "Agent manager not available", "agent_name": agent_name}


try:
    from workflow_scheduler import WorkflowStatus
    from workflow_templates import WorkflowStep

    WORKFLOW_TYPES_AVAILABLE = True
except ImportError:
    WORKFLOW_TYPES_AVAILABLE = False

    class WorkflowStatus(Enum):
        SCHEDULED = "scheduled"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    @dataclass
    class WorkflowStep:
        id: str
        agent_type: str
        action: str
        description: str


class TaskPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class OrchestrationMode(Enum):
    SIMPLE = "simple"
    ENHANCED = "enhanced"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class OrchestratorConfig:
    """Configuration for the Orchestrator"""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._load_config()

    def _load_config(self):
        llm_config = self.config_manager.get_llm_config()
        self.orchestrator_llm_model = llm_config.get(
            "orchestrator_llm",
            llm_config.get("ollama", {}).get("selected_model"),
        )
        default_model = llm_config.get("ollama", {}).get("selected_model")
        self.task_llm_model = llm_config.get("task_llm", f"ollama_{default_model}")
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False

        self.max_parallel_tasks = self.config_manager.get("orchestrator.max_parallel_tasks", 3)
        self.task_timeout = self.config_manager.get("orchestrator.task_timeout", 300)
        self.retry_attempts = self.config_manager.get("orchestrator.retry_attempts", 3)
        self.agent_timeout = self.config_manager.get("orchestrator.agent_timeout", 120)
        self.max_agents = self.config_manager.get("orchestrator.max_agents", 5)
        self.enable_caching = self.config_manager.get("orchestrator.enable_caching", True)
        self.enable_streaming = self.config_manager.get("orchestrator.enable_streaming", True)

        logger.info("Orchestrator configured with model: %s", self.orchestrator_llm_model)


class Orchestrator:
    """
    Orchestrator for AutoBot — single conductor.

    Issue #5040: Merged all orchestrator implementations into one class.
    Issue #5058: Decomposed into collaborators; one workflow execution path via
    WorkflowRunner; one PerformanceTracker; no _ma_ prefixes.
    """

    # ------------------------------------------------------------------ init

    def _init_core_components(self, config_mgr) -> None:
        self.config_manager = config_mgr or _get_config_manager()
        self.config = OrchestratorConfig(self.config_manager)
        self.llm_interface = LLMInterface()
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
                agent_id="research_agent", agent_type="research",
                capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
                specializations=["web_search", "data_analysis", "information_synthesis"],
                max_concurrent_tasks=5,
                preferred_task_types=["research", "information_gathering", "analysis"],
            ),
            AgentProfile(
                agent_id="documentation_agent", agent_type="librarian",
                capabilities={AgentCapability.DOCUMENTATION, AgentCapability.KNOWLEDGE_MANAGEMENT},
                specializations=["auto_documentation", "knowledge_extraction", "content_organization"],
                max_concurrent_tasks=3,
                preferred_task_types=["documentation", "knowledge_management"],
            ),
            AgentProfile(
                agent_id="system_agent", agent_type="system_commands",
                capabilities={AgentCapability.SYSTEM_OPERATIONS, AgentCapability.CODE_GENERATION},
                specializations=["command_execution", "system_administration", "automation"],
                max_concurrent_tasks=2,
                preferred_task_types=["system_operations", "command_execution"],
            ),
            AgentProfile(
                agent_id="coordination_agent", agent_type="orchestrator",
                capabilities={AgentCapability.WORKFLOW_COORDINATION, AgentCapability.ANALYSIS},
                specializations=["workflow_management", "resource_allocation", "decision_making"],
                max_concurrent_tasks=10,
                preferred_task_types=["coordination", "planning", "optimization"],
            ),
        ]
        for profile in profiles:
            self.agent_registry[profile.agent_id] = profile
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
    ) -> Optional[str]:
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
            test_response = await self.llm_interface.generate_response(
                "Test connection", model=model_name, max_tokens=LLMDefaults.MINIMAL_MAX_TOKENS
            )
            return bool(test_response)
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
            ollama_connected = await self.llm_interface.check_ollama_connection()
            if not ollama_connected:
                raise Exception("Failed to connect to Ollama or configured models not found.")
            logger.info("✅ Ollama connection established")
            await self._ensure_working_llm_model()
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
        try:
            await asyncio.gather(
                self.llm_interface.cleanup(),
                self.memory_manager.cleanup(),
                self.agent_manager.cleanup(),
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning("Cleanup warning: %s", e)
        uptime = datetime.now(tz=timezone.utc) - self.start_time if self.start_time else 0
        logger.info("Orchestrator session %s completed (uptime %s)", self.session_id, uptime)
        logger.info("  Tasks completed: %s  failed: %s", self.metrics["tasks_completed"], self.metrics["tasks_failed"])

    # ----------------------------------------------------- process_user_request

    def _start_request_tracking(self, task_id, user_message, priority, context) -> None:
        get_task_tracker().start_task(
            task_id=task_id,
            task_type=TaskType.USER_REQUEST,
            description=user_message[:200],
            priority=Priority(priority.value),
            context=context or {},
        )

    def _update_success_metrics(self, processing_time: float) -> None:
        self.metrics["tasks_completed"] += 1
        self.metrics["total_processing_time"] += processing_time
        self.metrics["average_response_time"] = (
            self.metrics["total_processing_time"] / self.metrics["tasks_completed"]
        )

    async def process_user_request(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        mode: OrchestrationMode = OrchestrationMode.ENHANCED,
        priority: TaskPriority = TaskPriority.NORMAL,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process user request. Issue #281, #620, #5058.

        SIMPLE mode: direct LLM call (fast path, no workflow planning).
        All other modes: delegate to execute_enhanced_workflow (unified path).
        """
        start_time = time.time()
        task_id = str(uuid.uuid4())
        logger.info("Processing user request %s: %s...", task_id, user_message[:100])

        try:
            self._start_request_tracking(task_id, user_message, priority, context)
            classification_result = await self._classify_task(user_message)
            target_llm_model = self._select_model_for_task(classification_result)

            if mode == OrchestrationMode.SIMPLE:
                result = await self._process_simple_request(user_message, task_id, target_llm_model, context)
            else:
                result = await self.execute_enhanced_workflow(
                    user_request=user_message, context=context or {}
                )

            processing_time = time.time() - start_time
            self._update_success_metrics(processing_time)
            get_task_tracker().complete_task(task_id, result)
            logger.info("✅ Request %s completed in %.2fs", task_id, processing_time)
            return {
                "task_id": task_id,
                "success": True,
                "result": result,
                "processing_time": processing_time,
                "classification": classification_result.to_dict() if classification_result else None,
                "model_used": target_llm_model,
                "mode": mode.value,
            }
        except Exception as e:
            processing_time = time.time() - start_time
            self.metrics["tasks_failed"] += 1
            get_task_tracker().fail_task(task_id, str(e))
            logger.error("❌ Request %s failed after %.2fs: %s", task_id, processing_time, e)
            return {
                "task_id": task_id,
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "mode": mode.value,
            }

    async def _classify_task(self, user_message: str) -> Optional[Any]:
        if not self.classification_agent:
            return None
        try:
            result = await self.classification_agent.classify_user_request(user_message)
            logger.info("Task classified: %s complexity", result.complexity.value)
            return result
        except Exception as e:
            logger.warning("Classification failed: %s", e)
            return None

    def _select_model_for_task(self, classification_result: Optional[Any]) -> str:
        if classification_result and classification_result.complexity == TaskComplexity.SIMPLE:
            model = config_manager.get_default_llm_model()
            logger.info("Using fast model for simple task: %s", model)
            return model
        return self.config.orchestrator_llm_model

    async def _process_simple_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        response = await self.llm_interface.generate_response(
            user_message, model=model, max_tokens=LLMDefaults.ENRICHED_MAX_TOKENS, context=context
        )
        return {"type": "simple_response", "content": response, "sources": [{"type": "llm", "model": model}]}

    # ------------------------------------------------- execute_enhanced_workflow

    def _get_enhanced_documenter(self) -> WorkflowDocumenter:
        if not hasattr(self, "_enh_documenter") or self._enh_documenter is None:
            self._enh_documenter = WorkflowDocumenter(
                knowledge_base=self.knowledge_base,
                llm_interface=self.llm_interface,
            )
        return self._enh_documenter

    async def execute_enhanced_workflow(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
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
            self.workflow_metrics["average_execution_time"] = (
                (cur_avg * (total - 1)) + elapsed
            ) / total

            if auto_document:
                documenter = self._get_enhanced_documenter()
                await documenter.generate_workflow_documentation(workflow_id, exec_result)
                doc = documenter.get_doc(workflow_id)
                if doc:
                    self.workflow_documentation[workflow_id] = doc

            if self.knowledge_extraction_enabled:
                documenter = self._get_enhanced_documenter()
                await documenter.extract_workflow_knowledge(
                    workflow_id, user_request, exec_result, self.agent_registry
                )

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

    async def plan_workflow_steps(
        self, user_request: str, complexity: TaskComplexity
    ) -> List[WorkflowStep]:
        """Plan WorkflowStep objects based on complexity.

        Retained for callers in orchestration/workflow_planner.py,
        services/workflow_automation/, services/advanced_workflow/, and tests.
        """
        if not WORKFLOW_TYPES_AVAILABLE:
            return []
        try:
            if complexity == TaskComplexity.SIMPLE:
                return [WorkflowStep(
                    id="step_1", agent_type="llm", action="generate_response",
                    description="Generate direct response to user query",
                    requires_approval=False, dependencies=[],
                    inputs={"query": user_request}, expected_duration_ms=2000,
                )]
            return [
                WorkflowStep(id="step_1", agent_type="analyzer", action="analyze_request",
                             description="Analyze user request", requires_approval=False,
                             dependencies=[], inputs={"query": user_request}, expected_duration_ms=3000),
                WorkflowStep(id="step_2", agent_type="executor", action="execute_plan",
                             description="Execute the planned actions", requires_approval=True,
                             dependencies=["step_1"], inputs={"query": user_request}, expected_duration_ms=10000),
                WorkflowStep(id="step_3", agent_type="synthesizer", action="synthesize_results",
                             description="Synthesize results", requires_approval=False,
                             dependencies=["step_2"], inputs={"query": user_request}, expected_duration_ms=2000),
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
        return f"""
        You are an expert workflow planner. Analyze this goal and create an execution plan.

        Goal: {goal}

        Available agents and their capabilities:
        {capabilities_json}

        Create a workflow plan with:
        1. Required agents and their specific tasks
        2. Task dependencies (which tasks must complete before others)
        3. Execution strategy (sequential, parallel, pipeline, collaborative)
        4. Success criteria
        5. Estimated duration and resource requirements

        Respond in JSON format:
        {{
            "strategy": "parallel|sequential|pipeline|collaborative",
            "tasks": [
                {{
                    "agent": "agent_type",
                    "action": "specific_action",
                    "inputs": {{}},
                    "dependencies": ["task_ids"],
                    "priority": 1-10,
                    "capabilities_required": ["capability_names"]
                }}
            ],
            "success_criteria": ["criteria1", "criteria2"],
            "estimated_duration": 60.0,
            "resource_requirements": {{}}
        }}
        """

    def _parse_planning_response(self, response: Any, goal: str) -> Dict[str, Any]:
        if response.tier_used.value in FALLBACK_TIERS:
            return self._strategy_planner.create_fallback_plan(goal)
        from agents.json_formatter_agent import json_formatter
        parse_result = json_formatter.parse_llm_response(response.content)
        if parse_result.success:
            return parse_result.data
        return self._strategy_planner.create_fallback_plan(goal)

    async def create_workflow_plan(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> WorkflowPlan:
        """Create an intelligent workflow plan for a goal via LLM planning.

        Issue #5040: merged from EnhancedMultiAgentOrchestrator.
        """
        logger.info("Creating workflow plan for: %s", goal)
        try:
            from agents.llm_failsafe_agent import get_robust_llm_response
            planning_prompt = self._build_planning_prompt(goal)
            response = await get_robust_llm_response(planning_prompt, context)
            plan_data = self._parse_planning_response(response, goal)
            plan = self._strategy_planner.build_workflow_plan(goal, plan_data)
            self.active_workflows[plan.plan_id] = plan
            return plan
        except Exception as e:
            logger.error("Failed to create workflow plan: %s", e)
            return self._strategy_planner.create_simple_workflow_plan(goal)

    # ---------------------------------------------- delegation to WorkflowRunner

    async def execute_workflow(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute a WorkflowPlan. Delegates to WorkflowRunner (#5058)."""
        return await self._runner.execute_workflow(plan)

    async def get_agent_recommendations(
        self, capabilities_needed: Set
    ) -> List[str]:
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
            from utils.event_manager import event_manager
            event_manager.publish("settings_update", {"phi2_enabled": enabled})
        except ImportError:
            logger.debug("Event manager not available for settings update")

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

async def create_and_execute_workflow(
    goal: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
