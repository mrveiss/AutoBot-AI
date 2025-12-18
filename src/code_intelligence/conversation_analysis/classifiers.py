# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intent and Response Classifiers

Issue #381: Extracted from conversation_flow_analyzer.py god class refactoring.
Contains classifiers for user intents and assistant responses.
"""

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .types import IntentCategory, ResponseType


class IntentClassifier:
    """Classifies user intents based on message content."""

    # Intent keyword mappings
    INTENT_KEYWORDS: Dict[IntentCategory, Set[str]] = {
        IntentCategory.INSTALLATION: {
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
            "pip install",
            "npm install",
            "docker",
        },
        IntentCategory.ARCHITECTURE: {
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
            "structure",
        },
        IntentCategory.TROUBLESHOOTING: {
            "error",
            "issue",
            "problem",
            "not working",
            "broken",
            "failed",
            "fail",
            "crash",
            "bug",
            "fix",
            "debug",
            "timeout",
            "exception",
            "traceback",
            "stack trace",
        },
        IntentCategory.API_USAGE: {
            "api",
            "endpoint",
            "request",
            "response",
            "rest",
            "http",
            "curl",
            "postman",
            "swagger",
            "openapi",
            "route",
            "method",
        },
        IntentCategory.SECURITY: {
            "security",
            "authentication",
            "authorization",
            "token",
            "jwt",
            "password",
            "secret",
            "encrypt",
            "vulnerability",
            "audit",
            "permission",
            "access",
        },
        IntentCategory.PERFORMANCE: {
            "performance",
            "slow",
            "fast",
            "optimize",
            "speed",
            "latency",
            "memory",
            "cpu",
            "bottleneck",
            "profile",
            "benchmark",
            "cache",
        },
        IntentCategory.KNOWLEDGE_BASE: {
            "knowledge",
            "document",
            "search",
            "vector",
            "embedding",
            "chromadb",
            "rag",
            "retrieval",
            "index",
            "semantic",
        },
        IntentCategory.CODE_ANALYSIS: {
            "code",
            "analyze",
            "review",
            "pattern",
            "refactor",
            "quality",
            "lint",
            "test",
            "coverage",
            "complexity",
        },
        IntentCategory.RESEARCH: {
            "research",
            "find",
            "look up",
            "search for",
            "investigate",
            "explore",
            "discover",
            "learn about",
            "web search",
        },
        IntentCategory.GREETING: {
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "greetings",
        },
        IntentCategory.FAREWELL: {
            "goodbye",
            "bye",
            "see you",
            "later",
            "exit",
            "quit",
            "done",
            "thanks bye",
            "farewell",
        },
        IntentCategory.CLARIFICATION: {
            "what do you mean",
            "explain",
            "clarify",
            "don't understand",
            "confused",
            "unclear",
            "more details",
            "elaborate",
        },
        IntentCategory.CONFIRMATION: {
            "yes",
            "no",
            "ok",
            "okay",
            "sure",
            "correct",
            "right",
            "wrong",
            "confirm",
            "cancel",
            "proceed",
        },
    }

    # Compiled patterns for performance
    _compiled_patterns: Dict[IntentCategory, List[re.Pattern]] = {}

    @classmethod
    def _ensure_patterns_compiled(cls) -> None:
        """Compile patterns if not already done."""
        if not cls._compiled_patterns:
            for intent, keywords in cls.INTENT_KEYWORDS.items():
                patterns = []
                for keyword in keywords:
                    # Create word boundary pattern
                    pattern = re.compile(
                        r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE
                    )
                    patterns.append(pattern)
                cls._compiled_patterns[intent] = patterns

    @classmethod
    def classify(cls, message: str) -> Tuple[IntentCategory, float]:
        """
        Classify the intent of a message.

        Args:
            message: The message to classify

        Returns:
            Tuple of (IntentCategory, confidence_score)
        """
        cls._ensure_patterns_compiled()

        if not message or not message.strip():
            return IntentCategory.UNKNOWN, 0.0

        message_lower = message.lower().strip()

        # Score each intent
        scores: Dict[IntentCategory, int] = defaultdict(int)
        for intent, patterns in cls._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message_lower):
                    scores[intent] += 1

        if not scores:
            return IntentCategory.GENERAL, 0.3

        # Get highest scoring intent
        best_intent = max(scores, key=lambda k: scores[k])
        max_score = scores[best_intent]

        # Calculate confidence
        total_keywords = len(cls.INTENT_KEYWORDS.get(best_intent, set()))
        confidence = min(max_score / max(total_keywords, 1), 1.0)

        return best_intent, confidence

    @classmethod
    def classify_sequence(
        cls, messages: List[str]
    ) -> List[Tuple[IntentCategory, float]]:
        """Classify a sequence of messages."""
        return [cls.classify(msg) for msg in messages]


class ResponseClassifier:
    """Classifies assistant response types."""

    RESPONSE_PATTERNS: Dict[ResponseType, List[str]] = {
        ResponseType.GREETING: [
            r"^(hello|hi|hey|greetings)",
            r"(welcome|how can i help)",
            r"good (morning|afternoon|evening)",
        ],
        ResponseType.QUESTION: [
            r"\?$",
            r"^(what|why|how|when|where|which|who|can|could|would|should)",
            r"(please (tell|explain|describe)|could you)",
        ],
        ResponseType.CLARIFICATION: [
            r"(do you mean|did you mean)",
            r"(to clarify|let me clarify)",
            r"(just to confirm|to make sure)",
        ],
        ResponseType.ERROR_MESSAGE: [
            r"(error|failed|exception|traceback)",
            r"(sorry.*(couldn't|cannot|unable))",
            r"(unfortunately|I apologize)",
        ],
        ResponseType.SUGGESTION: [
            r"(suggest|recommend|consider|try)",
            r"(you (could|might|should))",
            r"(one option|another approach)",
        ],
        ResponseType.CONFIRMATION_REQUEST: [
            r"(proceed|continue|confirm)\?",
            r"(is that (correct|right|ok))\?",
            r"(shall i|should i|do you want me to)",
        ],
        ResponseType.FAREWELL: [
            r"(goodbye|bye|see you)",
            r"(take care|have a (good|great|nice))",
            r"(feel free to return|anytime)",
        ],
        ResponseType.TOOL_CALL: [
            r"(executing|running|calling)",
            r"(using the .* tool)",
            r"(let me (search|look|check|run))",
        ],
    }

    _compiled_patterns: Dict[ResponseType, List[re.Pattern]] = {}

    @classmethod
    def _ensure_patterns_compiled(cls) -> None:
        """Compile patterns if not already done."""
        if not cls._compiled_patterns:
            for resp_type, patterns in cls.RESPONSE_PATTERNS.items():
                compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
                cls._compiled_patterns[resp_type] = compiled

    @classmethod
    def classify(cls, response: str) -> ResponseType:
        """Classify a response type."""
        cls._ensure_patterns_compiled()

        if not response or not response.strip():
            return ResponseType.INFORMATION

        for resp_type, patterns in cls._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(response):
                    return resp_type

        return ResponseType.INFORMATION
