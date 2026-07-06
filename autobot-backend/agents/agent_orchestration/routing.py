# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Routing Module

Issue #381: Extracted from agent_orchestrator.py god class refactoring.
Contains routing decision logic, quick route analysis, and LLM-based routing.
Issue #2092: Added Q-learning RL router between pattern-match and LLM fallback.
"""

import json
import os
import time
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import LLMDefaults

from .topology import AgentTopology, InMemoryTopologyDB
from .topology_routing import TopologyAwareRouter
from .types import (
    AUDIO_PROCESSING_PATTERNS,
    CODE_GENERATION_PATTERNS,
    DATA_ANALYSIS_PATTERNS,
    GREETING_PATTERNS,
    IMAGE_ANALYSIS_PATTERNS,
    KNOWLEDGE_PATTERNS,
    RESEARCH_PATTERNS,
    SENTIMENT_PATTERNS,
    SUMMARIZATION_PATTERNS,
    SYSTEM_COMMAND_PATTERNS,
    TRANSLATION_PATTERNS,
    AgentCapabilityDescriptor,
    AgentType,
)

logger = get_logger(__name__)


class AgentRouter:
    """Handles intelligent routing decisions for agent requests."""

    def __init__(
        self,
        agent_capabilities: Dict[AgentType, AgentCapabilityDescriptor],
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
        # Issue #2209: in-memory TTL cache for learned strategies.
        # Avoids Redis GET + TaskPatternLearner instantiation per routing call.
        self._strategy_cache: Dict[str, tuple] = {}  # task_type -> (strategy, expires)
        self._strategy_cache_ttl = 60  # seconds
        # Issue #2092: Q-learning RL router (lazy-initialised on first use).
        self._rl_router = None
        self.rl_routing_enabled: bool = True
        # Issue #6821: topology-aware router (lazy-initialised on first use).
        # Gated by env var TOPOLOGY_ROUTING_ENABLED (default: False).
        self._topology_router: TopologyAwareRouter | None = None
        self.topology_routing_enabled: bool = os.environ.get("TOPOLOGY_ROUTING_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
        }

    async def _check_learned_strategy(
        self, request: str, context: Dict[str, Any] | None = None
    ) -> Dict[str, Any] | None:
        """Query TaskPatternLearner for a learned strategy (#2105).

        Checks Redis for a previously learned strategy matching the
        task type derived from context or quick-route analysis.
        """
        task_type = (context or {}).get("task_type")
        if not task_type:
            quick = self.quick_route_analysis(request)
            agent = quick.get("primary_agent")
            task_type = agent.value if hasattr(agent, "value") else str(agent)

        try:
            from agents.task_pattern_learner import (
                LEARNED_STRATEGY_CONFIDENCE,
                TaskPatternLearner,
            )

            learner = TaskPatternLearner()
            task_type = learner.normalize_task_type(task_type)

            # Issue #2209: check in-memory cache before hitting Redis.
            now = time.monotonic()
            cached = self._strategy_cache.get(task_type)
            if cached is not None:
                strategy, expires = cached
                if now < expires:
                    if strategy and strategy.confidence > LEARNED_STRATEGY_CONFIDENCE:
                        return self._build_learned_result(strategy, task_type)
                    return None

            strategy = await learner.get_learned_strategy(task_type)
            self._strategy_cache[task_type] = (strategy, now + self._strategy_cache_ttl)

            if strategy and strategy.confidence > LEARNED_STRATEGY_CONFIDENCE:
                return self._build_learned_result(strategy, task_type)
        except Exception as exc:
            logger.debug("Learned strategy lookup failed: %s", exc)
        return None

    def _build_learned_result(self, strategy, task_type: str) -> Dict[str, Any]:
        """Build routing result dict from a LearnedStrategy (#2209, #10580)."""
        logger.info(
            "Using learned strategy for %s (confidence=%.2f)",
            task_type,
            strategy.confidence,
        )
        result: Dict[str, Any] = {
            "strategy": "single_agent",
            "primary_agent": self._resolve_agent_type(strategy.best_approach),
            "confidence": strategy.confidence,
            "reasoning": (f"Learned strategy: {strategy.best_approach} " f"(samples={strategy.sample_size})"),
            "source": "learned",
        }
        # #10580: thread best_prompt_template through so prompt assembly can use it.
        if strategy.best_prompt_template:
            result["learned_prompt_template"] = strategy.best_prompt_template
        return result

    def _get_rl_router(self):
        """Lazily initialise and return the RLRouter singleton (Issue #2092)."""
        if self._rl_router is None:
            from .rl_router import RLRouter

            self._rl_router = RLRouter()
        return self._rl_router

    def _get_topology_router(self) -> TopologyAwareRouter:
        """Lazily initialise and return the TopologyAwareRouter singleton (Issue #6821)."""
        if self._topology_router is None:
            topology = AgentTopology(db=InMemoryTopologyDB())
            self._topology_router = TopologyAwareRouter(topology=topology, base_router=self)
        return self._topology_router

    def _available_agent_ids(self) -> List[str]:
        """Return all known AgentType values as string IDs."""
        return [at.value for at in self.agent_capabilities]

    async def _check_rl_routing(self, request: str) -> Dict[str, Any] | None:
        """Attempt Q-learning based routing for *request* (Issue #2092).

        Returns a routing result dict when the RL router's confidence exceeds
        the 0.6 threshold, or None to fall through to the LLM fallback.
        """
        if not self.rl_routing_enabled:
            return None
        available = self._available_agent_ids()
        if not available:
            return None
        try:
            rl = self._get_rl_router()
            agent_id, confidence, state_key = await rl.select_agent(request, available)
            if confidence <= 0.6:
                logger.debug("RL confidence %.2f too low; falling back to LLM", confidence)
                return None
            agent_type = self._resolve_agent_type(agent_id)
            logger.info(
                "RL routing: agent=%s confidence=%.2f state=%s",
                agent_id,
                confidence,
                state_key,
            )
            return {
                "strategy": "single_agent",
                "primary_agent": agent_type,
                "confidence": confidence,
                "reasoning": f"RL router selected {agent_id} (Q-learning, state={state_key})",
                "source": "rl",
                "rl_state_key": state_key,
            }
        except Exception as exc:
            logger.warning("RL routing error: %s", exc)
            return None

    async def _maybe_augment_with_topology(
        self,
        request: str,
        context: Dict[str, Any] | None,
        routing_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Optionally augment *routing_decision* with topology collaborators.

        Issue #6821: When ``TOPOLOGY_ROUTING_ENABLED`` is set and the routing
        decision indicates a complex/multi-hop/multi-step task, consults
        ``TopologyAwareRouter`` to add historically effective collaborator
        agents to the result.

        Args:
            request: The original user request.
            context: Optional routing context dict.
            routing_decision: The primary routing decision to augment.

        Returns:
            The (possibly augmented) routing decision dict.
        """
        if not self.topology_routing_enabled:
            return routing_decision

        primary_agent = routing_decision.get("primary_agent")
        if primary_agent is None:
            return routing_decision

        primary_agent_id = primary_agent.value if hasattr(primary_agent, "value") else str(primary_agent)
        topo_context = dict(context or {})
        # Derive complexity from the routing strategy when not set in context.
        if "complexity" not in topo_context:
            strategy = routing_decision.get("strategy", "single_agent")
            topo_context["complexity"] = "complex" if strategy != "single_agent" else "simple"

        try:
            topo_router = self._get_topology_router()
            topo_result = await topo_router.route_with_collaborators(
                request=request,
                context=topo_context,
                primary_agent_id=primary_agent_id,
            )
            if topo_result.get("topology_consulted"):
                routing_decision["topology_collaborators"] = topo_result.get("collaborators", [])
                routing_decision["topology_pattern"] = topo_result.get("pattern")
                logger.info(
                    "Topology augmentation: primary=%s collaborators=%s",
                    primary_agent_id,
                    routing_decision["topology_collaborators"],
                )
        except Exception as exc:
            logger.warning("Topology augmentation failed: %s", exc)

        return routing_decision

    def _resolve_agent_type(self, approach: str) -> AgentType:
        """Map a learned approach string to an AgentType enum (#2105)."""
        try:
            return AgentType(approach)
        except ValueError:
            approach_lower = approach.lower()
            for agent_type in AgentType:
                if agent_type.value in approach_lower:
                    return agent_type
            return AgentType.CHAT

    async def determine_routing(
        self,
        request: str,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Determine the optimal routing strategy for the request.

        Issue #10545: after the base decision is computed, apply a bounded,
        explainable preference bias from captured human feedback so the agent
        shifts away from behaviors this tenant keeps rejecting. The base
        decision is unchanged when no qualifying signal exists.

        Args:
            request: User's request
            context: Optional context (may carry ``user_id`` / ``org_id`` /
                ``task_class`` for tenant-scoped preference lookup).

        Returns:
            Dict containing routing decision.
        """
        decision = await self._determine_routing_base(request, context)
        return await self._apply_preference_bias(decision, context)

    async def _determine_routing_base(
        self,
        request: str,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Compute the base routing decision (pre preference bias, #10545)."""
        try:
            # Quick pattern matching for common cases
            quick_routing = self.quick_route_analysis(request)
            if quick_routing["confidence"] >= 0.8:
                return quick_routing

            # Check learned strategies before LLM fallback (#2105)
            learned = await self._check_learned_strategy(request, context)
            if learned:
                return learned

            # Q-learning RL router: sits between pattern-match and LLM (#2092)
            rl_result = await self._check_rl_routing(request)
            if rl_result:
                return rl_result

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

            # Issue #6821: augment with topology collaborators when enabled.
            routing_decision = await self._maybe_augment_with_topology(request, context, routing_decision)

            return routing_decision

        except Exception as e:
            logger.error("Error in routing decision: %s", e)
            # Fallback to simple routing
            return self.quick_route_analysis(request)

    async def _apply_preference_bias(
        self,
        decision: Dict[str, Any],
        context: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        """Nudge routing away from behaviors this tenant keeps rejecting (#10545).

        Reads the tenant-scoped preference aggregator for the chosen agent. When
        humans in this org/user/task-class have repeatedly rejected or edited
        that agent's output, its confidence is reduced by the bounded bias and
        the adjustment is recorded (explainably) in the decision's ``reasoning``
        and ``preference_bias`` fields. Best-effort: any failure returns the
        base decision untouched.
        """
        primary = decision.get("primary_agent")
        if primary is None:
            return decision
        behavior = primary.value if hasattr(primary, "value") else str(primary)
        ctx = context or {}
        try:
            from services.feedback_aggregator import get_feedback_aggregator

            bias = await get_feedback_aggregator().get_bias(
                behavior,
                task_class=ctx.get("task_class", "general"),
                user_id=ctx.get("user_id"),
                org_id=ctx.get("org_id"),
            )
        except Exception as exc:  # noqa: BLE001 — never break routing on bias lookup
            logger.debug("preference bias lookup failed: %s", exc)
            return decision

        if bias is None:
            return decision

        base_conf = float(decision.get("confidence", 0.5))
        decision["confidence"] = max(0.0, base_conf + bias.bias)
        decision["preference_bias"] = bias.to_trajectory_entry()
        decision["reasoning"] = f"{decision.get('reasoning', '')} | {bias.explanation}".strip(" |")
        logger.info(
            "routing preference bias applied: agent=%s bias=%.3f (%s)",
            behavior,
            bias.bias,
            bias.explanation,
        )
        return decision

    def _check_chat_patterns(self, request_lower: str) -> Dict[str, Any] | None:
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

    def _check_system_command_patterns(self, request_lower: str) -> Dict[str, Any] | None:
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

    def _check_research_patterns(self, request_lower: str) -> Dict[str, Any] | None:
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

    def _check_knowledge_patterns(self, request_lower: str) -> Dict[str, Any] | None:
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

    def _check_specialized_agent_patterns(self, request_lower: str) -> Dict[str, Any] | None:
        """Check for specialized agent patterns (Issue #60)."""
        pattern_agent_map = [
            (DATA_ANALYSIS_PATTERNS, AgentType.DATA_ANALYSIS, "Data analysis pattern"),
            (
                CODE_GENERATION_PATTERNS,
                AgentType.CODE_GENERATION,
                "Code generation pattern",
            ),
            (TRANSLATION_PATTERNS, AgentType.TRANSLATION, "Translation pattern"),
            (SUMMARIZATION_PATTERNS, AgentType.SUMMARIZATION, "Summarization pattern"),
            (
                SENTIMENT_PATTERNS,
                AgentType.SENTIMENT_ANALYSIS,
                "Sentiment analysis pattern",
            ),
            (
                IMAGE_ANALYSIS_PATTERNS,
                AgentType.IMAGE_ANALYSIS,
                "Image analysis pattern",
            ),
            (
                AUDIO_PROCESSING_PATTERNS,
                AgentType.AUDIO_PROCESSING,
                "Audio processing pattern",
            ),
        ]
        for patterns, agent_type, reasoning in pattern_agent_map:
            if any(pattern in request_lower for pattern in patterns):
                return {
                    "strategy": "single_agent",
                    "primary_agent": agent_type,
                    "confidence": 0.85,
                    "reasoning": reasoning,
                }
        return None

    def quick_route_analysis(self, request: str) -> Dict[str, Any]:
        """Quick pattern-based routing analysis."""
        request_lower = request.lower()

        # Check patterns in priority order (O(1) lookups - Issue #326)
        for checker in [
            self._check_chat_patterns,
            self._check_system_command_patterns,
            self._check_research_patterns,
            self._check_knowledge_patterns,
            self._check_specialized_agent_patterns,
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
                parsed["secondary_agents"] = [AgentType(agent) for agent in parsed["secondary_agents"]]

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
