# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestrator Coordinator

Issue #3393: Moved from agents/agent_orchestrator.py into the
agents/agent_orchestration package as part of orchestrator consolidation.

Coordinates specialized agents for optimal task handling, supporting both
legacy agent routing and distributed agent communication protocols.
"""

import logging
import uuid
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from services.llm_service import get_llm_service

from .agent_execution import AgentExecutor
from .distributed_management import DistributedAgentManager
from .routing import AgentRouter
from .types import (
    DEFAULT_AGENT_CAPABILITIES,
    DistributedAgentInfo,
)

logger = get_logger(__name__)

# Import communication protocol
try:
    from protocols.agent_communication import get_communication_manager

    COMMUNICATION_AVAILABLE = True
except ImportError:
    COMMUNICATION_AVAILABLE = False
    logging.warning("Agent communication protocol not available")

# Import specialized agents
try:
    from agents.chat_agent import get_chat_agent
    from agents.enhanced_system_commands_agent import get_enhanced_system_commands_agent
    from agents.kb_librarian_agent import get_kb_librarian
    from agents.librarian_assistant import get_librarian_assistant
    from agents.rag_agent import get_rag_agent

    LEGACY_AGENTS_AVAILABLE = True
except ImportError:
    LEGACY_AGENTS_AVAILABLE = False
    logging.warning("Some legacy agents not available")

# Import distributed agents
try:
    from agents.classification_agent import ClassificationAgent
    from agents.npu_code_search_agent import get_npu_code_search

    DISTRIBUTED_AGENTS_AVAILABLE = True
except ImportError as e:
    DISTRIBUTED_AGENTS_AVAILABLE = False
    logger.debug("Distributed agents not available: %s", e)

# Issue #60: Import specialized agents
_SPECIALIZED_AGENT_GETTERS = {}
try:
    from agents.audio_processing_agent import get_audio_processing_agent
    from agents.code_generation_agent import get_code_generation_agent
    from agents.data_analysis_agent import get_data_analysis_agent
    from agents.image_analysis_agent import get_image_analysis_agent
    from agents.sentiment_analysis_agent import get_sentiment_analysis_agent
    from agents.summarization_agent import get_summarization_agent
    from agents.translation_agent import get_translation_agent

    _SPECIALIZED_AGENT_GETTERS = {
        "data_analysis": get_data_analysis_agent,
        "code_generation": get_code_generation_agent,
        "translation": get_translation_agent,
        "summarization": get_summarization_agent,
        "sentiment_analysis": get_sentiment_analysis_agent,
        "image_analysis": get_image_analysis_agent,
        "audio_processing": get_audio_processing_agent,
    }
    SPECIALIZED_AGENTS_AVAILABLE = True
except ImportError as e:
    SPECIALIZED_AGENTS_AVAILABLE = False
    logger.debug("Some specialized agents not available: %s", e)


class DistributedAgentCoordinator:
    """
    Enhanced orchestrator that coordinates both legacy and distributed agents.

    Issue #381: Refactored to delegate to agent_orchestration package components.
    Issue #3393: Moved from agents/agent_orchestrator.py into this package.

    Supports dual modes:
    1. Legacy mode: Uses specialized agents with direct method calls
    2. Distributed mode: Uses standardized communication protocol

    Automatically falls back between modes based on availability.
    """

    # Agent identifier for SSOT config lookup
    AGENT_ID = "orchestrator"

    def _init_llm_config(self) -> None:
        """
        Initialize LLM interface and SSOT configuration.

        Issue #620.
        """
        self.llm_interface = get_llm_service()
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

    def _init_legacy_agents(self) -> None:
        """
        Initialize legacy agent instance placeholders for lazy loading.

        Issue #620.
        """
        self.agent_capabilities = DEFAULT_AGENT_CAPABILITIES.copy()
        self._chat_agent = None
        self._system_commands_agent = None
        self._rag_agent = None
        self._kb_librarian = None
        self._research_agent = None

    def _init_distributed_components(self) -> None:
        """
        Initialize distributed agent manager, router, and executor.

        Issue #620.
        """
        builtin_distributed_agents = {}
        if DISTRIBUTED_AGENTS_AVAILABLE:
            builtin_distributed_agents = {
                "classification": ClassificationAgent,
                "npu_code_search": get_npu_code_search,
            }
        self._distributed_manager = DistributedAgentManager(
            builtin_agents=builtin_distributed_agents,
            health_check_interval=30.0,
        )
        self._router = AgentRouter(
            agent_capabilities=self.agent_capabilities,
            llm_interface=self.llm_interface,
        )
        self._executor = AgentExecutor(
            distributed_manager=self._distributed_manager,
            router=self._router,
            get_chat_agent=self._get_chat_agent,
            get_system_commands_agent=self._get_system_commands_agent,
            get_rag_agent=self._get_rag_agent,
            get_kb_librarian=self._get_kb_librarian,
            get_research_agent=self._get_research_agent,
            specialized_agent_getters=_SPECIALIZED_AGENT_GETTERS,
        )

    def _init_communication(self) -> None:
        """
        Initialize communication manager if available.

        Issue #620.
        """
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

    def __init__(self):
        """Initialize the Enhanced Agent Orchestrator with explicit LLM configuration."""
        self._init_llm_config()
        self._init_legacy_agents()
        self._init_distributed_components()
        self._init_communication()

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

    async def _try_distributed_processing(
        self,
        request: str,
        context: Dict[str, Any] | None,
        chat_history: List[Dict[str, Any]] | None,
        preferred_agents: List[str] | None,
    ) -> Dict[str, Any] | None:
        """
        Attempt to process request with distributed agents.

        Issue #620.

        Args:
            request: User's request
            context: Optional context information
            chat_history: Optional chat history
            preferred_agents: Optional list of preferred agents

        Returns:
            Response dict if successful, None if should fall back to legacy
        """
        if not (self.is_running and len(self.distributed_agents) > 0):
            return None
        try:
            return await self._executor.process_with_distributed_agents(
                request, context, chat_history, preferred_agents
            )
        except Exception as e:
            logger.warning("Distributed processing failed: %s, falling back to legacy", e)
            return None

    def _build_no_agents_response(self) -> Dict[str, Any]:
        """
        Build response when no agents are available.

        Issue #620.

        Returns:
            Error response dict
        """
        return {
            "status": "error",
            "response": "No agents available for processing",
            "agent_used": "none",
            "routing_strategy": "no_agents_available",
        }

    def _build_error_response(self, error: Exception) -> Dict[str, Any]:
        """
        Build response for orchestrator errors.

        Issue #620.

        Args:
            error: The exception that occurred

        Returns:
            Error response dict
        """
        return {
            "status": "error",
            "response": ("I encountered an error while processing your request. " "Please try rephrasing it."),
            "error": str(error),
            "agent_used": "orchestrator",
            "routing_strategy": "error_fallback",
        }

    async def process_request(
        self,
        request: str,
        context: Dict[str, Any] | None = None,
        chat_history: List[Dict[str, Any]] | None = None,
        preferred_agents: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Enhanced request processing supporting both legacy and distributed agents.

        Issue #620: Refactored to use extracted helper methods.

        Args:
            request: User's request
            context: Optional context information
            chat_history: Optional chat history for context
            preferred_agents: Optional list of preferred agents to use

        Returns:
            Dict containing response and routing information
        """
        try:
            logger.info("Enhanced Agent Orchestrator processing request: %s...", request[:50])

            # Try distributed agents first if available and running
            distributed_result = await self._try_distributed_processing(
                request, context, chat_history, preferred_agents
            )
            if distributed_result is not None:
                return distributed_result

            # Fallback to legacy agent processing
            if LEGACY_AGENTS_AVAILABLE:
                return await self._executor.process_with_legacy_agents(request, context, chat_history)
            return self._build_no_agents_response()

        except Exception as e:
            logger.error("Agent Orchestrator error: %s", e)
            return self._build_error_response(e)

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
            self._research_agent = get_librarian_assistant()
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
                "error": "Failed to retrieve orchestrator statistics",
                "orchestrator_id": self.orchestrator_id,
                "is_running": self.is_running,
            }


get_distributed_agent_coordinator = lazy_singleton(DistributedAgentCoordinator)
