# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Orchestrator for AutoBot - Phase 5 Code Consolidation

This module consolidates all orchestrator implementations into a single,
comprehensive orchestrator that integrates the best features from:
- src/orchestrator.py (main orchestrator)
- src/enhanced_orchestrator.py (enhanced features)
- src/langchain_agent_orchestrator.py (LangChain integration)
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.circuit_breaker import circuit_breaker_async
from src.constants.network_constants import NetworkConstants
from src.conversation import ConversationManager
from src.llm_interface import LLMInterface
from src.retry_mechanism import RetryStrategy, retry_network_operation
from src.task_execution_tracker import Priority, TaskType, task_tracker
from src.unified_config_manager import config_manager
from src.unified_memory_manager import LongTermMemoryManager
from src.utils.logging_manager import get_logger

# Import KnowledgeBase for enhanced features
try:
    from src.knowledge_base import KnowledgeBase

    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False
    logger.warning("KnowledgeBase not available - auto-documentation features disabled")

# Import TaskComplexity from correct location (always available)
from src.autobot_types import TaskComplexity

# Import task classification (optional)
try:
    from src.agents.gemma_classification_agent import GemmaClassificationAgent

    # Note: TaskClassificationResult doesn't exist yet, using quoted type annotations
    # from src.task_classification import TaskClassificationResult

    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False

# Import agent manager
try:
    from src.agents.agent_manager import AgentManager

    AGENT_MANAGER_AVAILABLE = True
except ImportError:
    AGENT_MANAGER_AVAILABLE = False

    # Create a fallback AgentManager class
    class AgentManager:
        """Fallback AgentManager when the real one is not available"""

        async def initialize(self):
            pass

        async def cleanup(self):
            pass

        async def execute_agent_task(self, agent_name, task, context=None):
            return {"error": "Agent manager not available", "agent_name": agent_name}


# Import workflow types for backward compatibility
try:
    from src.workflow_scheduler import WorkflowStatus
    from src.workflow_templates import WorkflowStep

    WORKFLOW_TYPES_AVAILABLE = True
except ImportError:
    WORKFLOW_TYPES_AVAILABLE = False
    # Define minimal fallback types
    from dataclasses import dataclass
    from enum import Enum

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


logger = get_logger("orchestrator")


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


class AgentCapability(Enum):
    """Agent capabilities for dynamic task assignment"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    DOCUMENTATION = "documentation"
    CODE_GENERATION = "code_generation"
    SYSTEM_OPERATIONS = "system_operations"
    DATA_PROCESSING = "data_processing"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    WORKFLOW_COORDINATION = "workflow_coordination"


class DocumentationType(Enum):
    """Types of auto-generated documentation"""

    WORKFLOW_SUMMARY = "workflow_summary"
    AGENT_INTERACTION = "agent_interaction"
    DECISION_LOG = "decision_log"
    PERFORMANCE_REPORT = "performance_report"
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"
    ERROR_ANALYSIS = "error_analysis"


@dataclass
class AgentProfile:
    """Enhanced agent profile with capabilities and performance metrics"""

    agent_id: str
    agent_type: str
    capabilities: Set[AgentCapability]
    specializations: List[str]
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    availability_status: str = "available"
    current_workload: int = 0
    max_concurrent_tasks: int = 3
    success_rate: float = 1.0
    average_completion_time: float = 0.0
    preferred_task_types: List[str] = field(default_factory=list)


@dataclass
class WorkflowDocumentation:
    """Auto-generated documentation for workflow execution"""

    workflow_id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    documentation_type: DocumentationType
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    related_workflows: List[str] = field(default_factory=list)
    knowledge_extracted: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentInteraction:
    """Record of interaction between agents"""

    interaction_id: str
    timestamp: datetime
    source_agent: str
    target_agent: str
    interaction_type: str  # request, response, notification, collaboration
    message: Dict[str, Any]
    context: Dict[str, Any]
    outcome: str = "pending"


class OrchestratorConfig:
    """Configuration for the Orchestrator"""

    def __init__(self, config_manager):
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
            f"Orchestrator configured with model: {self.orchestrator_llm_model}"
        )


class ConsolidatedOrchestrator:
    """
    Consolidated Orchestrator for AutoBot - Phase 5

    Integrates all orchestrator features into a single, comprehensive system
    """

    def __init__(self, config_mgr=None):
        # Use provided config_manager or fall back to global config_manager
        from src.unified_config_manager import config_manager as global_config_manager

        self.config_manager = config_mgr or global_config_manager
        self.config = OrchestratorConfig(self.config_manager)

        # Core components
        self.llm_interface = LLMInterface()
        self.memory_manager = LongTermMemoryManager()
        self.conversation_manager = ConversationManager()
        self.agent_manager = AgentManager()

        # Task management
        self.active_tasks = {}
        self.task_queue = []
        self.completed_tasks = {}

        # State management
        self.is_running = False
        self.session_id = str(uuid.uuid4())
        self.start_time = None

        # Performance tracking
        self.metrics = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0,
            "average_response_time": 0,
        }

        # Enhanced orchestrator components (from enhanced_orchestrator)
        self.agent_registry: Dict[str, AgentProfile] = {}
        self.workflow_documentation: Dict[str, WorkflowDocumentation] = {}
        self.agent_interactions: List[AgentInteraction] = []

        # Initialize knowledge base if available
        if KNOWLEDGE_BASE_AVAILABLE:
            self.knowledge_base = KnowledgeBase()
        else:
            self.knowledge_base = None

        # Auto-documentation settings
        self.auto_doc_enabled = True
        self.doc_generation_threshold = (
            0.8  # Generate docs for workflows with >80% completion
        )
        self.knowledge_extraction_enabled = KNOWLEDGE_BASE_AVAILABLE

        # Enhanced workflow metrics
        self.workflow_metrics = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "average_execution_time": 0.0,
            "agent_utilization": {},
            "documentation_generated": 0,
            "knowledge_extracted": 0,
        }

        # Classification agent
        self.classification_agent = None
        if CLASSIFICATION_AVAILABLE:
            try:
                self.classification_agent = GemmaClassificationAgent()
                logger.info("Classification agent initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize classification agent: {e}")

        # Initialize default agent profiles
        self._initialize_default_agents()

        logger.info(
            f"Consolidated Orchestrator initialized with session: {self.session_id}"
        )

    def _initialize_default_agents(self):
        """Initialize default agent profiles"""
        default_agents = [
            AgentProfile(
                agent_id="research_agent",
                agent_type="research",
                capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
                specializations=[
                    "web_search",
                    "data_analysis",
                    "information_synthesis",
                ],
                max_concurrent_tasks=5,
                preferred_task_types=["research", "information_gathering", "analysis"],
            ),
            AgentProfile(
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
            ),
            AgentProfile(
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
            ),
            AgentProfile(
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
            ),
        ]

        for agent in default_agents:
            self.agent_registry[agent.agent_id] = agent

        logger.info(f"Initialized {len(default_agents)} default agent profiles")

    async def initialize(self):
        """Initialize orchestrator components"""
        logger.info("Initializing Consolidated Orchestrator...")

        try:
            # Initialize core components
            await self.llm_interface.initialize()
            await self.memory_manager.initialize()
            await self.agent_manager.initialize()

            # Validate LLM connection
            ollama_connected = await self.llm_interface.check_ollama_connection()
            if ollama_connected:
                logger.info("✅ Ollama connection established")

                # Test orchestrator model availability
                try:
                    test_response = await self.llm_interface.generate_response(
                        "Test connection",
                        model=self.config.orchestrator_llm_model,
                        max_tokens=10,
                    )
                    if test_response:
                        logger.info(
                            f"✅ Orchestrator model '{self.config.orchestrator_llm_model}' is working"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Orchestrator model '{self.config.orchestrator_llm_model}' test failed"
                        )
                except Exception as e:
                    logger.error(
                        f"❌ Orchestrator model '{self.config.orchestrator_llm_model}' is not available: {e}"
                    )
                    # Try fallback model
                    try:
                        fallback_model = config_manager.get_default_llm_model()
                        test_response = await self.llm_interface.generate_response(
                            "Test connection", model=fallback_model, max_tokens=10
                        )
                        if test_response:
                            logger.info(f"✅ Using fallback model: {fallback_model}")
                            self.config.orchestrator_llm_model = fallback_model
                        else:
                            raise Exception("Fallback model also failed")
                    except Exception as fallback_error:
                        logger.error(f"❌ Fallback model also failed: {fallback_error}")
                        raise Exception("No working LLM models available")
            else:
                logger.error("❌ Failed to connect to Ollama")
                raise Exception(
                    "Failed to connect to Ollama or configured models not found."
                )

            self.is_running = True
            self.start_time = datetime.now()
            logger.info("✅ Consolidated Orchestrator initialization complete")

        except Exception as e:
            logger.error(f"❌ Orchestrator initialization failed: {e}")
            raise

    async def shutdown(self):
        """Shutdown orchestrator gracefully"""
        logger.info("Shutting down Consolidated Orchestrator...")

        self.is_running = False

        # Complete pending tasks
        if self.active_tasks:
            logger.info(
                f"Waiting for {len(self.active_tasks)} active tasks to complete..."
            )
            await asyncio.sleep(2)  # Brief wait for tasks to complete

        # Cleanup components
        try:
            await self.llm_interface.cleanup()
            await self.memory_manager.cleanup()
            await self.agent_manager.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")

        # Log final metrics
        uptime = datetime.now() - self.start_time if self.start_time else 0
        logger.info(f"Orchestrator session {self.session_id} completed:")
        logger.info(f"  Uptime: {uptime}")
        logger.info(f"  Tasks completed: {self.metrics['tasks_completed']}")
        logger.info(f"  Tasks failed: {self.metrics['tasks_failed']}")
        logger.info("✅ Orchestrator shutdown complete")

    async def process_user_request(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        mode: OrchestrationMode = OrchestrationMode.ENHANCED,
        priority: TaskPriority = TaskPriority.NORMAL,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process user request with enhanced orchestration"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        logger.info(f"Processing user request {task_id}: {user_message[:100]}...")

        try:
            # Track task
            task_tracker.start_task(
                task_id=task_id,
                task_type=TaskType.USER_REQUEST,
                description=user_message[:200],
                priority=Priority(priority.value),
                context=context or {},
            )

            # Classify task if available
            classification_result = None
            if self.classification_agent:
                try:
                    classification_result = (
                        await self.classification_agent.classify_user_request(
                            user_message
                        )
                    )
                    logger.info(
                        f"Task classified: {classification_result.complexity.value} complexity"
                    )
                except Exception as e:
                    logger.warning(f"Classification failed: {e}")

            # Generate execution plan
            target_llm_model = self.config.orchestrator_llm_model

            if (
                classification_result
                and classification_result.complexity == TaskComplexity.SIMPLE
            ):
                # Use faster model for simple tasks
                target_llm_model = config_manager.get_default_llm_model()
                logger.info(f"Using fast model for simple task: {target_llm_model}")
            else:
                logger.info(
                    f"Generating plan using Orchestrator LLM: {target_llm_model}"
                )

            # Generate response based on mode
            if mode == OrchestrationMode.SIMPLE:
                result = await self._process_simple_request(
                    user_message, task_id, target_llm_model, context
                )
            elif mode == OrchestrationMode.ENHANCED:
                result = await self._process_enhanced_request(
                    user_message,
                    task_id,
                    target_llm_model,
                    classification_result,
                    context,
                )
            elif mode == OrchestrationMode.PARALLEL:
                result = await self._process_parallel_request(
                    user_message, task_id, target_llm_model, context
                )
            else:  # SEQUENTIAL
                result = await self._process_sequential_request(
                    user_message, task_id, target_llm_model, context
                )

            # Update metrics
            processing_time = time.time() - start_time
            self.metrics["tasks_completed"] += 1
            self.metrics["total_processing_time"] += processing_time
            self.metrics["average_response_time"] = (
                self.metrics["total_processing_time"] / self.metrics["tasks_completed"]
            )

            # Complete task tracking
            task_tracker.complete_task(task_id, result)

            logger.info(f"✅ Request {task_id} completed in {processing_time:.2f}s")

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

        except Exception as e:
            # Update failure metrics
            processing_time = time.time() - start_time
            self.metrics["tasks_failed"] += 1

            # Track failure
            task_tracker.fail_task(task_id, str(e))

            logger.error(
                f"❌ Request {task_id} failed after {processing_time:.2f}s: {e}"
            )

            return {
                "task_id": task_id,
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "mode": mode.value,
            }

    async def _process_simple_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process simple request with minimal orchestration"""
        response = await self.llm_interface.generate_response(
            user_message, model=model, max_tokens=1000, context=context
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
        classification: Optional["TaskClassificationResult"],
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
                user_message, model=model, max_tokens=500
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
            enhanced_prompt, model=model, max_tokens=1000
        )

        return {
            "type": "sequential_response",
            "content": response,
            "context_used": relevant_context,
            "execution_method": "sequential",
        }

    async def _coordinate_multiple_agents(
        self,
        user_message: str,
        agent_names: List[str],
        context: Optional[Dict],
        classification: Optional["TaskClassificationResult"],
    ) -> Dict[str, Any]:
        """Coordinate execution across multiple agents"""

        agent_results = {}
        execution_order = []

        # Execute agents based on complexity
        if classification and classification.complexity == TaskComplexity.COMPLEX:
            # Sequential execution for complex tasks
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
                    logger.warning(f"Agent {agent_name} failed: {e}")
                    agent_results[agent_name] = {"error": str(e)}
        else:
            # Parallel execution for simpler tasks
            tasks = []
            for agent_name in agent_names:
                task = self.agent_manager.execute_agent_task(
                    agent_name=agent_name, task=user_message, context=context
                )
                tasks.append((agent_name, task))

            # Execute in parallel
            results = await asyncio.gather(
                *[task for _, task in tasks], return_exceptions=True
            )

            for i, (agent_name, _) in enumerate(tasks):
                if isinstance(results[i], Exception):
                    agent_results[agent_name] = {"error": str(results[i])}
                else:
                    agent_results[agent_name] = results[i]
                execution_order.append(agent_name)

        # Synthesize results
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
            synthesis_prompt, model=self.config.orchestrator_llm_model, max_tokens=1500
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
                    f"Agent {agent_profile.agent_id} already registered, updating profile"
                )

            self.agent_registry[agent_profile.agent_id] = agent_profile
            logger.info(
                f"Agent {agent_profile.agent_id} registered with capabilities: {agent_profile.capabilities}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to register agent {agent_profile.agent_id}: {e}")
            return False

    def find_best_agent_for_task(
        self, task_type: str, required_capabilities: Set[AgentCapability] = None
    ) -> Optional[str]:
        """
        Find the best agent for a specific task based on capabilities and current workload
        """
        required_capabilities = required_capabilities or set()

        suitable_agents = []

        for agent_id, agent in self.agent_registry.items():
            # Check availability
            if agent.availability_status != "available":
                continue

            # Check workload capacity
            if agent.current_workload >= agent.max_concurrent_tasks:
                continue

            # Check capabilities
            if required_capabilities and not required_capabilities.issubset(
                agent.capabilities
            ):
                continue

            # Check task type preference
            task_match_score = 0
            if task_type in agent.preferred_task_types:
                task_match_score += 2
            if any(spec in task_type for spec in agent.specializations):
                task_match_score += 1

            # Calculate overall suitability score
            workload_factor = 1.0 - (
                agent.current_workload / agent.max_concurrent_tasks
            )
            performance_factor = agent.success_rate

            suitability_score = (
                (task_match_score * 0.4)
                + (workload_factor * 0.3)
                + (performance_factor * 0.3)
            )

            suitable_agents.append((agent_id, suitability_score))

        if not suitable_agents:
            logger.warning(f"No suitable agent found for task type: {task_type}")
            return None

        # Return agent with highest suitability score
        suitable_agents.sort(key=lambda x: x[1], reverse=True)
        best_agent_id = suitable_agents[0][0]

        logger.debug(
            f"Selected agent {best_agent_id} for task {task_type} (score: {suitable_agents[0][1]:.2f})"
        )
        return best_agent_id

    def _reserve_agent(self, agent_id: str):
        """Reserve an agent for task execution"""
        if agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            agent.current_workload += 1
            agent.availability_status = (
                "busy"
                if agent.current_workload >= agent.max_concurrent_tasks
                else "available"
            )

    def _release_agent(self, agent_id: str):
        """Release an agent after task completion"""
        if agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            agent.current_workload = max(0, agent.current_workload - 1)
            agent.availability_status = (
                "available"
                if agent.current_workload < agent.max_concurrent_tasks
                else "busy"
            )

    def _update_agent_performance(
        self, agent_id: str, success: bool, execution_time: float
    ):
        """Update agent performance metrics"""
        if agent_id not in self.agent_registry:
            return

        agent = self.agent_registry[agent_id]

        # Update success rate
        current_attempts = agent.performance_metrics.get("total_attempts", 0)
        current_successes = agent.performance_metrics.get("total_successes", 0)

        new_attempts = current_attempts + 1
        new_successes = current_successes + (1 if success else 0)

        agent.success_rate = new_successes / new_attempts if new_attempts > 0 else 1.0
        agent.performance_metrics["total_attempts"] = new_attempts
        agent.performance_metrics["total_successes"] = new_successes

        # Update average completion time
        current_avg_time = agent.average_completion_time
        if current_avg_time == 0:
            agent.average_completion_time = execution_time
        else:
            # Weighted average (give more weight to recent performance)
            agent.average_completion_time = (current_avg_time * 0.7) + (
                execution_time * 0.3
            )

        logger.debug(
            f"Updated agent {agent_id} performance: success_rate={agent.success_rate:.2f}, avg_time={agent.average_completion_time:.2f}s"
        )

    def set_phi2_enabled(self, enabled: bool):
        """Set Phi-2 model enabled status"""
        self.config.phi2_enabled = enabled
        logger.info(f"Phi-2 enabled status set to: {self.config.phi2_enabled}")

        # Publish configuration change
        try:
            from src.utils.event_manager import event_manager

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
                    logger.info(f"Updated configuration: {key} = {value}")

            # Reinitialize components if needed
            if "orchestrator_llm_model" in new_config:
                logger.info("Reinitializing LLM interface with new model")
                await self.llm_interface.initialize()

            return True

        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
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
            logger.error(f"Classification failed: {e}, defaulting to COMPLEX")
            return TaskComplexity.COMPLEX

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
            # Create a basic workflow plan based on complexity
            steps = []

            if complexity == TaskComplexity.SIMPLE:
                # Simple request: single LLM response step
                steps.append(
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
                )
            else:  # COMPLEX
                # Complex request: multi-step workflow
                steps.extend(
                    [
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
                )

            logger.info(
                f"Generated {len(steps)} workflow steps for {complexity.value} task"
            )
            return steps

        except Exception as e:
            logger.error(f"Failed to plan workflow steps: {e}")
            return []


# Global orchestrator instance
_orchestrator_instance = None


async def get_orchestrator() -> ConsolidatedOrchestrator:
    """Get or create global orchestrator instance"""
    global _orchestrator_instance

    if _orchestrator_instance is None:
        _orchestrator_instance = ConsolidatedOrchestrator()
        await _orchestrator_instance.initialize()

    return _orchestrator_instance


async def shutdown_orchestrator():
    """Shutdown global orchestrator instance"""
    global _orchestrator_instance

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
