"""
Agent Orchestrator - Coordinates specialized agents for optimal task handling.

Routes requests to appropriate agents based on request type and context.
Uses Llama 3.2 3B model for complex routing decisions and coordination.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.config import config as global_config_manager
from src.llm_interface import LLMInterface

# Import specialized agents
from .chat_agent import get_chat_agent
from .containerized_librarian_assistant import get_containerized_librarian_assistant
from .enhanced_system_commands_agent import get_enhanced_system_commands_agent
from .kb_librarian_agent import get_kb_librarian
from .rag_agent import get_rag_agent

logger = logging.getLogger(__name__)


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


class AgentOrchestrator:
    """
    Orchestrates multiple specialized agents for optimal task distribution.

    Uses a 3B model for routing decisions and coordinates responses from
    specialized 1B and 3B agents based on task requirements.
    """

    def __init__(self):
        """Initialize the Agent Orchestrator."""
        self.llm_interface = LLMInterface()
        self.model_name = global_config_manager.get_task_specific_model("orchestrator")
        self.agent_type = "orchestrator"

        # Initialize agent capabilities map
        self.agent_capabilities = self._initialize_agent_capabilities()

        # Agent instances (lazy loaded)
        self._chat_agent = None
        self._system_commands_agent = None
        self._rag_agent = None
        self._kb_librarian = None
        self._research_agent = None

        logger.info(f"Agent Orchestrator initialized with model: {self.model_name}")

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
    ) -> Dict[str, Any]:
        """
        Process a request by routing to appropriate agent(s).

        Args:
            request: User's request
            context: Optional context information
            chat_history: Optional chat history for context

        Returns:
            Dict containing response and routing information
        """
        try:
            logger.info(f"Agent Orchestrator processing request: {request[:50]}...")

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

        except Exception as e:
            logger.error(f"Agent Orchestrator error: {e}")
            return {
                "status": "error",
                "response": "I encountered an error while processing your request. Please try rephrasing it.",
                "error": str(e),
                "agent_used": "orchestrator",
                "routing_strategy": "error_fallback",
            }

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
                max_tokens=512,
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
        if any(
            pattern in request_lower
            for pattern in ["hello", "hi", "how are you", "thank you", "goodbye"]
        ):
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.9,
                "reasoning": "Simple greeting/conversational pattern",
            }

        # System command patterns
        if any(
            pattern in request_lower
            for pattern in [
                "run",
                "execute",
                "command",
                "system",
                "shell",
                "terminal",
                "ps",
                "ls",
                "df",
            ]
        ):
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.SYSTEM_COMMANDS,
                "confidence": 0.9,
                "reasoning": "System command pattern detected",
            }

        # Research patterns
        if any(
            pattern in request_lower
            for pattern in [
                "search web",
                "research",
                "find online",
                "latest",
                "current",
                "recent",
            ]
        ):
            return {
                "strategy": "multi_agent",
                "primary_agent": AgentType.RESEARCH,
                "secondary_agents": [AgentType.RAG],
                "confidence": 0.8,
                "reasoning": "Web research pattern with synthesis needed",
            }

        # Knowledge/RAG patterns
        if any(
            pattern in request_lower
            for pattern in [
                "according to",
                "based on documents",
                "analyze",
                "summarize",
            ]
        ):
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

    async def _execute_single_agent(
        self,
        agent_type: AgentType,
        request: str,
        context: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Execute request using a single specialized agent."""
        try:
            if agent_type == AgentType.CHAT:
                agent = self._get_chat_agent()
                result = await agent.process_chat_message(
                    request, context, chat_history
                )

            elif agent_type == AgentType.SYSTEM_COMMANDS:
                agent = self._get_system_commands_agent()
                result = await agent.process_command_request(request, context)

            elif agent_type == AgentType.RAG:
                # RAG needs documents first
                kb_agent = self._get_kb_librarian()
                kb_result = await kb_agent.process_query(request)
                documents = kb_result.get("documents", [])

                agent = self._get_rag_agent()
                result = await agent.process_document_query(request, documents, context)

            elif agent_type == AgentType.KNOWLEDGE_RETRIEVAL:
                agent = self._get_kb_librarian()
                result = await agent.process_query(request)

            elif agent_type == AgentType.RESEARCH:
                agent = self._get_research_agent()
                result = await agent.research_query(request)

            else:
                raise ValueError(f"Unknown agent type: {agent_type}")

            # Add routing metadata
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
        if self._chat_agent is None:
            self._chat_agent = get_chat_agent()
        return self._chat_agent

    def _get_system_commands_agent(self):
        if self._system_commands_agent is None:
            self._system_commands_agent = get_enhanced_system_commands_agent()
        return self._system_commands_agent

    def _get_rag_agent(self):
        if self._rag_agent is None:
            self._rag_agent = get_rag_agent()
        return self._rag_agent

    def _get_kb_librarian(self):
        if self._kb_librarian is None:
            self._kb_librarian = get_kb_librarian()
        return self._kb_librarian

    def _get_research_agent(self):
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

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        try:
            if isinstance(response, dict):
                if "message" in response and isinstance(response["message"], dict):
                    content = response["message"].get("content")
                    if content:
                        return content.strip()

                if "choices" in response and isinstance(response["choices"], list):
                    if len(response["choices"]) > 0:
                        choice = response["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            return choice["message"]["content"].strip()

                if "content" in response:
                    return response["content"].strip()

            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return "Error extracting response"


# Singleton instance
_agent_orchestrator_instance = None


def get_agent_orchestrator() -> AgentOrchestrator:
    """Get the singleton Agent Orchestrator instance."""
    global _agent_orchestrator_instance
    if _agent_orchestrator_instance is None:
        _agent_orchestrator_instance = AgentOrchestrator()
    return _agent_orchestrator_instance
