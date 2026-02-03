# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Failsafe Communication Agent

A robust multi-tier system that ensures we can always communicate with some form
of LLM, even when primary systems fail. Implements multiple fallback strategies
and degraded operation modes.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.ssot_config import (
    AgentConfigurationError,
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)

logger = logging.getLogger(__name__)


class LLMTier(Enum):
    """Different tiers of LLM communication capabilities"""

    PRIMARY = "primary"  # Full-featured local/cloud LLM
    SECONDARY = "secondary"  # Backup LLM (different model)
    BASIC = "basic"  # Simple rule-based responses
    EMERGENCY = "emergency"  # Static predefined responses


@dataclass
class LLMResponse:
    """Standardized LLM response format"""

    content: str
    tier_used: LLMTier
    model_used: str
    confidence: float
    response_time: float
    success: bool
    warnings: List[str]
    metadata: Dict[str, Any]


class LLMFailsafeAgent:
    """
    Multi-tier LLM communication system with robust fallbacks.

    This agent ensures that user requests always get some form of response,
    even when primary LLM systems are down or malfunctioning.
    """

    # Agent identifier for SSOT config lookup
    AGENT_ID = "llm_failsafe"

    def __init__(self):
        """Initialize the failsafe LLM agent with explicit LLM configuration."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.logger.info(
            "LLM Failsafe Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider, self.llm_endpoint, self.model_name
        )

        # Track system health
        self.tier_health = {
            LLMTier.PRIMARY: True,
            LLMTier.SECONDARY: True,
            LLMTier.BASIC: True,
            LLMTier.EMERGENCY: True,
        }

        # Performance tracking
        self.tier_stats = {
            tier: {"requests": 0, "failures": 0, "avg_time": 0.0} for tier in LLMTier
        }

        # Configuration - use explicit model from SSOT config
        self.primary_models = [self.model_name]
        self.secondary_models = [self.model_name]

        # Timeout settings (in seconds)
        self.timeouts = {
            LLMTier.PRIMARY: 15.0,  # Reduced from 30.0 to 15.0 seconds
            LLMTier.SECONDARY: 10.0,  # Reduced from 20.0 to 10.0 seconds
            LLMTier.BASIC: 5.0,
            LLMTier.EMERGENCY: 1.0,
        }

        # Initialize basic and emergency response systems
        self._init_basic_responses()
        self._init_emergency_responses()

    def _get_greeting_patterns(self) -> dict:
        """Get greeting and help patterns (Issue #398: extracted)."""
        return {
            r"hello|hi|hey|greetings": [
                "Hello! I'm AutoBot. How can I help you today?",
                "Hi there! What would you like me to assist you with?",
                "Greetings! I'm ready to help with your tasks.",
            ],
            r"help|assist|support": [
                (
                    "I can help with: System automation, Research, File operations, "
                    "Development.\nWhat specifically would you like help with?"
                ),
                "I'm here to assist! You can ask me to help with automation, "
                "research, coding, or system tasks.",
            ],
            r"status|health|working": [
                (
                    "I'm operational and ready to help! Primary LLM systems may be "
                    "experiencing issues, but I can still assist you."
                ),
                "System status: Basic operations functional. How can I help you today?",
            ],
        }

    def _get_task_patterns(self) -> dict:
        """Get task-related patterns (Issue #398: extracted)."""
        return {
            r"what.*time|time|date": [
                f"The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Current date and time: {time.strftime('%A, %B %d, %Y at %H:%M:%S')}",
            ],
            r"calculate|math|compute|\d+.*[\+\-\*\/].*\d+": [
                "I can help with calculations. Please provide the specific math problem you'd like me to solve.",
                "For mathematical calculations, please specify the exact computation you need.",
            ],
            r"file|directory|folder|list.*files": [
                (
                    "I can help with file operations including listing, reading, "
                    "writing, and organizing files. What specific file task do you need?"
                ),
                "File operations available: list files, read content, create files, "
                "organize directories. What would you like to do?",
            ],
            r"system|install|configure|setup": [
                (
                    "I can assist with system configuration, software installation, "
                    "and setup tasks. Please specify what you'd like to install or configure."
                ),
                "System operations available. What specific system task or installation "
                "do you need help with?",
            ],
            r".*": [
                (
                    "I understand you need assistance. Due to system limitations, I'm "
                    "operating in basic mode. Can you please rephrase your request more specifically?"
                ),
                "I'm currently in basic operation mode. Please provide a clear, "
                "specific request and I'll do my best to help.",
                "I'm here to help! Could you please be more specific about what "
                "you need assistance with?",
            ],
        }

    def _init_basic_responses(self):
        """Initialize rule-based response system (Issue #398: refactored)."""
        self.basic_patterns = {**self._get_greeting_patterns(), **self._get_task_patterns()}

    def _init_emergency_responses(self):
        """Initialize emergency static responses"""
        self.emergency_responses = {
            "default": (
                (
                    "AutoBot Emergency Mode: I'm experiencing technical difficulties "
                    "but I'm still here to help. Please try again or contact support "
                    "if the issue persists."
                )
            ),
            "greeting": (
                (
                    "Hello! AutoBot is currently in emergency mode due to system issues, "
                    "but I'm still operational for basic assistance."
                )
            ),
            "help": (
                (
                    "Emergency Help: AutoBot systems are degraded. "
                    "For immediate assistance, please:\n"
                    "1. Try rephrasing your request\n2. Check system logs\n"
                    "3. Restart the service if needed\n4. Contact technical support"
                )
            ),
            "error": (
                (
                    "An error occurred in the primary systems. AutoBot is operating "
                    "in emergency mode. Your request has been noted and I'll assist "
                    "as best I can."
                )
            ),
            "status": (
                (
                    f"AutoBot Emergency Status - {time.strftime('%Y-%m-%d %H:%M:%S')}: "
                    f"Basic functions operational, primary LLM systems unavailable."
                )
            ),
        }

    def _build_base_system_content(
        self, context: Optional[Dict[str, Any]] = None
    ) -> dict:
        """
        Build the base system content structure for LLM messages.

        Issue #281: Extracted from _create_structured_messages to reduce function
        length and improve reusability of system content generation.

        Args:
            context: Optional context information for response formatting

        Returns:
            Dict with base system content structure
        """
        return {
            "role": "system",
            "instructions": (
                "You are AutoBot, an advanced autonomous AI platform specifically designed "
                "for Linux system administration and intelligent task automation. "
                "You are NOT a Meta AI model or related to Transformers. "
                "You are an enterprise-grade automation platform with 20+ specialized "
                "AI agents, expert Linux knowledge, and multi-modal processing capabilities."
            ),
            "response_format": {
                "type": "conversational",
                "style": "professional but friendly",
                "include_sources": (
                    True if context and context.get("kb_context") else False
                ),
            },
            "identity": {
                "name": "AutoBot",
                "type": "Autonomous AI Platform",
                "specialization": "Linux System Administration and Automation",
                "not_affiliated_with": ["Meta", "Facebook", "Transformers franchise"],
            },
            "capabilities": [
                "Linux system administration expertise",
                "Multi-agent task orchestration",
                "Terminal command execution",
                "GUI automation and desktop control",
                "Knowledge base management",
                "Security-first operations",
            ],
        }

    def _add_context_info_to_system_content(
        self, system_content: dict, context: Dict[str, Any]
    ) -> None:
        """
        Add context-specific information to system content.

        Issue #281: Extracted from _create_structured_messages to reduce function
        length and separate context processing logic.

        Args:
            system_content: System content dict to modify in place
            context: Context information to add
        """
        system_content["context_info"] = {}

        if context.get("chat_id"):
            system_content["context_info"]["chat_session"] = context["chat_id"]

        if context.get("kb_documents_found", 0) > 0:
            system_content["context_info"]["knowledge_base"] = {
                "documents_found": context["kb_documents_found"],
                "has_context": True,
                "instruction": (
                    "Use the provided knowledge base context to inform your response. "
                    "Cite sources when using KB information."
                ),
            }

        if context.get("response_type"):
            system_content["context_info"]["expected_response_type"] = context[
                "response_type"
            ]

        if context.get("instructions"):
            system_content["context_info"]["special_instructions"] = context[
                "instructions"
            ]

    def _create_structured_messages(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> list:
        """
        Create structured JSON messages for better LLM understanding.

        Args:
            prompt: User input/request
            context: Optional context information

        Returns:
            List of properly structured message objects
        """
        messages = []

        # Issue #281: Use extracted helpers for system content building
        system_content = self._build_base_system_content(context)

        # Add context-specific instructions if available
        if context:
            self._add_context_info_to_system_content(system_content, context)

        messages.append(
            {"role": "system", "content": json.dumps(system_content, indent=2)}
        )

        # Add knowledge base context if available
        if context and context.get("kb_context"):
            messages.append(
                {
                    "role": "system",
                    "content": f"Knowledge Base Context:\n{context['kb_context']}",
                }
            )

        # Add user message with structured format
        user_message = {
            "role": "user",
            "content": prompt,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "request_type": "chat_completion",
        }

        messages.append(user_message)

        return messages

    async def get_response(
        self, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Get a response using the most appropriate available tier.

        Args:
            prompt: User input/request
            context: Optional context information

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        # Determine the best available tier
        available_tier = self._get_best_available_tier()

        try:
            if available_tier == LLMTier.PRIMARY:
                return await self._try_primary_llm(prompt, context, start_time)
            elif available_tier == LLMTier.SECONDARY:
                return await self._try_secondary_llm(prompt, context, start_time)
            elif available_tier == LLMTier.BASIC:
                return await self._try_basic_response(prompt, context, start_time)
            else:  # EMERGENCY
                return await self._try_emergency_response(prompt, context, start_time)

        except Exception as e:
            self.logger.error("All LLM tiers failed: %s", e)
            return self._create_emergency_response(
                prompt, start_time, f"Complete system failure: {e}"
            )

    def _get_best_available_tier(self) -> LLMTier:
        """Determine the best available LLM tier based on health status"""
        for tier in (
            LLMTier.PRIMARY,
            LLMTier.SECONDARY,
            LLMTier.BASIC,
            LLMTier.EMERGENCY,
        ):
            if self.tier_health[tier]:
                return tier

        # If somehow all tiers are marked unhealthy, force emergency mode
        self.tier_health[LLMTier.EMERGENCY] = True
        return LLMTier.EMERGENCY

    def _build_llm_response(
        self, response: str, tier: LLMTier, model: str, context: Any, start_time: float,
        confidence: float = 0.9, warnings: list = None, extra_metadata: dict = None
    ) -> LLMResponse:
        """Build LLMResponse object (Issue #398: extracted)."""
        response_time = time.time() - start_time
        self._update_tier_stats(tier, response_time, success=True)
        metadata = {"context": context}
        if extra_metadata:
            metadata.update(extra_metadata)
        return LLMResponse(
            content=response, tier_used=tier, model_used=model, confidence=confidence,
            response_time=response_time, success=True, warnings=warnings or [], metadata=metadata
        )

    async def _try_primary_llm(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Try primary LLM communication (Issue #398: refactored)."""
        self.tier_stats[LLMTier.PRIMARY]["requests"] += 1
        try:
            from src.llm_interface import LLMInterface
            llm = LLMInterface()
            for model in self.primary_models:
                try:
                    messages = self._create_structured_messages(prompt, context)
                    response_data = await asyncio.wait_for(
                        llm.chat_completion(messages, llm_type="task"),
                        timeout=self.timeouts[LLMTier.PRIMARY]
                    )
                    response = response_data.get("response", "")
                    if response and response.strip():
                        return self._build_llm_response(response, LLMTier.PRIMARY, model, context, start_time)
                except asyncio.TimeoutError:
                    self.logger.warning("Primary model %s timed out", model)
                except Exception as e:
                    self.logger.warning("Primary model %s failed: %s", model, e)
            raise Exception("All primary models failed")
        except Exception as e:
            self.logger.error("Primary LLM tier failed: %s", e)
            self._update_tier_stats(LLMTier.PRIMARY, time.time() - start_time, success=False)
            self._mark_tier_unhealthy(LLMTier.PRIMARY)
            return await self._try_secondary_llm(prompt, context, start_time)

    async def _try_secondary_llm(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Try secondary LLM communication (Issue #398: refactored)."""
        self.tier_stats[LLMTier.SECONDARY]["requests"] += 1
        try:
            from src.llm_interface import LLMInterface
            llm = LLMInterface()
            simplified_prompt = self._simplify_prompt(prompt)
            for model in self.secondary_models:
                try:
                    messages = [{"role": "user", "content": simplified_prompt}]
                    response_data = await asyncio.wait_for(
                        llm.chat_completion(messages, llm_type="task"),
                        timeout=self.timeouts[LLMTier.SECONDARY]
                    )
                    response = response_data.get("response", "")
                    if response and response.strip():
                        return self._build_llm_response(
                            response, LLMTier.SECONDARY, model, context, start_time,
                            confidence=0.7, warnings=["Using secondary LLM tier"],
                            extra_metadata={"simplified": True}
                        )
                except asyncio.TimeoutError:
                    self.logger.warning("Secondary model %s timed out", model)
                except Exception as e:
                    self.logger.warning("Secondary model %s failed: %s", model, e)
            raise Exception("All secondary models failed")

        except Exception as e:
            self.logger.error("Secondary LLM tier failed: %s", e)
            self._update_tier_stats(
                LLMTier.SECONDARY, time.time() - start_time, success=False
            )
            self._mark_tier_unhealthy(LLMTier.SECONDARY)

            # Fall back to basic
            return await self._try_basic_response(prompt, context, start_time)

    def _match_pattern_response(self, prompt: str, context: Any, start_time: float) -> Optional[LLMResponse]:
        """Match pattern and return response (Issue #398: extracted)."""
        import re
        prompt_lower = prompt.lower().strip()
        for pattern, responses in self.basic_patterns.items():
            if re.search(pattern, prompt_lower):
                selected = responses[hash(prompt) % len(responses)]
                return self._build_llm_response(
                    selected, LLMTier.BASIC, "rule_based_system", context, start_time,
                    confidence=0.5, warnings=["Using basic rule-based responses"],
                    extra_metadata={"pattern_matched": pattern}
                )
        return None

    async def _try_basic_response(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Generate rule-based response (Issue #398: refactored)."""
        self.tier_stats[LLMTier.BASIC]["requests"] += 1
        try:
            matched = self._match_pattern_response(prompt, context, start_time)
            if matched:
                return matched
            default_responses = self.basic_patterns[r".*"]
            selected = default_responses[hash(prompt) % len(default_responses)]
            return self._build_llm_response(
                selected, LLMTier.BASIC, "rule_based_system", context, start_time,
                confidence=0.3, warnings=["Using basic rule-based responses", "No specific pattern matched"],
                extra_metadata={"pattern_matched": "default"}
            )
        except Exception as e:
            self.logger.error("Basic response tier failed: %s", e)
            self._update_tier_stats(LLMTier.BASIC, time.time() - start_time, success=False)
            self._mark_tier_unhealthy(LLMTier.BASIC)
            return await self._try_emergency_response(prompt, context, start_time)

    def _get_emergency_response_type(self, prompt_lower: str) -> str:
        """Determine emergency response type (Issue #334 - extracted helper)."""
        response_patterns = {
            "greeting": ["hello", "hi", "hey", "greetings"],
            "help": ["help", "assist", "support"],
            "status": ["status", "health", "working"],
            "error": ["error", "problem", "issue"],
        }
        for resp_type, keywords in response_patterns.items():
            if any(word in prompt_lower for word in keywords):
                return resp_type
        return "default"

    async def _try_emergency_response(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Generate emergency static response"""
        self.tier_stats[LLMTier.EMERGENCY]["requests"] += 1

        try:
            prompt_lower = prompt.lower().strip()
            response_type = self._get_emergency_response_type(prompt_lower)
            response = self.emergency_responses[response_type]

            response_time = time.time() - start_time
            self._update_tier_stats(LLMTier.EMERGENCY, response_time, success=True)

            return LLMResponse(
                content=response,
                tier_used=LLMTier.EMERGENCY,
                model_used="emergency_static_responses",
                confidence=0.1,
                response_time=response_time,
                success=True,
                warnings=["System in emergency mode", "Using static responses only"],
                metadata={"emergency_mode": True, "context": context},
            )

        except Exception as e:
            self.logger.critical("Emergency response tier failed: %s", e)
            return self._create_emergency_response(
                prompt, start_time, f"Emergency tier failure: {e}"
            )

    def _create_emergency_response(
        self, prompt: str, start_time: float, error_msg: str
    ) -> LLMResponse:
        """Create absolute last resort response"""
        # Create a more user-friendly emergency response
        user_message = (
            "I'm temporarily experiencing technical difficulties. "
            "Please try your request again in a moment."
        )
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            user_message = (
                "I'm having trouble connecting to my AI models right now. "
                "Please try again in a few seconds."
            )
        elif "model" in error_msg.lower():
            user_message = (
                "My AI models are currently unavailable. I'm working to restore service. "
                "Please try again shortly."
            )

        return LLMResponse(
            content=user_message,
            tier_used=LLMTier.EMERGENCY,
            model_used="emergency_fallback",
            confidence=0.1,  # Slightly higher confidence for user-friendly message
            response_time=time.time() - start_time,
            success=True,  # Mark as success to prevent further error handling
            warnings=["All LLM tiers temporarily unavailable"],
            metadata={"fallback_reason": error_msg, "original_prompt": prompt[:100]},
        )

    def _simplify_prompt(self, prompt: str) -> str:
        """Simplify prompt for secondary LLM"""
        # Remove complex instructions and keep core request
        if len(prompt) > 200:
            # Take first sentence or first 200 chars
            first_sentence = prompt.split(".")[0]
            if len(first_sentence) < 200:
                return first_sentence.strip() + "."
            else:
                return prompt[:200].strip() + "..."
        return prompt

    def _update_tier_stats(self, tier: LLMTier, response_time: float, success: bool):
        """Update performance statistics for a tier"""
        stats = self.tier_stats[tier]

        if not success:
            stats["failures"] += 1

        # Update average response time
        if stats["requests"] > 0:
            stats["avg_time"] = (
                stats["avg_time"] * (stats["requests"] - 1) + response_time
            ) / stats["requests"]
        else:
            stats["avg_time"] = response_time

    def _mark_tier_unhealthy(self, tier: LLMTier):
        """Mark a tier as unhealthy"""
        self.tier_health[tier] = False
        self.logger.warning("Marked %s tier as unhealthy", tier.value)

        # Auto-recovery: try to restore health after some failures
        failure_rate = self.tier_stats[tier]["failures"] / max(
            self.tier_stats[tier]["requests"], 1
        )
        if failure_rate > 0.8:  # If more than 80% failures
            # Schedule health check after delay
            asyncio.create_task(self._schedule_health_check(tier, delay=60))

    async def _schedule_health_check(self, tier: LLMTier, delay: int):
        """Schedule a health check for a tier"""
        await asyncio.sleep(delay)
        # Reset health status to allow retry
        self.tier_health[tier] = True
        self.logger.info("Restored %s tier to healthy status for retry", tier.value)

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        total_requests = sum(stats["requests"] for stats in self.tier_stats.values())
        total_failures = sum(stats["failures"] for stats in self.tier_stats.values())

        return {
            "tier_health": {
                tier.value: healthy for tier, healthy in self.tier_health.items()
            },
            "tier_statistics": {
                tier.value: {
                    "requests": stats["requests"],
                    "failures": stats["failures"],
                    "failure_rate": stats["failures"] / max(stats["requests"], 1),
                    "avg_response_time": stats["avg_time"],
                }
                for tier, stats in self.tier_stats.items()
            },
            "overall_stats": {
                "total_requests": total_requests,
                "total_failures": total_failures,
                "overall_success_rate": 1 - (total_failures / max(total_requests, 1)),
                "active_tier": self._get_best_available_tier().value,
            },
        }

    async def _test_tier(self, tier: LLMTier, test_prompt: str) -> LLMResponse:
        """Test a specific tier (Issue #334 - extracted helper)."""
        tier_handlers = {
            LLMTier.PRIMARY: self._try_primary_llm,
            LLMTier.SECONDARY: self._try_secondary_llm,
            LLMTier.BASIC: self._try_basic_response,
            LLMTier.EMERGENCY: self._try_emergency_response,
        }
        handler = tier_handlers[tier]
        return await handler(test_prompt, None, time.time())

    async def health_check(self) -> Dict[LLMTier, bool]:
        """Perform health check on all tiers"""
        self.logger.info("Performing comprehensive LLM tier health check")

        test_prompt = "Hello, please respond with 'OK' to confirm you're working."

        for tier in LLMTier:
            try:
                response = await self._test_tier(tier, test_prompt)
                self.tier_health[tier] = response.success
            except Exception as e:
                self.logger.error("Health check failed for %s: %s", tier.value, e)
                self.tier_health[tier] = False

        return self.tier_health


# Global instance for easy access
llm_failsafe = LLMFailsafeAgent()


async def get_robust_llm_response(
    prompt: str, context: Optional[Dict[str, Any]] = None
) -> LLMResponse:
    """
    Convenience function to get a robust LLM response with automatic failover.

    Args:
        prompt: User input/request
        context: Optional context information

    Returns:
        LLMResponse with guaranteed content (even if degraded)
    """
    return await llm_failsafe.get_response(prompt, context)


def get_llm_system_status() -> Dict[str, Any]:
    """Get current LLM system status"""
    return llm_failsafe.get_system_status()


async def perform_llm_health_check() -> Dict[LLMTier, bool]:
    """Perform health check on all LLM tiers"""
    return await llm_failsafe.health_check()
