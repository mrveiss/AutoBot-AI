# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Intent Detector - User Intent Classification for Chat Workflows

This module provides intent detection capabilities for chat workflows, enabling
context-aware responses based on user's conversation goals.

Extracted from src/chat_workflow_manager.py as part of Phase 2 refactoring
(Issue #40 - Targeted Refactoring).

Key Features:
- Exit intent detection for conversation termination
- Multi-category intent classification (installation, architecture, troubleshooting, API, general)
- Context-aware intent scoring based on conversation history
- Dynamic context prompt selection based on detected intent

Functions:
- detect_exit_intent(): Detect if user wants to end conversation
- detect_user_intent(): Classify user's intent from message
- select_context_prompt(): Select appropriate system prompt based on intent

Related Issue: #40 - Chat/Conversation Targeted Refactoring
Created: 2025-01-14 (Phase 2)
"""

import logging
from typing import Dict, List, Optional

from prompt_manager import get_prompt

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Exit intent detection keywords
EXIT_KEYWORDS = {
    "goodbye",
    "bye",
    "exit",
    "quit",
    "end chat",
    "stop",
    "that's all",
    "thanks goodbye",
    "bye bye",
    "see you",
    "farewell",
    "good bye",
    "later",
    "end conversation",
    "no more",
    "i'm done",
    "im done",
    "close chat",
}

# Intent keyword mappings
INTENT_KEYWORDS = {
    "installation": {
        "install",
        "setup",
        "configure",
        "deployment",
        "deploy",
        "first time",
        "getting started",
        "how to start",
        "run autobot",
        "start autobot",
        "vm setup",
        "distributed setup",
    },
    "architecture": {
        "architecture",
        "design",
        "why",
        "how does",
        "how is",
        "vm",
        "virtual machine",
        "distributed",
        "infrastructure",
        "service",
        "component",
        "system design",
        "how many",
    },
    "troubleshooting": {
        "error",
        "issue",
        "problem",
        "not working",
        "broken",
        "failed",
        "fail",
        "crash",
        "timeout",
        "can't",
        "cannot",
        "stuck",
        "help",
        "fix",
        "debug",
        "troubleshoot",
    },
    "api": {
        "api",
        "endpoint",
        "request",
        "response",
        "integration",
        "curl",
        "http",
        "rest",
        "websocket",
        "stream",
        "documentation",
        "docs",
        "how to call",
        "how to use",
    },
}

# Context prompt mapping for each intent
CONTEXT_PROMPT_MAP = {
    "installation": "chat.installation_help",
    "architecture": "chat.architecture_explanation",
    "troubleshooting": "chat.troubleshooting",
    "api": "chat.api_documentation",
}

# =============================================================================
# Private Helper Functions
# =============================================================================


def _get_non_exit_context_phrases() -> set:
    """
    Return phrases that indicate the user is asking ABOUT exit concepts, not trying to exit.

    These are compound terms where exit/quit/etc are part of technical concepts
    rather than conversation termination requests.

    Returns:
        set: Phrases that should not trigger exit intent detection.

    Issue #620.
    """
    return {
        "exit code",
        "exit status",
        "exit signal",
        "exit value",
        "exit point",
        "quit command",
        "quit signal",
        "stop signal",
        "stop command",
        "about exit",
        "about the exit",
        "the exit",
        "what exit",
        "which exit",
        "bye command",
        "the bye",
        "how to quit",
        "explain how",
        "tell me about",
    }


def _check_non_exit_context(message_lower: str) -> bool:
    """
    Check if message contains non-exit context phrases.

    Args:
        message_lower: Lowercase message to check.

    Returns:
        bool: True if message contains a non-exit context phrase.

    Issue #620.
    """
    non_exit_context_phrases = _get_non_exit_context_phrases()
    for phrase in non_exit_context_phrases:
        if phrase in message_lower:
            logger.debug("Exit keyword found but in non-exit context: '%s'", phrase)
            return True
    return False


def _combine_prompts(base_prompt: str, context_prompt: str, intent: str) -> str:
    """
    Combine base prompt with context-specific prompt.

    Args:
        base_prompt: Base system prompt to use as foundation.
        context_prompt: Context-specific prompt to append.
        intent: The detected intent for logging.

    Returns:
        str: Combined prompt with base + context-specific instructions.

    Issue #620.
    """
    return f"""{base_prompt}

---

## CONTEXT-SPECIFIC GUIDANCE

{context_prompt}

---

**Remember**: Follow both the general conversation management rules above AND the context-specific guidance for this {intent} conversation."""


# =============================================================================
# Public Functions
# =============================================================================


def detect_exit_intent(message: str) -> bool:
    """
    Detect if user explicitly wants to end the conversation.

    This function checks for explicit exit phrases and keywords that indicate
    the user wants to terminate the chat session. It's designed to avoid
    false positives by checking for question marks (which typically indicate
    the user is asking about exiting, not actually exiting).

    Args:
        message: User's message to analyze

    Returns:
        bool: True if user explicitly wants to exit, False otherwise

    Example:
        >>> detect_exit_intent("goodbye")
        True
        >>> detect_exit_intent("How do I exit the application?")
        False
        >>> detect_exit_intent("thanks, bye!")
        True
    """
    message_lower = message.lower().strip()

    # Check for exact exit phrases
    if message_lower in EXIT_KEYWORDS:
        logger.info("Exit intent detected: '%s'", message_lower)
        return True

    # Check for exit keywords in message (with word boundaries)
    words = message_lower.split()

    # If message contains any non-exit context phrase, don't trigger exit
    if _check_non_exit_context(message_lower):
        return False

    for exit_word in EXIT_KEYWORDS:
        if exit_word in words:
            # Only consider it an exit if it's not part of a question
            if "?" not in message:
                logger.info("Exit intent detected from keyword: '%s'", exit_word)
                return True

    return False


def _calculate_intent_scores(message_lower: str) -> Dict[str, float]:
    """
    Calculate initial intent scores based on keyword matches.

    Args:
        message_lower: Lowercase message to analyze.

    Returns:
        Dict mapping intent names to their match scores.

    Issue #620.
    """
    return {
        intent: sum(1 for kw in keywords if kw in message_lower)
        for intent, keywords in INTENT_KEYWORDS.items()
    }


def _boost_scores_from_context(
    intent_scores: Dict[str, float],
    conversation_history: Optional[List[Dict[str, str]]],
) -> None:
    """
    Boost intent scores based on conversation context (in-place).

    Args:
        intent_scores: Dict of intent scores to modify.
        conversation_history: Previous conversation messages for context.

    Issue #620.
    """
    if not conversation_history or len(conversation_history) == 0:
        return

    last_responses = [msg.get("assistant", "") for msg in conversation_history[-2:]]
    context = " ".join(last_responses).lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in context for kw in keywords):
            intent_scores[intent] += 0.5


def detect_user_intent(
    message: str, conversation_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Detect user's intent to select appropriate context prompt.

    This function analyzes the user's message and conversation history to
    classify their intent into one of several categories. It uses keyword
    matching and contextual boosting to improve accuracy.

    Intent Categories:
    - installation: Setup, deployment, getting started questions
    - architecture: System design, component explanations
    - troubleshooting: Error resolution, debugging, fixes
    - api: API usage, endpoints, integration
    - general: General conversation (fallback)

    Args:
        message: User's message to analyze
        conversation_history: Previous conversation messages for context
            Format: [{"user": "msg1", "assistant": "resp1"}, ...]

    Returns:
        str: Detected intent ('installation', 'architecture', 'troubleshooting', 'api', 'general')

    Example:
        >>> detect_user_intent("How do I install AutoBot?")
        'installation'
        >>> detect_user_intent("What's the architecture of the system?")
        'architecture'
        >>> detect_user_intent("I'm getting a timeout error")
        'troubleshooting'
    """
    message_lower = message.lower().strip()
    intent_scores = _calculate_intent_scores(message_lower)
    _boost_scores_from_context(intent_scores, conversation_history)

    max_score = max(intent_scores.values())

    if max_score > 0:
        detected_intent = max(intent_scores, key=intent_scores.get)
        logger.debug(
            f"Intent detected: {detected_intent} (score: {max_score}) for message: {message[:50]}..."
        )
        return detected_intent

    logger.debug(
        f"No specific intent detected, using general context for: {message[:50]}..."
    )
    return "general"


def select_context_prompt(intent: str, base_prompt: str) -> str:
    """Select and combine appropriate context prompt based on detected intent.

    Loads intent-specific context prompts and combines them with the base
    system prompt to provide tailored responses based on user needs.

    Args:
        intent: Detected user intent ('installation', 'architecture', etc.)
        base_prompt: Base system prompt to use as foundation

    Returns:
        str: Combined prompt with base + context-specific instructions.
             Falls back to base_prompt if intent is 'general', not in mapping,
             or context prompt fails to load.

    Example:
        >>> base = "You are AutoBot, a helpful assistant."
        >>> enhanced = select_context_prompt("installation", base)
        >>> "installation" in enhanced.lower()
        True
    """
    # If general intent, return base prompt only
    if intent == "general" or intent not in CONTEXT_PROMPT_MAP:
        logger.debug("Using base system prompt (general context)")
        return base_prompt

    # Load context-specific prompt
    try:
        context_key = CONTEXT_PROMPT_MAP[intent]
        context_prompt = get_prompt(context_key)
        logger.info("Loaded context prompt: %s for intent: %s", context_key, intent)
        return _combine_prompts(base_prompt, context_prompt, intent)
    except Exception as e:
        logger.warning("Failed to load context prompt for intent '%s': %s", intent, e)
        logger.warning("Falling back to base system prompt")
        return base_prompt


# =============================================================================
# Module Information
# =============================================================================

__all__ = [
    "detect_exit_intent",
    "detect_user_intent",
    "select_context_prompt",
    "EXIT_KEYWORDS",
    "INTENT_KEYWORDS",
    "CONTEXT_PROMPT_MAP",
]
