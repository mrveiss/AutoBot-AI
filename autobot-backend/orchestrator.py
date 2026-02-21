# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Orchestrator for AutoBot - Phase 5 Code Consolidation

This module consolidates all orchestrator implementations into a single,
comprehensive orchestrator that integrates the best features from:
- src/orchestrator.py (main orchestrator)
- src/enhanced_orchestrator.py (enhanced features)
- chat_workflow/graph.py (LangGraph StateGraph — Issue #1043, replaces legacy LangChain)
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from config import config_manager
from conversation import ConversationManager
from llm_interface import LLMInterface
from memory import LongTermMemoryManager

# Issue #381: Import shared types from orchestration package
from orchestration import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    DocumentationType,
    WorkflowDocumentation,
)
from task_execution_tracker import Priority, TaskType, task_tracker

from autobot_shared.logging_manager import get_logger
from backend.constants.threshold_constants import LLMDefaults, TimingConstants

# Import shared agent selection utilities (Issue #292 - Eliminate duplicate code)
from backend.utils.agent_selection import find_best_agent_for_task as _find_best_agent
from backend.utils.agent_selection import release_agent as _release_agent
from backend.utils.agent_selection import reserve_agent as _reserve_agent
from backend.utils.agent_selection import (
    update_agent_performance as _update_performance,
)

logger = get_logger("orchestrator")

# Import KnowledgeBase for enhanced features
try:
    from knowledge_base import KnowledgeBase

    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False
    logger.warning("KnowledgeBase not available - auto-documentation features disabled")

# Import TaskComplexity from correct location (always available)
from autobot_types import TaskComplexity

# Import task classification (optional)
try:
    from agents.gemma_classification_agent import GemmaClassificationAgent

    # Note: TaskClassificationResult doesn't exist yet, using quoted type annotations
    # from task_classification import TaskClassificationResult

    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False

# Import agent manager
try:
    from agents.agent_manager import AgentManager

    AGENT_MANAGER_AVAILABLE = True
except ImportError:
    AGENT_MANAGER_AVAILABLE = False

    # Create a fallback AgentManager class
    class AgentManager:
        """Fallback AgentManager when the real one is not available"""

        async def initialize(self):
            """Initialize placeholder - no operation when unavailable."""

        async def cleanup(self):
            """Cleanup placeholder - no operation when unavailable."""

        async def execute_agent_task(self, agent_name, task, context=None):
            """Return error indicating agent manager is not available."""
            return {"error": "Agent manager not available", "agent_name": agent_name}


# Import workflow types for backward compatibility
try:
    from workflow_scheduler import WorkflowStatus
    from workflow_templates import WorkflowStep

    WORKFLOW_TYPES_AVAILABLE = True
except ImportError:
    WORKFLOW_TYPES_AVAILABLE = False

    # Define minimal fallback types (dataclass and Enum already imported above)
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
    """Task priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class OrchestrationMode(Enum):
    """Orchestration operation modes"""

    SIMPLE = "simple"
    ENHANCED = "enhanced"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


# Issue #381: AgentCapability, DocumentationType, AgentProfile, WorkflowDocumentation,
# and AgentInteraction are now imported from orchestration


class OrchestratorConfig:
    """Configuration for the Orchestrator"""

    def __init__(self, config_manager):
        """Initialize orchestrator config from config manager."""
        self.config_manager = config_manager
        self._load_config()

    def _load_config(self):
        """Load orchestrator configuration"""
        # Get LLM configuration
        llm_config = self.config_manager.get_llm_config()

        # Use selected_model from config, no hardcoding
        self.orchestrator_llm_model = llm_config.get(
            "orchestrator_llm",
            llm_config.get("ollama", {}).get("selected_model"),
        )
        default_model = llm_config.get("ollama", {}).get("selected_model")
        self.task_llm_model = llm_config.get(
            "task_llm",
            f"ollama_{default_model}",
        )
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False  # This will be driven by config if needed

        # Task configuration
        self.max_parallel_tasks = self.config_manager.get(
            "orchestrator.max_parallel_tasks", 3
        )
        self.task_timeout = self.config_manager.get("orchestrator.task_timeout", 300)
        self.retry_attempts = self.config_manager.get("orchestrator.retry_attempts", 3)

        # Agent configuration
        self.agent_timeout = self.config_manager.get("orchestrator.agent_timeout", 120)
        self.max_agents = self.config_manager.get("orchestrator.max_agents", 5)

        # Performance settings
        self.enable_caching = self.config_manager.get(
            "orchestrator.enable_caching", True
        )
        self.enable_streaming = self.config_manager.get(
            "orchestrator.enable_streaming", True
        )

        logger.info(
            "Orchestrator configured with model: %s", self.orchestrator_llm_model
        )


class ConsolidatedOrchestrator:
    """
    Consolidated Orchestrator for AutoBot - Phase 5

    Integrates all orchestrator features into a single, comprehensive system
    """

    def _init_core_components(self, config_mgr) -> None:
        """Initialize core orchestrator components. Issue #620."""
        from config import config_manager as global_config_manager

        self.config_manager = config_mgr or global_config_manager
        self.config = OrchestratorConfig(self.config_manager)

        self.llm_interface = LLMInterface()
        self.memory_manager = LongTermMemoryManager()
        self.conversation_manager = ConversationManager()
        self.agent_manager = AgentManager()

    def _init_task_state(self) -> None:
        """Initialize task and state management attributes. Issue #620."""
        self.active_tasks = {}
        self.task_queue = []
        self.completed_tasks = {}

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
        """Initialize enhanced orchestrator components. Issue #620."""
        self.agent_registry: Dict[str, AgentProfile] = {}
        self.workflow_documentation: Dict[str, WorkflowDocumentation] = {}
        self.agent_interactions: List[AgentInteraction] = []

        self.knowledge_base = KnowledgeBase() if KNOWLEDGE_BASE_AVAILABLE else None

        self.auto_doc_enabled = True
        self.doc_generation_threshold = 0.8
        self.knowledge_extraction_enabled = KNOWLEDGE_BASE_AVAILABLE

        self.workflow_metrics = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "average_execution_time": 0.0,
            "agent_utilization": {},
            "documentation_generated": 0,
            "knowledge_extracted": 0,
        }

    def _init_classification_agent(self) -> None:
        """Initialize classification agent if available. Issue #620."""
        self.classification_agent = None
        if CLASSIFICATION_AVAILABLE:
            try:
                self.classification_agent = GemmaClassificationAgent()
                logger.info("Classification agent initialized successfully")
            except Exception as e:
                logger.warning("Failed to initialize classification agent: %s", e)

    def __init__(self, config_mgr=None):
        """Initialize consolidated orchestrator with all core components."""
        self._init_core_components(config_mgr)
        self._init_task_state()
        self._init_enhanced_components()
        self._init_classification_agent()
        self._initialize_default_agents()

        logger.info(
            "Consolidated Orchestrator initialized with session: %s", self.session_id
        )

    def _create_research_agent_profile(self) -> AgentProfile:
        """Create the research agent profile. Issue #620."""
        return AgentProfile(
            agent_id="research_agent",
            agent_type="research",
            capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            specializations=["web_search", "data_analysis", "information_synthesis"],
            max_concurrent_tasks=5,
            preferred_task_types=["research", "information_gathering", "analysis"],
        )

    def _create_documentation_agent_profile(self) -> AgentProfile:
        """Create the documentation agent profile. Issue #620."""
        return AgentProfile(
            agent_id="documentation_agent",
            agent_type="librarian",
            capabilities={
                AgentCapability.DOCUMENTATION,
                AgentCapability.KNOWLEDGE_MANAGEMENT,
            },
            specializations=[
                "auto_documentation",
                "knowledge_extraction",
                "content_organization",
            ],
            max_concurrent_tasks=3,
            preferred_task_types=["documentation", "knowledge_management"],
        )

    def _create_system_agent_profile(self) -> AgentProfile:
        """Create the system agent profile. Issue #620."""
        return AgentProfile(
            agent_id="system_agent",
            agent_type="system_commands",
            capabilities={
                AgentCapability.SYSTEM_OPERATIONS,
                AgentCapability.CODE_GENERATION,
            },
            specializations=[
                "command_execution",
                "system_administration",
                "automation",
            ],
            max_concurrent_tasks=2,
            preferred_task_types=["system_operations", "command_execution"],
        )

    def _create_coordination_agent_profile(self) -> AgentProfile:
        """Create the coordination agent profile. Issue #620."""
        return AgentProfile(
            agent_id="coordination_agent",
            agent_type="orchestrator",
            capabilities={
                AgentCapability.WORKFLOW_COORDINATION,
                AgentCapability.ANALYSIS,
            },
            specializations=[
                "workflow_management",
                "resource_allocation",
                "decision_making",
            ],
            max_concurrent_tasks=10,
            preferred_task_types=["coordination", "planning", "optimization"],
        )

    def _initialize_default_agents(self):
        """Initialize default agent profiles."""
        default_agents = [
            self._create_research_agent_profile(),
            self._create_documentation_agent_profile(),
            self._create_system_agent_profile(),
            self._create_coordination_agent_profile(),
        ]

        for agent in default_agents:
            self.agent_registry[agent.agent_id] = agent

        logger.info("Initialized %d default agent profiles", len(default_agents))

    async def _validate_llm_model(self, model_name: str) -> bool:
        """Test if an LLM model is available and working (Issue #315: extracted).

        Args:
            model_name: The model name to test

        Returns:
            True if model works, False otherwise
        """
        try:
            test_response = await self.llm_interface.generate_response(
                "Test connection",
                model=model_name,
                max_tokens=LLMDefaults.MINIMAL_MAX_TOKENS,
            )
            return bool(test_response)
        except Exception as e:
            logger.debug("Model test failed for %s: %s", model_name, e)
            return False

    async def _ensure_working_llm_model(self) -> None:
        """Ensure we have a working LLM model (Issue #315: depth reduction).

        Tries the configured orchestrator model first, then falls back to default.

        Raises:
            Exception: If no working model is found
        """
        # Try primary model
        if await self._validate_llm_model(self.config.orchestrator_llm_model):
            logger.info(
                "✅ Orchestrator model '%s' is working",
                self.config.orchestrator_llm_model,
            )
            return

        logger.warning(
            "⚠️ Orchestrator model '%s' test failed", self.config.orchestrator_llm_model
        )

        # Try fallback model
        fallback_model = config_manager.get_default_llm_model()
        if await self._validate_llm_model(fallback_model):
            logger.info("✅ Using fallback model: %s", fallback_model)
            self.config.orchestrator_llm_model = fallback_model
            return

        logger.error("❌ Fallback model '%s' also failed", fallback_model)
        raise Exception("No working LLM models available")

    async def initialize(self) -> None:
        """Initialize orchestrator components.

        Issue #315: Refactored to use helper methods for reduced nesting depth.
        """
        logger.info("Initializing Consolidated Orchestrator...")

        try:
            # Issue #379: Initialize core components in parallel
            await asyncio.gather(
                self.llm_interface.initialize(),
                self.memory_manager.initialize(),
                self.agent_manager.initialize(),
            )

            # Validate LLM connection
            ollama_connected = await self.llm_interface.check_ollama_connection()
            if not ollama_connected:
                logger.error("❌ Failed to connect to Ollama")
                raise Exception(
                    "Failed to connect to Ollama or configured models not found."
                )

            logger.info("✅ Ollama connection established")

            # Issue #315: Use helper for model validation (reduces nesting)
            await self._ensure_working_llm_model()

            self.is_running = True
            self.start_time = datetime.now()
            logger.info("✅ Consolidated Orchestrator initialization complete")

        except Exception as e:
            logger.error("❌ Orchestrator initialization failed: %s", e)
            raise

    async def shutdown(self) -> None:
        """Shutdown orchestrator gracefully"""
        logger.info("Shutting down Consolidated Orchestrator...")

        self.is_running = False

        # Complete pending tasks
        if self.active_tasks:
            logger.info(
                "Waiting for %d active tasks to complete...", len(self.active_tasks)
            )
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)  # Brief wait for tasks

        # Issue #379: Cleanup components in parallel
        try:
            await asyncio.gather(
                self.llm_interface.cleanup(),
                self.memory_manager.cleanup(),
                self.agent_manager.cleanup(),
                return_exceptions=True,  # Don't fail if one cleanup fails
            )
        except Exception as e:
            logger.warning("Cleanup warning: %s", e)

        # Log final metrics
        uptime = datetime.now() - self.start_time if self.start_time else 0
        logger.info("Orchestrator session %s completed:", self.session_id)
        logger.info("  Uptime: %s", uptime)
        logger.info("  Tasks completed: %s", self.metrics["tasks_completed"])
        logger.info("  Tasks failed: %s", self.metrics["tasks_failed"])
        logger.info("✅ Orchestrator shutdown complete")

    def _start_request_tracking(
        self,
        task_id: str,
        user_message: str,
        priority: TaskPriority,
        context: Optional[Dict[str, Any]],
    ) -> None:
        """Start task tracking for user request. Issue #620."""
        task_tracker.start_task(
            task_id=task_id,
            task_type=TaskType.USER_REQUEST,
            description=user_message[:200],
            priority=Priority(priority.value),
            context=context or {},
        )

    def _update_success_metrics(self, processing_time: float) -> None:
        """Update metrics after successful request processing. Issue #620."""
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
        """Process user request with enhanced orchestration. Issue #281, #620."""
        start_time = time.time()
        task_id = str(uuid.uuid4())
        logger.info("Processing user request %s: %s...", task_id, user_message[:100])

        try:
            self._start_request_tracking(task_id, user_message, priority, context)
            classification_result = await self._classify_task(user_message)
            target_llm_model = self._select_model_for_task(classification_result)

            result = await self._execute_mode_request(
                mode,
                user_message,
                task_id,
                target_llm_model,
                classification_result,
                context,
            )

            processing_time = time.time() - start_time
            self._update_success_metrics(processing_time)
            task_tracker.complete_task(task_id, result)
            logger.info("✅ Request %s completed in %.2fs", task_id, processing_time)

            return self._build_success_response(
                task_id,
                result,
                processing_time,
                classification_result,
                target_llm_model,
                mode,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            self.metrics["tasks_failed"] += 1
            task_tracker.fail_task(task_id, str(e))
            logger.error(
                "❌ Request %s failed after %.2fs: %s", task_id, processing_time, e
            )
            return self._build_failure_response(task_id, e, processing_time, mode)

    async def _classify_task(self, user_message: str) -> Optional[Any]:
        """Classify user request if classification agent is available (Issue #281 - extracted helper)."""
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
        """Select appropriate LLM model based on task classification (Issue #281 - extracted helper)."""
        if (
            classification_result
            and classification_result.complexity == TaskComplexity.SIMPLE
        ):
            model = config_manager.get_default_llm_model()
            logger.info("Using fast model for simple task: %s", model)
            return model
        logger.info(
            "Generating plan using Orchestrator LLM: %s",
            self.config.orchestrator_llm_model,
        )
        return self.config.orchestrator_llm_model

    async def _execute_mode_request(
        self,
        mode: OrchestrationMode,
        user_message: str,
        task_id: str,
        target_llm_model: str,
        classification_result: Optional[Any],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute request based on orchestration mode (Issue #281 - extracted helper)."""
        if mode == OrchestrationMode.SIMPLE:
            return await self._process_simple_request(
                user_message, task_id, target_llm_model, context
            )
        elif mode == OrchestrationMode.ENHANCED:
            return await self._process_enhanced_request(
                user_message, task_id, target_llm_model, classification_result, context
            )
        elif mode == OrchestrationMode.PARALLEL:
            return await self._process_parallel_request(
                user_message, task_id, target_llm_model, context
            )
        else:  # SEQUENTIAL
            return await self._process_sequential_request(
                user_message, task_id, target_llm_model, context
            )

    def _build_success_response(
        self,
        task_id: str,
        result: Dict[str, Any],
        processing_time: float,
        classification_result: Optional[Any],
        target_llm_model: str,
        mode: OrchestrationMode,
    ) -> Dict[str, Any]:
        """Build success response for process_user_request (Issue #281 - extracted helper)."""
        return {
            "task_id": task_id,
            "success": True,
            "result": result,
            "processing_time": processing_time,
            "classification": (
                classification_result.to_dict() if classification_result else None
            ),
            "model_used": target_llm_model,
            "mode": mode.value,
        }

    def _build_failure_response(
        self,
        task_id: str,
        error: Exception,
        processing_time: float,
        mode: OrchestrationMode,
    ) -> Dict[str, Any]:
        """Build failure response for process_user_request (Issue #281 - extracted helper)."""
        return {
            "task_id": task_id,
            "success": False,
            "error": str(error),
            "processing_time": processing_time,
            "mode": mode.value,
        }

    async def _process_simple_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process simple request with minimal orchestration"""
        response = await self.llm_interface.generate_response(
            user_message,
            model=model,
            max_tokens=LLMDefaults.ENRICHED_MAX_TOKENS,
            context=context,
        )

        return {
            "type": "simple_response",
            "content": response,
            "sources": [{"type": "llm", "model": model}],
        }

    async def _process_enhanced_request(
        self,
        user_message: str,
        task_id: str,
        model: str,
        classification: Optional[Any],
        context: Optional[Dict],
    ) -> Dict[str, Any]:
        """Process request with enhanced orchestration features"""

        # Determine optimal agents based on classification
        suggested_agents = []
        if classification and classification.suggested_agents:
            suggested_agents = classification.suggested_agents
        else:
            # Default agent selection
            suggested_agents = ["general"]

        # Execute with appropriate agents
        if len(suggested_agents) == 1:
            # Single agent execution
            agent_result = await self.agent_manager.execute_agent_task(
                agent_name=suggested_agents[0], task=user_message, context=context
            )

            return {
                "type": "agent_response",
                "content": agent_result.get("response", ""),
                "agent_used": suggested_agents[0],
                "execution_details": agent_result,
                "classification": classification.to_dict() if classification else None,
            }
        else:
            # Multi-agent coordination
            return await self._coordinate_multiple_agents(
                user_message, suggested_agents, context, classification
            )

    async def _process_parallel_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process request with parallel execution"""

        # Create parallel tasks
        tasks = [
            self.llm_interface.generate_response(
                user_message, model=model, max_tokens=LLMDefaults.STANDARD_MAX_TOKENS
            ),
            self.memory_manager.search_relevant_context(user_message),
            # Add more parallel tasks as needed
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        llm_response = results[0] if not isinstance(results[0], Exception) else None
        context_results = results[1] if not isinstance(results[1], Exception) else []

        return {
            "type": "parallel_response",
            "content": llm_response,
            "context": context_results,
            "execution_method": "parallel",
        }

    async def _process_sequential_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process request with sequential execution"""

        # Step 1: Context retrieval
        relevant_context = await self.memory_manager.search_relevant_context(
            user_message
        )

        # Step 2: Enhanced prompt with context
        enhanced_prompt = f"Context: {relevant_context}\n\nUser Request: {user_message}"

        # Step 3: Generate response
        response = await self.llm_interface.generate_response(
            enhanced_prompt, model=model, max_tokens=LLMDefaults.ENRICHED_MAX_TOKENS
        )

        return {
            "type": "sequential_response",
            "content": response,
            "context_used": relevant_context,
            "execution_method": "sequential",
        }

    async def _execute_agents_sequentially(
        self,
        user_message: str,
        agent_names: List[str],
        context: Optional[Dict],
    ) -> tuple[Dict[str, Any], List[str]]:
        """Execute agents sequentially for complex tasks. Issue #620."""
        agent_results = {}
        execution_order = []

        for agent_name in agent_names:
            try:
                result = await self.agent_manager.execute_agent_task(
                    agent_name=agent_name,
                    task=user_message,
                    context={**(context or {}), "previous_results": agent_results},
                )
                agent_results[agent_name] = result
                execution_order.append(agent_name)
            except Exception as e:
                logger.warning("Agent %s failed: %s", agent_name, e)
                agent_results[agent_name] = {"error": str(e)}

        return agent_results, execution_order

    async def _execute_agents_in_parallel(
        self,
        user_message: str,
        agent_names: List[str],
        context: Optional[Dict],
    ) -> tuple[Dict[str, Any], List[str]]:
        """Execute agents in parallel for simpler tasks. Issue #620."""
        tasks = [
            (
                agent_name,
                self.agent_manager.execute_agent_task(
                    agent_name=agent_name, task=user_message, context=context
                ),
            )
            for agent_name in agent_names
        ]

        results = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        agent_results = {}
        execution_order = []
        for i, (agent_name, _) in enumerate(tasks):
            if isinstance(results[i], Exception):
                agent_results[agent_name] = {"error": str(results[i])}
            else:
                agent_results[agent_name] = results[i]
            execution_order.append(agent_name)

        return agent_results, execution_order

    async def _coordinate_multiple_agents(
        self,
        user_message: str,
        agent_names: List[str],
        context: Optional[Dict],
        classification: Optional[Any],
    ) -> Dict[str, Any]:
        """Coordinate execution across multiple agents."""
        is_complex = (
            classification and classification.complexity == TaskComplexity.COMPLEX
        )

        if is_complex:
            agent_results, execution_order = await self._execute_agents_sequentially(
                user_message, agent_names, context
            )
        else:
            agent_results, execution_order = await self._execute_agents_in_parallel(
                user_message, agent_names, context
            )

        synthesis = await self._synthesize_agent_results(user_message, agent_results)

        return {
            "type": "multi_agent_response",
            "content": synthesis,
            "agent_results": agent_results,
            "execution_order": execution_order,
            "classification": classification.to_dict() if classification else None,
        }

    async def _synthesize_agent_results(
        self, user_message: str, agent_results: Dict[str, Any]
    ) -> str:
        """Synthesize results from multiple agents"""

        # Create synthesis prompt
        synthesis_prompt = f"""
        User Request: {user_message}

        Agent Results:
        {json.dumps(agent_results, indent=2)}

        Please provide a comprehensive response that synthesizes the information from all agents.
        Focus on providing a clear, actionable answer to the user's request.
        """

        # Generate synthesis
        synthesis = await self.llm_interface.generate_response(
            synthesis_prompt,
            model=self.config.orchestrator_llm_model,
            max_tokens=LLMDefaults.EXTENDED_MAX_TOKENS,
        )

        return synthesis

    # ========================================================================
    # Enhanced Agent Management Methods (from enhanced_orchestrator)
    # ========================================================================

    async def register_agent(self, agent_profile: AgentProfile) -> bool:
        """Register a new agent with the orchestrator"""
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
    ) -> Optional[str]:
        """
        Find the best agent for a specific task based on capabilities and current workload.

        Uses shared utility from utils.agent_selection (Issue #292).
        """
        return _find_best_agent(
            agent_registry=self.agent_registry,
            task_type=task_type,
            required_capabilities=required_capabilities,
        )

    def _reserve_agent(self, agent_id: str):
        """Reserve an agent for task execution.

        Uses shared utility from utils.agent_selection (Issue #292).
        """
        _reserve_agent(self.agent_registry, agent_id)

    def _release_agent(self, agent_id: str):
        """Release an agent after task completion.

        Uses shared utility from utils.agent_selection (Issue #292).
        """
        _release_agent(self.agent_registry, agent_id)

    def _update_agent_performance(
        self, agent_id: str, success: bool, execution_time: float
    ):
        """Update agent performance metrics.

        Uses shared utility from utils.agent_selection (Issue #292).
        """
        _update_performance(
            agent_registry=self.agent_registry,
            agent_id=agent_id,
            success=success,
            execution_time=execution_time,
        )

    def set_phi2_enabled(self, enabled: bool):
        """Set Phi-2 model enabled status"""
        self.config.phi2_enabled = enabled
        logger.info("Phi-2 enabled status set to: %s", self.config.phi2_enabled)

        # Publish configuration change
        try:
            from utils.event_manager import event_manager

            event_manager.publish("settings_update", {"phi2_enabled": enabled})
        except ImportError:
            logger.debug("Event manager not available for settings update")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator status and metrics (enhanced version)"""
        uptime = datetime.now() - self.start_time if self.start_time else 0

        return {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "uptime": str(uptime),
            "active_tasks": len(self.active_tasks),
            "queued_tasks": len(self.task_queue),
            "metrics": self.metrics,
            "workflow_metrics": self.workflow_metrics,
            "configuration": {
                "orchestrator_model": self.config.orchestrator_llm_model,
                "task_model": self.config.task_llm_model,
                "max_parallel_tasks": self.config.max_parallel_tasks,
                "classification_enabled": self.classification_agent is not None,
                "auto_doc_enabled": self.auto_doc_enabled,
                "knowledge_extraction_enabled": self.knowledge_extraction_enabled,
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
            "active_workflows": len(
                [
                    doc
                    for doc in self.workflow_documentation.values()
                    if doc.content.get("status") == "in_progress"
                ]
            ),
            "total_documentation": len(self.workflow_documentation),
            "total_interactions": len(self.agent_interactions),
        }

    async def update_configuration(self, new_config: Dict[str, Any]) -> bool:
        """Update orchestrator configuration dynamically"""
        try:
            # Update configuration
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.info("Updated configuration: %s = %s", key, value)

            # Reinitialize components if needed
            if "orchestrator_llm_model" in new_config:
                logger.info("Reinitializing LLM interface with new model")
                await self.llm_interface.initialize()

            return True

        except Exception as e:
            logger.error("Failed to update configuration: %s", e)
            return False

    # ========================================================================
    # Backward Compatibility Methods
    # ========================================================================

    async def classify_request_complexity(self, user_request: str) -> TaskComplexity:
        """
        Classify request complexity (backward compatibility method).

        This method provides backward compatibility for code that expects
        the old orchestrator interface.
        """
        if not CLASSIFICATION_AVAILABLE:
            logger.warning("Classification agent not available, defaulting to COMPLEX")
            return TaskComplexity.COMPLEX

        try:
            if self.classification_agent:
                result = await self.classification_agent.classify_user_request(
                    user_request
                )
                return result.complexity
            else:
                logger.warning(
                    "Classification agent not initialized, defaulting to COMPLEX"
                )
                return TaskComplexity.COMPLEX
        except Exception as e:
            logger.error("Classification failed: %s, defaulting to COMPLEX", e)
            return TaskComplexity.COMPLEX

    def _create_simple_workflow_step(self, user_request: str) -> WorkflowStep:
        """Create a single workflow step for simple requests. Issue #620."""
        return WorkflowStep(
            id="step_1",
            agent_type="llm",
            action="generate_response",
            description="Generate direct response to user query",
            requires_approval=False,
            dependencies=[],
            inputs={"query": user_request},
            expected_duration_ms=2000,
        )

    def _create_complex_workflow_steps(self, user_request: str) -> List[WorkflowStep]:
        """Create multi-step workflow for complex requests. Issue #620."""
        return [
            WorkflowStep(
                id="step_1",
                agent_type="analyzer",
                action="analyze_request",
                description="Analyze user request and determine requirements",
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
                description="Synthesize results and generate final response",
                requires_approval=False,
                dependencies=["step_2"],
                inputs={"query": user_request},
                expected_duration_ms=2000,
            ),
        ]

    async def plan_workflow_steps(
        self, user_request: str, complexity: TaskComplexity
    ) -> List[WorkflowStep]:
        """
        Plan workflow steps based on request complexity (backward compatibility method).

        This method provides backward compatibility for code that expects
        the old orchestrator interface.
        """
        if not WORKFLOW_TYPES_AVAILABLE:
            logger.warning("Workflow types not available, returning empty step list")
            return []

        try:
            if complexity == TaskComplexity.SIMPLE:
                steps = [self._create_simple_workflow_step(user_request)]
            else:
                steps = self._create_complex_workflow_steps(user_request)

            logger.info(
                "Generated %d workflow steps for %s task", len(steps), complexity.value
            )
            return steps

        except Exception as e:
            logger.error("Failed to plan workflow steps: %s", e)
            return []


# Global orchestrator instance (thread-safe)
_orchestrator_instance = None
_orchestrator_lock = asyncio.Lock()


async def get_orchestrator() -> ConsolidatedOrchestrator:
    """Get or create global orchestrator instance (thread-safe)"""
    global _orchestrator_instance

    if _orchestrator_instance is None:
        async with _orchestrator_lock:
            # Double-check after acquiring lock
            if _orchestrator_instance is None:
                _orchestrator_instance = ConsolidatedOrchestrator()
                await _orchestrator_instance.initialize()

    return _orchestrator_instance


async def shutdown_orchestrator():
    """Shutdown global orchestrator instance (thread-safe)"""
    global _orchestrator_instance

    async with _orchestrator_lock:
        if _orchestrator_instance:
            await _orchestrator_instance.shutdown()
            _orchestrator_instance = None


# ============================================================================
# Backward Compatibility Alias
# ============================================================================

# Provide backward compatibility for code expecting "Orchestrator" class
Orchestrator = ConsolidatedOrchestrator


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    # Main orchestrator classes
    "Orchestrator",  # Backward compatibility alias
    "ConsolidatedOrchestrator",
    "OrchestratorConfig",
    # Enums
    "TaskPriority",
    "OrchestrationMode",
    "TaskComplexity",
    "WorkflowStatus",
    "AgentCapability",  # Enhanced feature from enhanced_orchestrator
    "DocumentationType",  # Enhanced feature from enhanced_orchestrator
    # Data classes
    "WorkflowStep",
    "AgentProfile",  # Enhanced feature from enhanced_orchestrator
    "WorkflowDocumentation",  # Enhanced feature from enhanced_orchestrator
    "AgentInteraction",  # Enhanced feature from enhanced_orchestrator
    # Functions
    "get_orchestrator",
    "shutdown_orchestrator",
]
