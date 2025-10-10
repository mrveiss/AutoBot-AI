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
from src.constants.network_constants import NetworkConstants

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

    def __init__(self):
        """Initialize the failsafe LLM agent"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

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

        # Configuration
        self.primary_models = [
            "gemma3:270m",  # Ultra lightweight - 291MB
            "llama3.2:1b-instruct-q4_K_M",  # Backup lightweight - 807MB
        ]
        self.secondary_models = ["gemma3:270m", "llama3.2:1b"]

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

    def _init_basic_responses(self):
        """Initialize rule-based response system"""
        self.basic_patterns = {
            # Greetings
            r"hello|hi|hey|greetings": [
                "Hello! I'm AutoBot. How can I help you today?",
                "Hi there! What would you like me to assist you with?",
                "Greetings! I'm ready to help with your tasks.",
            ],
            # Help requests
            r"help|assist|support": [
                "I can help you with various tasks including:\n- System automation\n- Research and information gathering\n- File operations\n- Development tasks\n\nWhat specifically would you like help with?",
                "I'm here to assist! You can ask me to help with automation, research, coding, or system tasks.",
            ],
            # Status queries
            r"status|health|working": [
                "I'm operational and ready to help! Primary LLM systems may be experiencing issues, but I can still assist you.",
                "System status: Basic operations functional. How can I help you today?",
            ],
            # Simple questions
            r"what.*time|time|date": [
                f"The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Current date and time: {time.strftime('%A, %B %d, %Y at %H:%M:%S')}",
            ],
            # Math/calculations
            r"calculate|math|compute|\d+.*[\+\-\*\/].*\d+": [
                "I can help with calculations. Please provide the specific math problem you'd like me to solve.",
                "For mathematical calculations, please specify the exact computation you need.",
            ],
            # File operations
            r"file|directory|folder|list.*files": [
                "I can help with file operations including listing, reading, writing, and organizing files. What specific file task do you need?",
                "File operations available: list files, read content, create files, organize directories. What would you like to do?",
            ],
            # System operations
            r"system|install|configure|setup": [
                "I can assist with system configuration, software installation, and setup tasks. Please specify what you'd like to install or configure.",
                "System operations available. What specific system task or installation do you need help with?",
            ],
            # Default fallback
            r".*": [
                "I understand you need assistance. Due to system limitations, I'm operating in basic mode. Can you please rephrase your request more specifically?",
                "I'm currently in basic operation mode. Please provide a clear, specific request and I'll do my best to help.",
                "I'm here to help! Could you please be more specific about what you need assistance with?",
            ],
        }

    def _init_emergency_responses(self):
        """Initialize emergency static responses"""
        self.emergency_responses = {
            "default": "AutoBot Emergency Mode: I'm experiencing technical difficulties but I'm still here to help. Please try again or contact support if the issue persists.",
            "greeting": "Hello! AutoBot is currently in emergency mode due to system issues, but I'm still operational for basic assistance.",
            "help": "Emergency Help: AutoBot systems are degraded. For immediate assistance, please:\n1. Try rephrasing your request\n2. Check system logs\n3. Restart the service if needed\n4. Contact technical support",
            "error": "An error occurred in the primary systems. AutoBot is operating in emergency mode. Your request has been noted and I'll assist as best I can.",
            "status": f"AutoBot Emergency Status - {time.strftime('%Y-%m-%d %H:%M:%S')}: Basic functions operational, primary LLM systems unavailable.",
        }

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

        # Add system message with structured instructions
        system_content = {
            "role": "system",
            "instructions": "You are AutoBot, an advanced autonomous AI platform specifically designed for Linux system administration and intelligent task automation. You are NOT a Meta AI model or related to Transformers. You are an enterprise-grade automation platform with 20+ specialized AI agents, expert Linux knowledge, and multi-modal processing capabilities.",
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

        # Add context-specific instructions if available
        if context:
            system_content["context_info"] = {}

            if context.get("chat_id"):
                system_content["context_info"]["chat_session"] = context["chat_id"]

            if context.get("kb_documents_found", 0) > 0:
                system_content["context_info"]["knowledge_base"] = {
                    "documents_found": context["kb_documents_found"],
                    "has_context": True,
                    "instruction": "Use the provided knowledge base context to inform your response. Cite sources when using KB information.",
                }

            if context.get("response_type"):
                system_content["context_info"]["expected_response_type"] = context[
                    "response_type"
                ]

            if context.get("instructions"):
                system_content["context_info"]["special_instructions"] = context[
                    "instructions"
                ]

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
            self.logger.error(f"All LLM tiers failed: {e}")
            return self._create_emergency_response(
                prompt, start_time, f"Complete system failure: {e}"
            )

    def _get_best_available_tier(self) -> LLMTier:
        """Determine the best available LLM tier based on health status"""
        for tier in [
            LLMTier.PRIMARY,
            LLMTier.SECONDARY,
            LLMTier.BASIC,
            LLMTier.EMERGENCY,
        ]:
            if self.tier_health[tier]:
                return tier

        # If somehow all tiers are marked unhealthy, force emergency mode
        self.tier_health[LLMTier.EMERGENCY] = True
        return LLMTier.EMERGENCY

    async def _try_primary_llm(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Try primary LLM communication"""
        self.tier_stats[LLMTier.PRIMARY]["requests"] += 1

        try:
            # Import here to avoid circular imports
            from src.llm_interface import LLMInterface

            llm = LLMInterface()

            # Try each primary model
            for model in self.primary_models:
                try:
                    # Create structured JSON messages with enhanced context
                    messages = self._create_structured_messages(prompt, context)
                    response_task = llm.chat_completion(messages, llm_type="task")
                    response_data = await asyncio.wait_for(
                        response_task, timeout=self.timeouts[LLMTier.PRIMARY]
                    )
                    response = response_data.get("response", "")

                    if response and len(response.strip()) > 0:
                        response_time = time.time() - start_time
                        self._update_tier_stats(
                            LLMTier.PRIMARY, response_time, success=True
                        )

                        return LLMResponse(
                            content=response,
                            tier_used=LLMTier.PRIMARY,
                            model_used=model,
                            confidence=0.9,
                            response_time=response_time,
                            success=True,
                            warnings=[],
                            metadata={"context": context},
                        )

                except asyncio.TimeoutError:
                    self.logger.warning(f"Primary model {model} timed out")
                    continue
                except Exception as e:
                    self.logger.warning(f"Primary model {model} failed: {e}")
                    continue

            # All primary models failed
            raise Exception("All primary models failed")

        except Exception as e:
            self.logger.error(f"Primary LLM tier failed: {e}")
            self._update_tier_stats(
                LLMTier.PRIMARY, time.time() - start_time, success=False
            )
            self._mark_tier_unhealthy(LLMTier.PRIMARY)

            # Fall back to secondary
            return await self._try_secondary_llm(prompt, context, start_time)

    async def _try_secondary_llm(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Try secondary LLM communication"""
        self.tier_stats[LLMTier.SECONDARY]["requests"] += 1

        try:
            from src.llm_interface import LLMInterface

            llm = LLMInterface()

            # Try secondary models with simpler prompts
            simplified_prompt = self._simplify_prompt(prompt)

            for model in self.secondary_models:
                try:
                    messages = [{"role": "user", "content": simplified_prompt}]
                    response_task = llm.chat_completion(messages, llm_type="task")
                    response_data = await asyncio.wait_for(
                        response_task, timeout=self.timeouts[LLMTier.SECONDARY]
                    )
                    response = response_data.get("response", "")

                    if response and len(response.strip()) > 0:
                        response_time = time.time() - start_time
                        self._update_tier_stats(
                            LLMTier.SECONDARY, response_time, success=True
                        )

                        return LLMResponse(
                            content=response,
                            tier_used=LLMTier.SECONDARY,
                            model_used=model,
                            confidence=0.7,
                            response_time=response_time,
                            success=True,
                            warnings=["Using secondary LLM tier"],
                            metadata={"context": context, "simplified": True},
                        )

                except asyncio.TimeoutError:
                    self.logger.warning(f"Secondary model {model} timed out")
                    continue
                except Exception as e:
                    self.logger.warning(f"Secondary model {model} failed: {e}")
                    continue

            raise Exception("All secondary models failed")

        except Exception as e:
            self.logger.error(f"Secondary LLM tier failed: {e}")
            self._update_tier_stats(
                LLMTier.SECONDARY, time.time() - start_time, success=False
            )
            self._mark_tier_unhealthy(LLMTier.SECONDARY)

            # Fall back to basic
            return await self._try_basic_response(prompt, context, start_time)

    async def _try_basic_response(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Generate rule-based response"""
        self.tier_stats[LLMTier.BASIC]["requests"] += 1

        try:
            import re

            prompt_lower = prompt.lower().strip()

            # Find matching pattern
            for pattern, responses in self.basic_patterns.items():
                if re.search(pattern, prompt_lower):
                    # Choose response based on request hash for consistency
                    response_idx = hash(prompt) % len(responses)
                    selected_response = responses[response_idx]

                    response_time = time.time() - start_time
                    self._update_tier_stats(LLMTier.BASIC, response_time, success=True)

                    return LLMResponse(
                        content=selected_response,
                        tier_used=LLMTier.BASIC,
                        model_used="rule_based_system",
                        confidence=0.5,
                        response_time=response_time,
                        success=True,
                        warnings=["Using basic rule-based responses"],
                        metadata={"pattern_matched": pattern, "context": context},
                    )

            # No pattern matched, use default
            default_responses = self.basic_patterns[r".*"]
            response_idx = hash(prompt) % len(default_responses)
            selected_response = default_responses[response_idx]

            response_time = time.time() - start_time
            self._update_tier_stats(LLMTier.BASIC, response_time, success=True)

            return LLMResponse(
                content=selected_response,
                tier_used=LLMTier.BASIC,
                model_used="rule_based_system",
                confidence=0.3,
                response_time=response_time,
                success=True,
                warnings=[
                    "Using basic rule-based responses",
                    "No specific pattern matched",
                ],
                metadata={"pattern_matched": "default", "context": context},
            )

        except Exception as e:
            self.logger.error(f"Basic response tier failed: {e}")
            self._update_tier_stats(
                LLMTier.BASIC, time.time() - start_time, success=False
            )
            self._mark_tier_unhealthy(LLMTier.BASIC)

            # Fall back to emergency
            return await self._try_emergency_response(prompt, context, start_time)

    async def _try_emergency_response(
        self, prompt: str, context: Optional[Dict[str, Any]], start_time: float
    ) -> LLMResponse:
        """Generate emergency static response"""
        self.tier_stats[LLMTier.EMERGENCY]["requests"] += 1

        try:
            prompt_lower = prompt.lower().strip()

            # Determine response type
            if any(
                word in prompt_lower for word in ["hello", "hi", "hey", "greetings"]
            ):
                response = self.emergency_responses["greeting"]
            elif any(word in prompt_lower for word in ["help", "assist", "support"]):
                response = self.emergency_responses["help"]
            elif any(word in prompt_lower for word in ["status", "health", "working"]):
                response = self.emergency_responses["status"]
            elif any(word in prompt_lower for word in ["error", "problem", "issue"]):
                response = self.emergency_responses["error"]
            else:
                response = self.emergency_responses["default"]

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
            # This should never happen, but just in case
            self.logger.critical(f"Emergency response tier failed: {e}")
            return self._create_emergency_response(
                prompt, start_time, f"Emergency tier failure: {e}"
            )

    def _create_emergency_response(
        self, prompt: str, start_time: float, error_msg: str
    ) -> LLMResponse:
        """Create absolute last resort response"""
        # Create a more user-friendly emergency response
        user_message = "I'm temporarily experiencing technical difficulties. Please try your request again in a moment."
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            user_message = "I'm having trouble connecting to my AI models right now. Please try again in a few seconds."
        elif "model" in error_msg.lower():
            user_message = "My AI models are currently unavailable. I'm working to restore service. Please try again shortly."

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
        self.logger.warning(f"Marked {tier.value} tier as unhealthy")

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
        self.logger.info(f"Restored {tier.value} tier to healthy status for retry")

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

    async def health_check(self) -> Dict[LLMTier, bool]:
        """Perform health check on all tiers"""
        self.logger.info("Performing comprehensive LLM tier health check")

        # Test each tier with a simple prompt
        test_prompt = "Hello, please respond with 'OK' to confirm you're working."

        for tier in LLMTier:
            try:
                if tier == LLMTier.PRIMARY:
                    response = await self._try_primary_llm(
                        test_prompt, None, time.time()
                    )
                elif tier == LLMTier.SECONDARY:
                    response = await self._try_secondary_llm(
                        test_prompt, None, time.time()
                    )
                elif tier == LLMTier.BASIC:
                    response = await self._try_basic_response(
                        test_prompt, None, time.time()
                    )
                else:  # EMERGENCY
                    response = await self._try_emergency_response(
                        test_prompt, None, time.time()
                    )

                self.tier_health[tier] = response.success

            except Exception as e:
                self.logger.error(f"Health check failed for {tier.value}: {e}")
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
