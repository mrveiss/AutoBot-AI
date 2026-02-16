# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Routing Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains routing decision logic, quick route analysis, and LLM-based routing.
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.constants.threshold_constants import LLMDefaults

from .types import (
    GREETING_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    AgentCapability,
    AgentType,
)

logger = logging.getLogger(__name__)


class AgentRouter:
    """Handles intelligent routing decisions for agent requests."""

    def __init__(
        self,
        agent_capabilities: Dict[AgentType, AgentCapability],
        llm_interface: Any,
    ):
        """
        Initialize the agent router.

        Args:
            agent_capabilities: Dict of agent type to capability info
            llm_interface: LLM interface for complex routing decisions
        """
        self.agent_capabilities = agent_capabilities
        self.llm_interface = llm_interface

    async def determine_routing(
        self,
        request: str,
        context: Optional[Dict[str, Any]] = None,
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
            quick_routing = self.quick_route_analysis(request)
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
            logger.error("Error in routing decision: %s", e)
            # Fallback to simple routing
            return self.quick_route_analysis(request)

    def _check_chat_patterns(self, request_lower: str) -> Optional[Dict[str, Any]]:
        """Check for greeting/chat patterns in request. Issue #620.

        Args:
            request_lower: Lowercase request string

        Returns:
            Routing dict if pattern matched, None otherwise
        """
        if any(pattern in request_lower for pattern in GREETING_PATTERNS):
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.9,
                "reasoning": "Simple greeting/conversational pattern",
            }
        return None

    def _check_system_command_patterns(
        self, request_lower: str
    ) -> Optional[Dict[str, Any]]:
        """Check for system command patterns in request. Issue #620.

        Args:
            request_lower: Lowercase request string

        Returns:
            Routing dict if pattern matched, None otherwise
        """
        if any(pattern in request_lower for pattern in SYSTEM_COMMAND_PATTERNS):
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.SYSTEM_COMMANDS,
                "confidence": 0.9,
                "reasoning": "System command pattern detected",
            }
        return None

    def _check_research_patterns(self, request_lower: str) -> Optional[Dict[str, Any]]:
        """Check for research patterns in request. Issue #620.

        Args:
            request_lower: Lowercase request string

        Returns:
            Routing dict if pattern matched, None otherwise
        """
        if any(pattern in request_lower for pattern in RESEARCH_PATTERNS):
            return {
                "strategy": "multi_agent",
                "primary_agent": AgentType.RESEARCH,
                "secondary_agents": [AgentType.RAG],
                "confidence": 0.8,
                "reasoning": "Web research pattern with synthesis needed",
            }
        return None

    def _check_knowledge_patterns(self, request_lower: str) -> Optional[Dict[str, Any]]:
        """Check for knowledge/RAG patterns in request. Issue #620.

        Args:
            request_lower: Lowercase request string

        Returns:
            Routing dict if pattern matched, None otherwise
        """
        if any(pattern in request_lower for pattern in KNOWLEDGE_PATTERNS):
            return {
                "strategy": "multi_agent",
                "primary_agent": AgentType.KNOWLEDGE_RETRIEVAL,
                "secondary_agents": [AgentType.RAG],
                "confidence": 0.8,
                "reasoning": "Knowledge retrieval with synthesis needed",
            }
        return None

    def _get_default_routing(self, request: str) -> Dict[str, Any]:
        """Get default routing for unmatched requests. Issue #620.

        Args:
            request: Original request string

        Returns:
            Routing dict for short or complex requests
        """
        if len(request.split()) <= 10:
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.6,
                "reasoning": "Short request, likely conversational",
            }
        return {
            "strategy": "orchestrator_analysis",
            "primary_agent": AgentType.ORCHESTRATOR,
            "confidence": 0.5,
            "reasoning": "Complex request requiring orchestrator analysis",
        }

    def quick_route_analysis(self, request: str) -> Dict[str, Any]:
        """Quick pattern-based routing analysis."""
        request_lower = request.lower()

        # Check patterns in priority order (O(1) lookups - Issue #326)
        for checker in [
            self._check_chat_patterns,
            self._check_system_command_patterns,
            self._check_research_patterns,
            self._check_knowledge_patterns,
        ]:
            result = checker(request_lower)
            if result:
                return result

        return self._get_default_routing(request)

    def _get_routing_system_prompt(self) -> str:
        """Get system prompt for routing decisions."""
        return (
            "You are an intelligent agent router. Your task is to analyze user "
            "requests and determine the optimal agent routing strategy.\n\n"
            "Available routing strategies:\n"
            '1. "single_agent" - Route to one specialized agent\n'
            '2. "multi_agent" - Coordinate multiple agents\n'
            '3. "orchestrator_analysis" - Complex analysis needed\n\n'
            "Respond in JSON format:\n"
            "{\n"
            '    "strategy": "single_agent|multi_agent|orchestrator_analysis",\n'
            '    "primary_agent": "chat|system_commands|rag|knowledge_retrieval|research",\n'
            '    "secondary_agents": ["agent1", "agent2"],\n'
            '    "confidence": 0.8,\n'
            '    "reasoning": "explanation of routing decision"\n'
            "}\n\n"
            "Consider:\n"
            "- Task complexity\n"
            "- Required capabilities\n"
            "- Resource efficiency\n"
            "- Response speed requirements"
        )

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

    def _try_extract_message_content(self, response: dict) -> Optional[str]:
        """Try to extract content from message dict (Issue #334 - extracted helper)."""
        if "message" not in response or not isinstance(response["message"], dict):
            return None
        content = response["message"].get("content")
        return content.strip() if content else None

    def _try_extract_choices_content(self, response: dict) -> Optional[str]:
        """Try to extract content from choices list (Issue #334 - extracted helper)."""
        if "choices" not in response or not isinstance(response["choices"], list):
            return None
        if len(response["choices"]) == 0:
            return None
        choice = response["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"].strip()
        return None

    def extract_response_content(self, response: Any) -> str:
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
            logger.error("Error extracting response content: %s", e)
            return "Error extracting response"

    def _parse_routing_response(self, response: Any) -> Dict[str, Any]:
        """Parse routing decision from LLM response."""
        try:
            content = self.extract_response_content(response)

            # Try to parse as JSON
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
            logger.error("Error parsing routing response: %s", e)
            # Fallback routing
            return {
                "strategy": "single_agent",
                "primary_agent": AgentType.CHAT,
                "confidence": 0.3,
                "reasoning": "Parsing error, fallback routing",
            }

    def adapt_request_for_secondary(
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
