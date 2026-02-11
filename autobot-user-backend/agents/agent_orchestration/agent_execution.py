# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Execution Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains agent execution logic, result synthesis, and fallback handling.
"""

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .types import CLASSIFICATION_TERMS, CODE_SEARCH_TERMS, AgentType

if TYPE_CHECKING:
    from agents.base_agent import AgentRequest, BaseAgent

    from .distributed_management import DistributedAgentManager
    from .routing import AgentRouter

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Handles execution of agent requests."""

    def __init__(
        self,
        distributed_manager: "DistributedAgentManager",
        router: "AgentRouter",
        get_chat_agent: Callable,
        get_system_commands_agent: Callable,
        get_rag_agent: Callable,
        get_kb_librarian: Callable,
        get_research_agent: Callable,
        specialized_agent_getters: Optional[Dict[str, Callable]] = None,
    ):
        """
        Initialize the agent executor.

        Args:
            distributed_manager: Manager for distributed agents
            router: Agent router for routing decisions
            get_*_agent: Lazy-loading getters for legacy agents
            specialized_agent_getters: Issue #60 - getters for specialized agents
        """
        self.distributed_manager = distributed_manager
        self.router = router
        self._get_chat_agent = get_chat_agent
        self._get_system_commands_agent = get_system_commands_agent
        self._get_rag_agent = get_rag_agent
        self._get_kb_librarian = get_kb_librarian
        self._get_research_agent = get_research_agent
        self._specialized_getters = specialized_agent_getters or {}

    def _create_agent_request(
        self,
        task_id: str,
        agent_type: str,
        request: str,
        context: Optional[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, Any]]],
    ) -> "AgentRequest":
        """
        Create an AgentRequest object for distributed processing.

        Args:
            task_id: Unique task identifier
            agent_type: Type of the agent
            request: User request string
            context: Optional context dictionary
            chat_history: Optional chat history list

        Returns:
            Configured AgentRequest object. Issue #620.
        """
        from agents.base_agent import AgentRequest

        return AgentRequest(
            request_id=task_id,
            agent_type=agent_type,
            action="process_user_request",
            payload={
                "request": request,
                "context": context or {},
                "chat_history": chat_history or [],
            },
            priority="normal",
        )

    def _build_distributed_response(
        self,
        response: Any,
        agent_id: str,
        agent_type: str,
        execution_time: float,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Build response dictionary from distributed agent execution.

        Args:
            response: Agent response object
            agent_id: ID of the agent used
            agent_type: Type of the agent
            execution_time: Time taken for execution
            task_id: Task identifier

        Returns:
            Formatted response dictionary. Issue #620.
        """
        return {
            "status": response.status,
            "response": (
                response.result.get("response", "No response")
                if response.result
                else "No result"
            ),
            "agent_used": agent_id,
            "agent_type": agent_type,
            "execution_time": execution_time,
            "routing_strategy": "distributed",
            "task_id": task_id,
        }

    async def process_with_distributed_agents(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        preferred_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Process request using distributed agent system. Issue #620."""
        selected_agent = await self._select_distributed_agent(
            request, context, preferred_agents
        )

        if not selected_agent:
            raise Exception("No suitable distributed agent found")

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        try:
            self.distributed_manager.add_active_task(selected_agent.agent_id, task_id)
            agent_request = self._create_agent_request(
                task_id, selected_agent.agent_type, request, context, chat_history
            )
            response = await selected_agent.process_request(agent_request)
            execution_time = (datetime.now() - start_time).total_seconds()

            return self._build_distributed_response(
                response,
                selected_agent.agent_id,
                selected_agent.agent_type,
                execution_time,
                task_id,
            )
        finally:
            self.distributed_manager.remove_active_task(
                selected_agent.agent_id, task_id
            )

    async def _select_distributed_agent(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        preferred_agents: Optional[List[str]] = None,
    ) -> Optional["BaseAgent"]:
        """Select the best distributed agent for the request."""
        # Filter healthy agents
        healthy_agents = self.distributed_manager.get_healthy_agents()

        if not healthy_agents:
            return None

        # Simple selection logic - can be enhanced with classification
        request_lower = request.lower()

        # Prefer specific agent types based on content
        if any(
            term in request_lower for term in CODE_SEARCH_TERMS
        ):  # O(1) lookup (Issue #326)
            npu_agents = [
                a for a in healthy_agents if a.agent_type == "npu_code_search"
            ]
            if npu_agents:
                return npu_agents[0]

        if any(
            term in request_lower for term in CLASSIFICATION_TERMS
        ):  # O(1) lookup (Issue #326)
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
            key=lambda a: len(
                self.distributed_manager.get_agent_info(a.agent_id).active_tasks
            ),
        )

    async def process_with_legacy_agents(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Process request using legacy agent system."""
        # Determine optimal agent routing
        routing_decision = await self.router.determine_routing(request, context)

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

    def _register_specialized_handlers(
        self, handlers: Dict, request: str, context: Optional[Dict]
    ) -> None:
        """Register specialized agent handlers (Issue #60)."""
        agent_type_map = {
            AgentType.DATA_ANALYSIS: "data_analysis",
            AgentType.CODE_GENERATION: "code_generation",
            AgentType.TRANSLATION: "translation",
            AgentType.SUMMARIZATION: "summarization",
            AgentType.SENTIMENT_ANALYSIS: "sentiment_analysis",
            AgentType.IMAGE_ANALYSIS: "image_analysis",
            AgentType.AUDIO_PROCESSING: "audio_processing",
        }
        for agent_type, getter_key in agent_type_map.items():
            getter = self._specialized_getters.get(getter_key)
            if getter:
                handlers[agent_type] = lambda g=getter: g().process_query(
                    request, context
                )

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
                AgentType.CHAT: lambda: self._execute_chat_agent(
                    request, context, chat_history
                ),
                AgentType.SYSTEM_COMMANDS: lambda: self._execute_system_commands_agent(
                    request, context
                ),
                AgentType.RAG: lambda: self._execute_rag_agent(request, context),
                AgentType.KNOWLEDGE_RETRIEVAL: lambda: self._get_kb_librarian().process_query(
                    request
                ),
                AgentType.RESEARCH: lambda: self._get_research_agent().research_query(
                    request
                ),
            }

            # Issue #60: Add specialized agent handlers
            self._register_specialized_handlers(agent_handlers, request, context)

            handler = agent_handlers.get(agent_type)
            if handler is None:
                raise ValueError(f"Unknown agent type: {agent_type}")

            result = await handler()
            result["routing_strategy"] = "single_agent"
            result["primary_agent"] = agent_type.value

            return result

        except Exception as e:
            logger.error("Error executing single agent %s: %s", agent_type, e)
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
                    secondary_request = self.router.adapt_request_for_secondary(
                        request, primary_result, agent_type
                    )

                    secondary_result = await self._execute_single_agent(
                        agent_type, secondary_request, context, chat_history
                    )
                    secondary_results.append(secondary_result)

                except Exception as e:
                    logger.error("Error in secondary agent %s: %s", agent_type, e)

            # Synthesize results
            final_result = await self._synthesize_multi_agent_results(
                primary_result, secondary_results, routing_decision
            )

            return final_result

        except Exception as e:
            logger.error("Error in multi-agent execution: %s", e)
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
            logger.error("Orchestrator fallback error: %s", e)
            return {
                "status": "error",
                "response": "I'm unable to process this request at the moment.",
                "error": str(e),
                "routing_strategy": "final_fallback",
            }

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
            logger.error("Error synthesizing multi-agent results: %s", e)
            return primary_result  # Fallback to primary result
