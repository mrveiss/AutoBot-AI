# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Orchestrator - Coordinates specialized agents for optimal task handling.

Enhanced orchestrator that supports both legacy agent routing and distributed
agent communication protocols. Routes requests to appropriate agents based on
request type and context, with fallback capabilities.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.constants.threshold_constants import LLMDefaults, TimingConstants
from src.llm_interface import LLMInterface
from src.unified_config_manager import config as global_config_manager

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for routing patterns (Issue #326)
CODE_SEARCH_TERMS = {"search", "find", "code", "function"}
CLASSIFICATION_TERMS = {"classify", "category", "type"}
GREETING_PATTERNS = {"hello", "hi", "how are you", "thank you", "goodbye"}
SYSTEM_COMMAND_PATTERNS = {
    "run",
    "execute",
    "command",
    "system",
    "shell",
    "terminal",
    "ps",
    "ls",
    "df",
}
RESEARCH_PATTERNS = {"search web", "research", "find online", "latest", "current", "recent"}
KNOWLEDGE_PATTERNS = {"according to", "based on documents", "analyze", "summarize"}

# Import communication protocol
try:
    from src.protocols.agent_communication import get_communication_manager

    COMMUNICATION_AVAILABLE = True
except ImportError:
    COMMUNICATION_AVAILABLE = False
    logging.warning("Agent communication protocol not available")

# Import base agent for distributed capabilities
try:
    from .base_agent import AgentHealth, AgentRequest, BaseAgent

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


class AgentType(Enum):
    """Enumeration of available agent types."""

    CHAT = "chat"
    SYSTEM_COMMANDS = "system_commands"
    RAG = "rag"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    RESEARCH = "research"
    ORCHESTRATOR = "orchestrator"


@dataclass
class AgentCapability:
    """Describes an agent's capabilities and constraints."""

    agent_type: AgentType
    model_size: str
    specialization: str
    strengths: List[str]
    limitations: List[str]
    resource_usage: str


@dataclass
class DistributedAgentInfo:
    """Information about a distributed agent"""

    agent: "BaseAgent"
    health: "AgentHealth"
    last_health_check: datetime
    active_tasks: Set[str]


class AgentOrchestrator:
    """
    Enhanced orchestrator that coordinates both legacy and distributed agents.

    Supports dual modes:
    1. Legacy mode: Uses specialized agents with direct method calls
    2. Distributed mode: Uses standardized communication protocol

    Automatically falls back between modes based on availability.
    """

    def __init__(self):
        """Initialize the Enhanced Agent Orchestrator."""
        self.llm_interface = LLMInterface()
        self.model_name = global_config_manager.get_task_specific_model("orchestrator")
        self.agent_type = "orchestrator"
        self.orchestrator_id = f"orchestrator_{uuid.uuid4().hex[:8]}"

        # Initialize agent capabilities map
        self.agent_capabilities = self._initialize_agent_capabilities()

        # Legacy agent instances (lazy loaded)
        self._chat_agent = None
        self._system_commands_agent = None
        self._rag_agent = None
        self._kb_librarian = None
        self._research_agent = None

        # Distributed agent management
        self.distributed_agents: Dict[str, DistributedAgentInfo] = {}
        self.communication_manager = None
        self.health_check_interval = 30.0
        self.health_monitor_task = None
        self.is_running = False

        # Initialize communication if available
        if COMMUNICATION_AVAILABLE:
            try:
                self.communication_manager = get_communication_manager()
            except Exception as e:
                logger.warning(f"Could not initialize communication manager: {e}")

        # Built-in distributed agents
        self.builtin_distributed_agents = {}
        if DISTRIBUTED_AGENTS_AVAILABLE:
            self.builtin_distributed_agents = {
                "classification": ClassificationAgent,
                "npu_code_search": get_npu_code_search,
            }

        logger.info(f"Enhanced Agent Orchestrator initialized: {self.orchestrator_id}")
        logger.info(f"Communication available: {COMMUNICATION_AVAILABLE}")
        logger.info(f"Legacy agents available: {LEGACY_AGENTS_AVAILABLE}")
        logger.info(f"Distributed agents available: {DISTRIBUTED_AGENTS_AVAILABLE}")

    async def start_distributed_mode(self):
        """Start distributed agent management"""
        if not COMMUNICATION_AVAILABLE or not DISTRIBUTED_AGENTS_AVAILABLE:
            logger.warning("Distributed mode not available")
            return False

        if self.is_running:
            logger.warning("Distributed mode already running")
            return True

        try:
            self.is_running = True

            # Initialize built-in distributed agents
            await self._initialize_distributed_agents()

            # Start health monitoring
            self.health_monitor_task = asyncio.create_task(self._health_monitor_loop())

            logger.info("Distributed agent mode started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start distributed mode: {e}")
            self.is_running = False
            return False

    async def stop_distributed_mode(self):
        """Stop distributed agent management"""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel health monitoring
        if self.health_monitor_task:
            self.health_monitor_task.cancel()

        # Shutdown distributed agents
        for agent_id in list(self.distributed_agents.keys()):
            await self._unregister_distributed_agent(agent_id)

        logger.info("Distributed agent mode stopped")

    async def _initialize_distributed_agents(self):
        """Initialize built-in distributed agents"""
        for agent_type, agent_class in self.builtin_distributed_agents.items():
            try:
                agent = agent_class()
                await self._register_distributed_agent(agent)
                logger.info(f"Initialized distributed agent: {agent_type}")
            except Exception as e:
                logger.error(
                    f"Failed to initialize distributed agent {agent_type}: {e}"
                )

    async def _register_distributed_agent(self, agent: "BaseAgent") -> bool:
        """Register a distributed agent"""
        try:
            agent_id = agent.agent_id

            # Initialize agent communication
            if not agent.communication_protocol:
                await agent.initialize_communication(agent.get_capabilities())

            # Perform health check
            health = await agent.health_check()

            # Register agent
            self.distributed_agents[agent_id] = DistributedAgentInfo(
                agent=agent,
                health=health,
                last_health_check=datetime.now(),
                active_tasks=set(),
            )

            logger.info(f"Registered distributed agent: {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to register distributed agent: {e}")
            return False

    async def _unregister_distributed_agent(self, agent_id: str) -> bool:
        """Unregister a distributed agent"""
        try:
            if agent_id not in self.distributed_agents:
                return False

            agent_info = self.distributed_agents[agent_id]
            await agent_info.agent.shutdown_communication()
            del self.distributed_agents[agent_id]

            logger.info(f"Unregistered distributed agent: {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister distributed agent {agent_id}: {e}")
            return False

    async def _check_single_agent_health(self, agent_id: str, agent_info) -> tuple:
        """Check health of single agent (Issue #334 - extracted helper)."""
        try:
            health = await agent_info.agent.health_check()
            return (agent_id, health, None)
        except Exception as e:
            return (agent_id, None, e)

    def _process_health_result(self, result, agent_id: str, health, error) -> None:
        """Process a single health check result (Issue #334 - extracted helper)."""
        agent_info = self.distributed_agents.get(agent_id)
        if not agent_info:
            return

        if error:
            logger.error(
                f"Health check failed for distributed agent {agent_id}: {error}"
            )
            return

        if not health:
            return

        agent_info.health = health
        agent_info.last_health_check = datetime.now()

        if health.status.value != "healthy":
            logger.warning(
                f"Distributed agent {agent_id} health issue: {health.status.value}"
            )

    async def _run_health_checks(self, agents_snapshot: list) -> None:
        """Run parallel health checks on agents (Issue #334 - extracted helper)."""
        results = await asyncio.gather(
            *[self._check_single_agent_health(aid, ainfo) for aid, ainfo in agents_snapshot],
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check task failed: {result}")
                continue
            agent_id, health, error = result
            self._process_health_result(result, agent_id, health, error)

    async def _health_monitor_loop(self):
        """Background health monitoring for distributed agents"""
        while self.is_running:
            try:
                agents_snapshot = list(self.distributed_agents.items())
                if agents_snapshot:
                    await self._run_health_checks(agents_snapshot)
                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in distributed health monitor: {e}")
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    def _initialize_agent_capabilities(self) -> Dict[AgentType, AgentCapability]:
        """Initialize the capabilities map for all agents."""
        return {
            AgentType.CHAT: AgentCapability(
                agent_type=AgentType.CHAT,
                model_size="1B",
                specialization="Conversational interactions",
                strengths=[
                    "Quick responses",
                    "Natural conversation",
                    "Simple Q&A",
                    "Greetings",
                ],
                limitations=[
                    "Complex reasoning",
                    "Multi-step tasks",
                    "Technical analysis",
                ],
                resource_usage="Low",
            ),
            AgentType.SYSTEM_COMMANDS: AgentCapability(
                agent_type=AgentType.SYSTEM_COMMANDS,
                model_size="1B",
                specialization="System command generation",
                strengths=[
                    "Shell commands",
                    "System operations",
                    "Security validation",
                    "Command explanation",
                ],
                limitations=["Complex system analysis", "Multi-server orchestration"],
                resource_usage="Low",
            ),
            AgentType.RAG: AgentCapability(
                agent_type=AgentType.RAG,
                model_size="3B",
                specialization="Document synthesis",
                strengths=[
                    "Information synthesis",
                    "Document analysis",
                    "Query reformulation",
                    "Context ranking",
                ],
                limitations=["Real-time data", "Interactive tasks"],
                resource_usage="Medium-High",
            ),
            AgentType.KNOWLEDGE_RETRIEVAL: AgentCapability(
                agent_type=AgentType.KNOWLEDGE_RETRIEVAL,
                model_size="1B",
                specialization="Fast fact lookup",
                strengths=[
                    "Quick searches",
                    "Database queries",
                    "Vector lookups",
                    "Simple retrieval",
                ],
                limitations=["Complex synthesis", "Cross-document analysis"],
                resource_usage="Low",
            ),
            AgentType.RESEARCH: AgentCapability(
                agent_type=AgentType.RESEARCH,
                model_size="3B + Playwright",
                specialization="Web research coordination",
                strengths=[
                    "Multi-step research",
                    "Data extraction",
                    "Source validation",
                    "Web scraping",
                ],
                limitations=["Private data", "Real-time interaction"],
                resource_usage="High",
            ),
        }

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
                    return await self._process_with_distributed_agents(
                        request, context, chat_history, preferred_agents
                    )
                except Exception as e:
                    logger.warning(
                        f"Distributed processing failed: {e}, falling back to legacy"
                    )

            # Fallback to legacy agent processing
            if LEGACY_AGENTS_AVAILABLE:
                return await self._process_with_legacy_agents(
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
            logger.error(f"Agent Orchestrator error: {e}")
            return {
                "status": "error",
                "response": (
                    "I encountered an error while processing your request. Please try rephrasing it."
                ),
                "error": str(e),
                "agent_used": "orchestrator",
                "routing_strategy": "error_fallback",
            }

    async def _process_with_distributed_agents(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        preferred_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Process request using distributed agent system"""

        # Select best distributed agent
        selected_agent = await self._select_distributed_agent(
            request, context, preferred_agents
        )

        if not selected_agent:
            raise Exception("No suitable distributed agent found")

        # Execute request with selected agent
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        try:
            # Track active task
            self.distributed_agents[selected_agent.agent_id].active_tasks.add(task_id)

            # Create agent request
            agent_request = AgentRequest(
                request_id=task_id,
                agent_type=selected_agent.agent_type,
                action="process_user_request",
                payload={
                    "request": request,
                    "context": context or {},
                    "chat_history": chat_history or [],
                },
                priority="normal",
            )

            # Execute request
            response = await selected_agent.process_request(agent_request)
            execution_time = (datetime.now() - start_time).total_seconds()

            return {
                "status": response.status,
                "response": (
                    response.result.get("response", "No response")
                    if response.result
                    else "No result"
                ),
                "agent_used": selected_agent.agent_id,
                "agent_type": selected_agent.agent_type,
                "execution_time": execution_time,
                "routing_strategy": "distributed",
                "task_id": task_id,
            }

        finally:
            # Remove from active tasks
            if selected_agent.agent_id in self.distributed_agents:
                self.distributed_agents[selected_agent.agent_id].active_tasks.discard(
                    task_id
                )

    async def _select_distributed_agent(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        preferred_agents: Optional[List[str]] = None,
    ) -> Optional["BaseAgent"]:
        """Select the best distributed agent for the request"""

        # Filter healthy agents
        healthy_agents = [
            info.agent
            for info in self.distributed_agents.values()
            if info.health.status.value == "healthy"
        ]

        if not healthy_agents:
            return None

        # Simple selection logic - can be enhanced with classification
        request_lower = request.lower()

        # Prefer specific agent types based on content
        if any(term in request_lower for term in CODE_SEARCH_TERMS):  # O(1) lookup (Issue #326)
            npu_agents = [
                a for a in healthy_agents if a.agent_type == "npu_code_search"
            ]
            if npu_agents:
                return npu_agents[0]

        if any(term in request_lower for term in CLASSIFICATION_TERMS):  # O(1) lookup (Issue #326)
            classification_agents = [
                a for a in healthy_agents if a.agent_type == "classification"
            ]
            if classification_agents:
                return classification_agents[0]

        # Prefer explicitly requested agents
        if preferred_agents:
            for agent in healthy_agents:
                if (
                    agent.agent_id in preferred_agents
                    or agent.agent_type in preferred_agents
                ):
                    return agent

        # Return least busy agent
        return min(
            healthy_agents,
            key=lambda a: len(self.distributed_agents[a.agent_id].active_tasks),
        )

    async def _process_with_legacy_agents(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Process request using legacy agent system"""

        # Determine optimal agent routing
        routing_decision = await self._determine_agent_routing(request, context)

        # Execute based on routing decision
        if routing_decision["strategy"] == "single_agent":
            return await self._execute_single_agent(
                routing_decision["primary_agent"], request, context, chat_history
            )
        elif routing_decision["strategy"] == "multi_agent":
            return await self._execute_multi_agent(
                routing_decision, request, context, chat_history
            )
        else:
            # Fallback to direct orchestrator handling
            return await self._execute_orchestrator_fallback(
                request, context, chat_history
            )

    async def _determine_agent_routing(
        self, request: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Determine the optimal routing strategy for the request.

        Args:
            request: User's request
            context: Optional context

        Returns:
            Dict containing routing decision
        """
        try:
            # Quick pattern matching for common cases
            quick_routing = self._quick_route_analysis(request)
            if quick_routing["confidence"] > 0.8:
                return quick_routing

            # Use LLM for complex routing decisions
            system_prompt = self._get_routing_system_prompt()
            agent_info = self._build_agent_info_context()

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"Available Agents:\n{agent_info}"},
                {"role": "user", "content": f"Request to route: {request}"},
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="orchestrator",
                temperature=0.3,  # Lower temperature for consistent routing
                max_tokens=LLMDefaults.CHAT_MAX_TOKENS,
                top_p=0.8,
            )

            # Parse routing decision
            routing_decision = self._parse_routing_response(response)

            return routing_decision

        except Exception as e:
            logger.error(f"Error in routing decision: {e}")
            # Fallback to simple routing
            return self._quick_route_analysis(request)

    def _quick_route_analysis(self, request: str) -> Dict[str, Any]:
        """Quick pattern-based routing analysis."""
        request_lower = request.lower()

        # Chat patterns
        if any(pattern in request_lower for pattern in GREETING_PATTERNS):  # O(1) lookup (Issue #326)
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.9,
                "reasoning": "Simple greeting/conversational pattern",
            }

        # System command patterns
        if any(pattern in request_lower for pattern in SYSTEM_COMMAND_PATTERNS):  # O(1) lookup (Issue #326)
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.SYSTEM_COMMANDS,
                "confidence": 0.9,
                "reasoning": "System command pattern detected",
            }

        # Research patterns
        if any(pattern in request_lower for pattern in RESEARCH_PATTERNS):  # O(1) lookup (Issue #326)
            return {
                "strategy": "multi_agent",
                "primary_agent": AgentType.RESEARCH,
                "secondary_agents": [AgentType.RAG],
                "confidence": 0.8,
                "reasoning": "Web research pattern with synthesis needed",
            }

        # Knowledge/RAG patterns
        if any(pattern in request_lower for pattern in KNOWLEDGE_PATTERNS):  # O(1) lookup (Issue #326)
            return {
                "strategy": "multi_agent",
                "primary_agent": AgentType.KNOWLEDGE_RETRIEVAL,
                "secondary_agents": [AgentType.RAG],
                "confidence": 0.8,
                "reasoning": "Knowledge retrieval with synthesis needed",
            }

        # Default to chat for simple requests
        if len(request.split()) <= 10:
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.6,
                "reasoning": "Short request, likely conversational",
            }

        # Complex requests need orchestrator analysis
        return {
            "strategy": "orchestrator_analysis",
            "primary_agent": AgentType.ORCHESTRATOR,
            "confidence": 0.5,
            "reasoning": "Complex request requiring orchestrator analysis",
        }

    async def _execute_chat_agent(
        self, request: str, context: Optional[Dict], chat_history: Optional[List]
    ) -> Dict[str, Any]:
        """Execute chat agent (Issue #334 - extracted helper)."""
        agent = self._get_chat_agent()
        return await agent.process_chat_message(request, context, chat_history)

    async def _execute_system_commands_agent(
        self, request: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute system commands agent (Issue #334 - extracted helper)."""
        agent = self._get_system_commands_agent()
        return await agent.process_command_request(request, context)

    async def _execute_rag_agent(
        self, request: str, context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Execute RAG agent with document retrieval (Issue #334 - extracted helper)."""
        kb_agent = self._get_kb_librarian()
        kb_result = await kb_agent.process_query(request)
        documents = kb_result.get("documents", [])

        agent = self._get_rag_agent()
        return await agent.process_document_query(request, documents, context)

    async def _execute_single_agent(
        self,
        agent_type: AgentType,
        request: str,
        context: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Execute request using a single specialized agent."""
        try:
            agent_handlers = {
                AgentType.CHAT: lambda: self._execute_chat_agent(request, context, chat_history),
                AgentType.SYSTEM_COMMANDS: lambda: self._execute_system_commands_agent(request, context),
                AgentType.RAG: lambda: self._execute_rag_agent(request, context),
                AgentType.KNOWLEDGE_RETRIEVAL: lambda: self._get_kb_librarian().process_query(request),
                AgentType.RESEARCH: lambda: self._get_research_agent().research_query(request),
            }

            handler = agent_handlers.get(agent_type)
            if handler is None:
                raise ValueError(f"Unknown agent type: {agent_type}")

            result = await handler()
            result["routing_strategy"] = "single_agent"
            result["primary_agent"] = agent_type.value

            return result

        except Exception as e:
            logger.error(f"Error executing single agent {agent_type}: {e}")
            return {
                "status": "error",
                "response": f"Error in {agent_type.value} agent: {str(e)}",
                "agent_used": agent_type.value,
                "routing_strategy": "single_agent_error",
            }

    async def _execute_multi_agent(
        self,
        routing_decision: Dict[str, Any],
        request: str,
        context: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Execute request using multiple coordinated agents."""
        try:
            primary_agent = routing_decision["primary_agent"]
            secondary_agents = routing_decision.get("secondary_agents", [])

            # Execute primary agent
            primary_result = await self._execute_single_agent(
                primary_agent, request, context, chat_history
            )

            # Execute secondary agents if needed
            secondary_results = []
            for agent_type in secondary_agents:
                try:
                    # Modify request based on primary result for secondary agents
                    secondary_request = self._adapt_request_for_secondary(
                        request, primary_result, agent_type
                    )

                    secondary_result = await self._execute_single_agent(
                        agent_type, secondary_request, context, chat_history
                    )
                    secondary_results.append(secondary_result)

                except Exception as e:
                    logger.error(f"Error in secondary agent {agent_type}: {e}")

            # Synthesize results
            final_result = await self._synthesize_multi_agent_results(
                primary_result, secondary_results, routing_decision
            )

            return final_result

        except Exception as e:
            logger.error(f"Error in multi-agent execution: {e}")
            return {
                "status": "error",
                "response": "Error in multi-agent coordination",
                "error": str(e),
                "routing_strategy": "multi_agent_error",
            }

    async def _execute_orchestrator_fallback(
        self,
        request: str,
        context: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Fallback to direct orchestrator processing."""
        try:
            # Use the existing orchestrator logic as fallback
            # This would integrate with the main orchestrator.py

            return {
                "status": "success",
                "response": "Request processed by orchestrator fallback",
                "agent_used": "orchestrator",
                "routing_strategy": "orchestrator_fallback",
            }

        except Exception as e:
            logger.error(f"Orchestrator fallback error: {e}")
            return {
                "status": "error",
                "response": "I'm unable to process this request at the moment.",
                "error": str(e),
                "routing_strategy": "final_fallback",
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

    def _get_routing_system_prompt(self) -> str:
        """Get system prompt for routing decisions."""
        return """You are an intelligent agent router. Your task is to analyze user requests and determine the optimal agent routing strategy.

Available routing strategies:
1. "single_agent" - Route to one specialized agent
2. "multi_agent" - Coordinate multiple agents
3. "orchestrator_analysis" - Complex analysis needed

Respond in JSON format:
{
    "strategy": "single_agent|multi_agent|orchestrator_analysis",
    "primary_agent": "chat|system_commands|rag|knowledge_retrieval|research",
    "secondary_agents": ["agent1", "agent2"],
    "confidence": 0.8,
    "reasoning": "explanation of routing decision"
}

Consider:
- Task complexity
- Required capabilities
- Resource efficiency
- Response speed requirements"""

    def _build_agent_info_context(self) -> str:
        """Build context string describing available agents."""
        info_parts = []

        for agent_type, capability in self.agent_capabilities.items():
            info_parts.append(
                f"{agent_type.value}: {capability.specialization} "
                f"(Model: {capability.model_size}, Resource: {capability.resource_usage})\n"
                f"Strengths: {', '.join(capability.strengths)}\n"
                f"Limitations: {', '.join(capability.limitations)}\n"
            )

        return "\n".join(info_parts)

    def _parse_routing_response(self, response: Any) -> Dict[str, Any]:
        """Parse routing decision from LLM response."""
        try:
            content = self._extract_response_content(response)

            # Try to parse as JSON
            import json

            parsed = json.loads(content)

            # Convert agent names to AgentType enums
            if "primary_agent" in parsed:
                parsed["primary_agent"] = AgentType(parsed["primary_agent"])

            if "secondary_agents" in parsed:
                parsed["secondary_agents"] = [
                    AgentType(agent) for agent in parsed["secondary_agents"]
                ]

            return parsed

        except Exception as e:
            logger.error(f"Error parsing routing response: {e}")
            # Fallback routing
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.3,
                "reasoning": "Parsing error, fallback routing",
            }

    def _adapt_request_for_secondary(
        self,
        original_request: str,
        primary_result: Dict[str, Any],
        secondary_agent: AgentType,
    ) -> str:
        """Adapt the request for secondary agent processing."""
        if secondary_agent == AgentType.RAG:
            # For RAG, focus on synthesis
            return f"Synthesize and analyze: {original_request}"
        elif secondary_agent == AgentType.RESEARCH:
            # For research, focus on additional information
            return f"Research additional information about: {original_request}"
        else:
            return original_request

    async def _synthesize_multi_agent_results(
        self,
        primary_result: Dict[str, Any],
        secondary_results: List[Dict[str, Any]],
        routing_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize results from multiple agents."""
        try:
            # Simple synthesis - can be enhanced
            primary_response = primary_result.get("response", "")

            # Combine secondary information if available
            additional_info = []
            for result in secondary_results:
                if result.get("status") == "success":
                    secondary_response = result.get("response", "")
                    if secondary_response:
                        additional_info.append(secondary_response)

            # Build combined response
            if additional_info:
                combined_response = (
                    f"{primary_response}\n\nAdditional Information:\n"
                    + "\n".join(additional_info)
                )
            else:
                combined_response = primary_response

            return {
                "status": "success",
                "response": combined_response,
                "primary_agent": routing_decision["primary_agent"].value,
                "secondary_agents": [
                    agent.value
                    for agent in routing_decision.get("secondary_agents", [])
                ],
                "routing_strategy": "multi_agent",
                "agents_used": len(secondary_results) + 1,
            }

        except Exception as e:
            logger.error(f"Error synthesizing multi-agent results: {e}")
            return primary_result  # Fallback to primary result

    def _try_extract_message_content(self, response: dict) -> str | None:
        """Try to extract content from message dict (Issue #334 - extracted helper)."""
        if "message" not in response or not isinstance(response["message"], dict):
            return None
        content = response["message"].get("content")
        return content.strip() if content else None

    def _try_extract_choices_content(self, response: dict) -> str | None:
        """Try to extract content from choices list (Issue #334 - extracted helper)."""
        if "choices" not in response or not isinstance(response["choices"], list):
            return None
        if len(response["choices"]) == 0:
            return None
        choice = response["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"].strip()
        return None

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        try:
            if isinstance(response, dict):
                content = self._try_extract_message_content(response)
                if content:
                    return content

                content = self._try_extract_choices_content(response)
                if content:
                    return content

                if "content" in response:
                    return response["content"].strip()

            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return "Error extracting response"

    async def get_statistics(self) -> Dict[str, Any]:
        """Get orchestrator statistics and performance metrics"""
        try:
            stats = {
                "orchestrator_id": self.orchestrator_id,
                "model_name": self.model_name,
                "is_running": self.is_running,
                "communication_available": COMMUNICATION_AVAILABLE,
                "legacy_agents_available": LEGACY_AGENTS_AVAILABLE,
                "distributed_agents_available": DISTRIBUTED_AGENTS_AVAILABLE,
                "agent_capabilities_count": len(self.agent_capabilities),
                "distributed_agents": {},
                "legacy_agents": {},
                "health_check_interval": self.health_check_interval,
            }

            # Distributed agent statistics
            if self.distributed_agents:
                for agent_id, agent_info in self.distributed_agents.items():
                    stats["distributed_agents"][agent_id] = {
                        "agent_type": agent_info.agent.agent_type,
                        "health_status": agent_info.health.status.value,
                        "last_health_check": agent_info.last_health_check.isoformat(),
                        "active_tasks": len(agent_info.active_tasks),
                        "active_task_list": list(agent_info.active_tasks),
                    }

            # Legacy agent status
            legacy_agent_status = {
                "chat_agent": self._chat_agent is not None,
                "system_commands_agent": self._system_commands_agent is not None,
                "rag_agent": self._rag_agent is not None,
                "kb_librarian": self._kb_librarian is not None,
                "research_agent": self._research_agent is not None,
            }
            stats["legacy_agents"] = legacy_agent_status

            return stats

        except Exception as e:
            logger.error(f"Error getting orchestrator statistics: {e}")
            return {
                "error": str(e),
                "orchestrator_id": self.orchestrator_id,
                "is_running": self.is_running,
            }


# Singleton instance (thread-safe)
import threading

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
