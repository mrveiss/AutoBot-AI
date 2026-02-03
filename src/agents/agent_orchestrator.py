# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestrator - Coordinates specialized agents for optimal task handling.

Issue #381: This file has been refactored into the agent_orchestration/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/agents/agent_orchestration/
- types.py: AgentType, AgentCapability, DistributedAgentInfo, routing patterns
- distributed_management.py: Distributed agent registration and health monitoring
- routing.py: Routing decision logic and LLM-based routing
- agent_execution.py: Agent execution, result synthesis, and fallback handling

Enhanced orchestrator that supports both legacy agent routing and distributed
agent communication protocols.
"""

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

# Re-export pattern constants for backward compatibility
# Re-export all public API from the package for backward compatibility
from src.agents.agent_orchestration import (  # noqa: F401
    CLASSIFICATION_TERMS,
    CODE_SEARCH_TERMS,
    DEFAULT_AGENT_CAPABILITIES,
    GREETING_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    AgentCapability,
    AgentExecutor,
    AgentRouter,
    AgentType,
    DistributedAgentInfo,
    DistributedAgentManager,
)
from src.config.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

# Import communication protocol
try:
    from src.protocols.agent_communication import get_communication_manager

    COMMUNICATION_AVAILABLE = True
except ImportError:
    COMMUNICATION_AVAILABLE = False
    logging.warning("Agent communication protocol not available")

# Import base agent for distributed capabilities
try:
    from .base_agent import BaseAgent  # noqa: F401

    DISTRIBUTED_AGENTS_AVAILABLE = True
except ImportError:
    DISTRIBUTED_AGENTS_AVAILABLE = False

# Import specialized agents
try:
    from .chat_agent import get_chat_agent
    from .containerized_librarian_assistant import get_containerized_librarian_assistant
    from .enhanced_system_commands_agent import get_enhanced_system_commands_agent
    from .kb_librarian_agent import get_kb_librarian
    from .rag_agent import get_rag_agent

    LEGACY_AGENTS_AVAILABLE = True
except ImportError:
    LEGACY_AGENTS_AVAILABLE = False
    logging.warning("Some legacy agents not available")

# Import distributed agents
try:
    from .classification_agent import ClassificationAgent
    from .npu_code_search_agent import get_npu_code_search

    DISTRIBUTED_AGENTS_AVAILABLE = True
except ImportError as e:
    logger.debug("Distributed agents not available: %s", e)


__all__ = [
    # Types
    "AgentType",
    "AgentCapability",
    "DistributedAgentInfo",
    # Main class
    "AgentOrchestrator",
    # Singleton access
    "get_agent_orchestrator",
    # Availability flags
    "COMMUNICATION_AVAILABLE",
    "LEGACY_AGENTS_AVAILABLE",
    "DISTRIBUTED_AGENTS_AVAILABLE",
]


class AgentOrchestrator:
    """
    Enhanced orchestrator that coordinates both legacy and distributed agents.

    Issue #381: Refactored to delegate to agent_orchestration package components.

    Supports dual modes:
    1. Legacy mode: Uses specialized agents with direct method calls
    2. Distributed mode: Uses standardized communication protocol

    Automatically falls back between modes based on availability.
    """

    # Agent identifier for SSOT config lookup
    AGENT_ID = "orchestrator"

    def __init__(self):
        """Initialize the Enhanced Agent Orchestrator with explicit LLM configuration."""
        self.llm_interface = LLMInterface()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.agent_type = "orchestrator"
        self.orchestrator_id = f"orchestrator_{uuid.uuid4().hex[:8]}"

        logger.info(
            "Agent Orchestrator initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

        # Initialize agent capabilities map
        self.agent_capabilities = DEFAULT_AGENT_CAPABILITIES.copy()

        # Legacy agent instances (lazy loaded)
        self._chat_agent = None
        self._system_commands_agent = None
        self._rag_agent = None
        self._kb_librarian = None
        self._research_agent = None

        # Build distributed agents config
        builtin_distributed_agents = {}
        if DISTRIBUTED_AGENTS_AVAILABLE:
            builtin_distributed_agents = {
                "classification": ClassificationAgent,
                "npu_code_search": get_npu_code_search,
            }

        # Initialize distributed agent manager (delegates to package)
        self._distributed_manager = DistributedAgentManager(
            builtin_agents=builtin_distributed_agents,
            health_check_interval=30.0,
        )

        # Initialize router (delegates to package)
        self._router = AgentRouter(
            agent_capabilities=self.agent_capabilities,
            llm_interface=self.llm_interface,
        )

        # Initialize executor (delegates to package)
        self._executor = AgentExecutor(
            distributed_manager=self._distributed_manager,
            router=self._router,
            get_chat_agent=self._get_chat_agent,
            get_system_commands_agent=self._get_system_commands_agent,
            get_rag_agent=self._get_rag_agent,
            get_kb_librarian=self._get_kb_librarian,
            get_research_agent=self._get_research_agent,
        )

        # Initialize communication if available
        self.communication_manager = None
        if COMMUNICATION_AVAILABLE:
            try:
                self.communication_manager = get_communication_manager()
            except Exception as e:
                logger.warning("Could not initialize communication manager: %s", e)

        logger.info("Enhanced Agent Orchestrator initialized: %s", self.orchestrator_id)
        logger.info("Communication available: %s", COMMUNICATION_AVAILABLE)
        logger.info("Legacy agents available: %s", LEGACY_AGENTS_AVAILABLE)
        logger.info("Distributed agents available: %s", DISTRIBUTED_AGENTS_AVAILABLE)

    @property
    def is_running(self) -> bool:
        """Check if distributed mode is running."""
        return self._distributed_manager.is_running

    @property
    def distributed_agents(self) -> Dict[str, DistributedAgentInfo]:
        """Get distributed agents dict."""
        return self._distributed_manager.distributed_agents

    @property
    def health_check_interval(self) -> float:
        """Get health check interval."""
        return self._distributed_manager.health_check_interval

    async def start_distributed_mode(self) -> bool:
        """Start distributed agent management."""
        if not COMMUNICATION_AVAILABLE or not DISTRIBUTED_AGENTS_AVAILABLE:
            logger.warning("Distributed mode not available")
            return False
        return await self._distributed_manager.start()

    async def stop_distributed_mode(self) -> None:
        """Stop distributed agent management."""
        await self._distributed_manager.stop()

    async def process_request(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        preferred_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced request processing supporting both legacy and distributed agents.

        Args:
            request: User's request
            context: Optional context information
            chat_history: Optional chat history for context
            preferred_agents: Optional list of preferred agents to use

        Returns:
            Dict containing response and routing information
        """
        try:
            logger.info(
                f"Enhanced Agent Orchestrator processing request: {request[:50]}..."
            )

            # Try distributed agents first if available and running
            if self.is_running and len(self.distributed_agents) > 0:
                try:
                    return await self._executor.process_with_distributed_agents(
                        request, context, chat_history, preferred_agents
                    )
                except Exception as e:
                    logger.warning(
                        f"Distributed processing failed: {e}, falling back to legacy"
                    )

            # Fallback to legacy agent processing
            if LEGACY_AGENTS_AVAILABLE:
                return await self._executor.process_with_legacy_agents(
                    request, context, chat_history
                )
            else:
                return {
                    "status": "error",
                    "response": "No agents available for processing",
                    "agent_used": "none",
                    "routing_strategy": "no_agents_available",
                }

        except Exception as e:
            logger.error("Agent Orchestrator error: %s", e)
            return {
                "status": "error",
                "response": (
                    "I encountered an error while processing your request. "
                    "Please try rephrasing it."
                ),
                "error": str(e),
                "agent_used": "orchestrator",
                "routing_strategy": "error_fallback",
            }

    # Agent instance getters (lazy loading)
    def _get_chat_agent(self):
        """Lazy-load and return chat agent instance."""
        if self._chat_agent is None:
            self._chat_agent = get_chat_agent()
        return self._chat_agent

    def _get_system_commands_agent(self):
        """Lazy-load and return system commands agent instance."""
        if self._system_commands_agent is None:
            self._system_commands_agent = get_enhanced_system_commands_agent()
        return self._system_commands_agent

    def _get_rag_agent(self):
        """Lazy-load and return RAG agent instance."""
        if self._rag_agent is None:
            self._rag_agent = get_rag_agent()
        return self._rag_agent

    def _get_kb_librarian(self):
        """Lazy-load and return knowledge base librarian agent instance."""
        if self._kb_librarian is None:
            self._kb_librarian = get_kb_librarian()
        return self._kb_librarian

    def _get_research_agent(self):
        """Lazy-load and return research agent instance."""
        if self._research_agent is None:
            self._research_agent = get_containerized_librarian_assistant()
        return self._research_agent

    async def get_statistics(self) -> Dict[str, Any]:
        """Get orchestrator statistics and performance metrics."""
        try:
            stats = {
                "orchestrator_id": self.orchestrator_id,
                "model_name": self.model_name,
                "is_running": self.is_running,
                "communication_available": COMMUNICATION_AVAILABLE,
                "legacy_agents_available": LEGACY_AGENTS_AVAILABLE,
                "distributed_agents_available": DISTRIBUTED_AGENTS_AVAILABLE,
                "agent_capabilities_count": len(self.agent_capabilities),
                "distributed_agents": self._distributed_manager.get_statistics(),
                "legacy_agents": {
                    "chat_agent": self._chat_agent is not None,
                    "system_commands_agent": self._system_commands_agent is not None,
                    "rag_agent": self._rag_agent is not None,
                    "kb_librarian": self._kb_librarian is not None,
                    "research_agent": self._research_agent is not None,
                },
                "health_check_interval": self.health_check_interval,
            }

            return stats

        except Exception as e:
            logger.error("Error getting orchestrator statistics: %s", e)
            return {
                "error": str(e),
                "orchestrator_id": self.orchestrator_id,
                "is_running": self.is_running,
            }


# Singleton instance (thread-safe)
_agent_orchestrator_instance = None
_agent_orchestrator_lock = threading.Lock()


def get_agent_orchestrator() -> AgentOrchestrator:
    """Get the singleton Agent Orchestrator instance (thread-safe)."""
    global _agent_orchestrator_instance
    if _agent_orchestrator_instance is None:
        with _agent_orchestrator_lock:
            # Double-check after acquiring lock
            if _agent_orchestrator_instance is None:
                _agent_orchestrator_instance = AgentOrchestrator()
    return _agent_orchestrator_instance
