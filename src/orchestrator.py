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
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from src.unified_config_manager import config_manager
from src.memory_manager import MemoryManager
from src.retry_mechanism import RetryStrategy, retry_network_operation
from src.circuit_breaker import circuit_breaker_async
from src.llm_interface import LLMInterface
from src.conversation import ConversationManager
from src.task_execution_tracker import task_tracker, Priority, TaskType
from src.agents.agent_manager import AgentManager
from src.utils.logging_manager import get_logger

# Import task classification
try:
    from src.agents.gemma_classification_agent import GemmaClassificationAgent
    from src.task_classification import TaskClassificationResult, TaskComplexity
    CLASSIFICATION_AVAILABLE = True
except ImportError:
    CLASSIFICATION_AVAILABLE = False


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
        default_model = llm_config.get("ollama", {}).get(
            "selected_model"
        )
        self.task_llm_model = llm_config.get(
            "task_llm",
            f"ollama_{default_model}",
        )
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False  # This will be driven by config if needed

        # Task configuration
        self.max_parallel_tasks = self.config_manager.get("orchestrator.max_parallel_tasks", 3)
        self.task_timeout = self.config_manager.get("orchestrator.task_timeout", 300)
        self.retry_attempts = self.config_manager.get("orchestrator.retry_attempts", 3)

        # Agent configuration
        self.agent_timeout = self.config_manager.get("orchestrator.agent_timeout", 120)
        self.max_agents = self.config_manager.get("orchestrator.max_agents", 5)

        # Performance settings
        self.enable_caching = self.config_manager.get("orchestrator.enable_caching", True)
        self.enable_streaming = self.config_manager.get("orchestrator.enable_streaming", True)

        logger.info(f"Orchestrator configured with model: {self.orchestrator_llm_model}")


class ConsolidatedOrchestrator:
    """
    Consolidated Orchestrator for AutoBot - Phase 5

    Integrates all orchestrator features into a single, comprehensive system
    """

    def __init__(self, config_manager=None):
        self.config_manager = config_manager or config_manager
        self.config = OrchestratorConfig(self.config_manager)

        # Core components
        self.llm_interface = LLMInterface()
        self.memory_manager = MemoryManager()
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
            "average_response_time": 0
        }

        # Classification agent
        self.classification_agent = None
        if CLASSIFICATION_AVAILABLE:
            try:
                self.classification_agent = GemmaClassificationAgent()
                logger.info("Classification agent initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize classification agent: {e}")

        logger.info(f"Consolidated Orchestrator initialized with session: {self.session_id}")

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
                        max_tokens=10
                    )
                    if test_response:
                        logger.info(f"✅ Orchestrator model '{self.config.orchestrator_llm_model}' is working")
                    else:
                        logger.warning(f"⚠️ Orchestrator model '{self.config.orchestrator_llm_model}' test failed")
                except Exception as e:
                    logger.error(f"❌ Orchestrator model '{self.config.orchestrator_llm_model}' is not available: {e}")
                    # Try fallback model
                    try:
                        fallback_model = "llama3.2:1b-instruct-q4_K_M"
                        test_response = await self.llm_interface.generate_response(
                            "Test connection",
                            model=fallback_model,
                            max_tokens=10
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
            logger.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
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
        context: Optional[Dict[str, Any]] = None
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
                context=context or {}
            )

            # Classify task if available
            classification_result = None
            if self.classification_agent:
                try:
                    classification_result = await self.classification_agent.classify_user_request(
                        user_message
                    )
                    logger.info(f"Task classified: {classification_result.complexity.value} complexity")
                except Exception as e:
                    logger.warning(f"Classification failed: {e}")

            # Generate execution plan
            target_llm_model = self.config.orchestrator_llm_model

            if classification_result and classification_result.complexity == TaskComplexity.SIMPLE:
                # Use faster model for simple tasks
                target_llm_model = "llama3.2:1b-instruct-q4_K_M"
                logger.info(f"Using fast model for simple task: {target_llm_model}")
            else:
                logger.info(f"Generating plan using Orchestrator LLM: {target_llm_model}")

            # Generate response based on mode
            if mode == OrchestrationMode.SIMPLE:
                result = await self._process_simple_request(
                    user_message, task_id, target_llm_model, context
                )
            elif mode == OrchestrationMode.ENHANCED:
                result = await self._process_enhanced_request(
                    user_message, task_id, target_llm_model, classification_result, context
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
                "classification": classification_result.to_dict() if classification_result else None,
                "model_used": target_llm_model,
                "mode": mode.value
            }

        except Exception as e:
            # Update failure metrics
            processing_time = time.time() - start_time
            self.metrics["tasks_failed"] += 1

            # Track failure
            task_tracker.fail_task(task_id, str(e))

            logger.error(f"❌ Request {task_id} failed after {processing_time:.2f}s: {e}")

            return {
                "task_id": task_id,
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "mode": mode.value
            }

    async def _process_simple_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process simple request with minimal orchestration"""
        response = await self.llm_interface.generate_response(
            user_message,
            model=model,
            max_tokens=1000,
            context=context
        )

        return {
            "type": "simple_response",
            "content": response,
            "sources": [{"type": "llm", "model": model}]
        }

    async def _process_enhanced_request(
        self,
        user_message: str,
        task_id: str,
        model: str,
        classification: Optional[TaskClassificationResult],
        context: Optional[Dict]
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
                agent_name=suggested_agents[0],
                task=user_message,
                context=context
            )

            return {
                "type": "agent_response",
                "content": agent_result.get("response", ""),
                "agent_used": suggested_agents[0],
                "execution_details": agent_result,
                "classification": classification.to_dict() if classification else None
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
            "execution_method": "parallel"
        }

    async def _process_sequential_request(
        self, user_message: str, task_id: str, model: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Process request with sequential execution"""

        # Step 1: Context retrieval
        relevant_context = await self.memory_manager.search_relevant_context(user_message)

        # Step 2: Enhanced prompt with context
        enhanced_prompt = f"Context: {relevant_context}\n\nUser Request: {user_message}"

        # Step 3: Generate response
        response = await self.llm_interface.generate_response(
            enhanced_prompt,
            model=model,
            max_tokens=1000
        )

        return {
            "type": "sequential_response",
            "content": response,
            "context_used": relevant_context,
            "execution_method": "sequential"
        }

    async def _coordinate_multiple_agents(
        self,
        user_message: str,
        agent_names: List[str],
        context: Optional[Dict],
        classification: Optional[TaskClassificationResult]
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
                        context={**(context or {}), "previous_results": agent_results}
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
                    agent_name=agent_name,
                    task=user_message,
                    context=context
                )
                tasks.append((agent_name, task))

            # Execute in parallel
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

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
            "classification": classification.to_dict() if classification else None
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
            max_tokens=1500
        )

        return synthesis

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
        """Get orchestrator status and metrics"""
        uptime = datetime.now() - self.start_time if self.start_time else 0

        return {
            "session_id": self.session_id,
            "is_running": self.is_running,
            "uptime": str(uptime),
            "active_tasks": len(self.active_tasks),
            "queued_tasks": len(self.task_queue),
            "metrics": self.metrics,
            "configuration": {
                "orchestrator_model": self.config.orchestrator_llm_model,
                "task_model": self.config.task_llm_model,
                "max_parallel_tasks": self.config.max_parallel_tasks,
                "classification_enabled": self.classification_agent is not None
            }
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