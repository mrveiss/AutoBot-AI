# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Flow Analyzer for AutoBot

Analyzes conversation flow patterns specific to AutoBot's chat system.
Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #227).

Features:
- Flow extraction from conversation histories
- Intent classification using pattern matching
- Response pattern analysis
- Error recovery pattern detection
- Bottleneck identification
- Optimization suggestions

Analysis Areas:
- Common conversation paths
- Error recovery strategies
- Context management
- Response generation patterns
- Cache opportunities
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class IntentCategory(Enum):
    """Categories of user intents in AutoBot conversations."""

    INSTALLATION = "installation"
    ARCHITECTURE = "architecture"
    TROUBLESHOOTING = "troubleshooting"
    API_USAGE = "api_usage"
    SECURITY = "security"
    PERFORMANCE = "performance"
    KNOWLEDGE_BASE = "knowledge_base"
    CODE_ANALYSIS = "code_analysis"
    RESEARCH = "research"
    GENERAL = "general"
    GREETING = "greeting"
    FAREWELL = "farewell"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    UNKNOWN = "unknown"


class FlowState(Enum):
    """States in a conversation flow."""

    INITIATED = "initiated"
    CONTEXT_GATHERING = "context_gathering"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    ERROR_RECOVERY = "error_recovery"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"


class ResponseType(Enum):
    """Types of assistant responses."""

    GREETING = "greeting"
    INFORMATION = "information"
    QUESTION = "question"
    CLARIFICATION = "clarification"
    ACTION_RESULT = "action_result"
    ERROR_MESSAGE = "error_message"
    SUGGESTION = "suggestion"
    CONFIRMATION_REQUEST = "confirmation_request"
    FAREWELL = "farewell"
    TOOL_CALL = "tool_call"
    STREAMING = "streaming"


class BottleneckType(Enum):
    """Types of conversation bottlenecks."""

    SLOW_RESPONSE = "slow_response"
    REPEATED_CLARIFICATION = "repeated_clarification"
    INTENT_CONFUSION = "intent_confusion"
    ERROR_LOOP = "error_loop"
    CONTEXT_LOSS = "context_loss"
    EXCESSIVE_TURNS = "excessive_turns"
    TIMEOUT = "timeout"
    USER_FRUSTRATION = "user_frustration"


class OptimizationType(Enum):
    """Types of optimization suggestions."""

    CACHING = "caching"
    PROMPT_IMPROVEMENT = "prompt_improvement"
    CONTEXT_MANAGEMENT = "context_management"
    ERROR_HANDLING = "error_handling"
    INTENT_CLASSIFICATION = "intent_classification"
    RESPONSE_TEMPLATE = "response_template"
    WORKFLOW_SHORTCUT = "workflow_shortcut"
    PREEMPTIVE_RESPONSE = "preemptive_response"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ConversationMessage:
    """A single message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[datetime] = None
    message_id: Optional[str] = None
    intent: Optional[IntentCategory] = None
    response_type: Optional[ResponseType] = None
    latency_ms: Optional[float] = None
    token_count: Optional[int] = None
    has_tool_call: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationFlow:
    """A complete conversation flow."""

    session_id: str
    messages: List[ConversationMessage]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    final_state: FlowState = FlowState.INITIATED
    primary_intent: Optional[IntentCategory] = None
    intent_sequence: List[IntentCategory] = field(default_factory=list)
    turn_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0
    clarification_count: int = 0
    successful: bool = False
    user_satisfaction_signals: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowPattern:
    """A detected conversation flow pattern."""

    pattern_id: str
    name: str
    description: str
    intent_sequence: List[IntentCategory]
    state_sequence: List[FlowState]
    occurrence_count: int
    avg_turn_count: float
    avg_latency_ms: float
    success_rate: float
    sample_flows: List[str] = field(default_factory=list)


@dataclass
class Bottleneck:
    """A detected conversation bottleneck."""

    bottleneck_type: BottleneckType
    description: str
    severity: str  # "low", "medium", "high", "critical"
    occurrence_count: int
    affected_sessions: List[str]
    context: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class Optimization:
    """An optimization suggestion."""

    optimization_type: OptimizationType
    description: str
    impact: str  # "low", "medium", "high"
    effort: str  # "low", "medium", "high"
    affected_patterns: List[str]
    implementation_notes: str = ""
    estimated_improvement: str = ""


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    total_conversations: int
    total_messages: int
    avg_turn_count: float
    avg_latency_ms: float
    success_rate: float
    intent_distribution: Dict[IntentCategory, int]
    response_type_distribution: Dict[ResponseType, int]
    flow_patterns: List[FlowPattern]
    bottlenecks: List[Bottleneck]
    optimizations: List[Optimization]
    common_paths: List[List[IntentCategory]]
    error_recovery_patterns: List[Dict[str, Any]]
    cache_opportunities: List[Dict[str, Any]]
    health_score: float
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Intent Classification
# =============================================================================


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


# =============================================================================
# Response Classification
# =============================================================================


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


# =============================================================================
# Flow Analyzer
# =============================================================================


class ConversationFlowAnalyzer:
    """
    Analyzes conversation flow patterns specific to AutoBot's chat system.

    Provides flow extraction, pattern classification, bottleneck detection,
    and optimization suggestions.
    """

    def __init__(
        self,
        min_pattern_occurrences: int = 3,
        slow_response_threshold_ms: float = 2000.0,
        max_turns_threshold: int = 20,
        clarification_threshold: int = 3,
    ):
        """
        Initialize the analyzer.

        Args:
            min_pattern_occurrences: Minimum occurrences to report a pattern
            slow_response_threshold_ms: Threshold for slow response detection
            max_turns_threshold: Maximum turns before flagging as excessive
            clarification_threshold: Max clarifications before flagging confusion
        """
        self.min_pattern_occurrences = min_pattern_occurrences
        self.slow_response_threshold_ms = slow_response_threshold_ms
        self.max_turns_threshold = max_turns_threshold
        self.clarification_threshold = clarification_threshold

        # Analysis state
        self._flows: List[ConversationFlow] = []
        self._patterns: Dict[str, FlowPattern] = {}
        self._bottlenecks: List[Bottleneck] = []
        self._optimizations: List[Optimization] = []

    def parse_conversation(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "unknown",
    ) -> ConversationFlow:
        """
        Parse a raw conversation into a ConversationFlow.

        Args:
            messages: List of message dicts with 'role' and 'content'
            session_id: Session identifier

        Returns:
            Parsed ConversationFlow
        """
        parsed_messages: List[ConversationMessage] = []
        intent_sequence: List[IntentCategory] = []
        total_latency = 0.0
        error_count = 0
        clarification_count = 0
        user_satisfaction_signals: List[str] = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp")
            latency = msg.get("latency_ms", 0.0)

            if timestamp and isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp = None

            # Classify intent for user messages
            intent = None
            response_type = None
            if role == "user":
                intent, _ = IntentClassifier.classify(content)
                intent_sequence.append(intent)
                if intent == IntentCategory.CLARIFICATION:
                    clarification_count += 1
                # Check for satisfaction signals
                if any(
                    word in content.lower()
                    for word in ["thanks", "great", "perfect", "excellent", "helpful"]
                ):
                    user_satisfaction_signals.append(content[:100])
            elif role == "assistant":
                response_type = ResponseClassifier.classify(content)
                if response_type == ResponseType.ERROR_MESSAGE:
                    error_count += 1

            # Check for tool calls
            has_tool_call = bool(msg.get("tool_calls")) or "using the" in content.lower()

            total_latency += latency

            parsed_messages.append(
                ConversationMessage(
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    message_id=msg.get("message_id"),
                    intent=intent,
                    response_type=response_type,
                    latency_ms=latency,
                    token_count=msg.get("token_count"),
                    has_tool_call=has_tool_call,
                    metadata=msg.get("metadata", {}),
                )
            )

        # Determine final state
        final_state = self._determine_final_state(
            parsed_messages, error_count, clarification_count
        )

        # Determine primary intent
        primary_intent = self._determine_primary_intent(intent_sequence)

        # Calculate success
        successful = final_state in (FlowState.COMPLETED, FlowState.INITIATED)
        if error_count > 2 or clarification_count > self.clarification_threshold:
            successful = False

        # Get timestamps
        start_time = parsed_messages[0].timestamp if parsed_messages else None
        end_time = parsed_messages[-1].timestamp if parsed_messages else None

        return ConversationFlow(
            session_id=session_id,
            messages=parsed_messages,
            start_time=start_time,
            end_time=end_time,
            final_state=final_state,
            primary_intent=primary_intent,
            intent_sequence=intent_sequence,
            turn_count=len([m for m in parsed_messages if m.role == "user"]),
            total_latency_ms=total_latency,
            error_count=error_count,
            clarification_count=clarification_count,
            successful=successful,
            user_satisfaction_signals=user_satisfaction_signals,
        )

    def _determine_final_state(
        self,
        messages: List[ConversationMessage],
        error_count: int,
        clarification_count: int,
    ) -> FlowState:
        """Determine the final state of a conversation."""
        if not messages:
            return FlowState.ABANDONED

        last_msg = messages[-1]

        # Check for farewell
        if last_msg.intent == IntentCategory.FAREWELL or (
            last_msg.response_type == ResponseType.FAREWELL
        ):
            return FlowState.COMPLETED

        # Check for error recovery
        if error_count > 0:
            return FlowState.ERROR_RECOVERY

        # Check for excessive clarification
        if clarification_count >= self.clarification_threshold:
            return FlowState.ESCALATED

        # Check for awaiting confirmation
        if last_msg.response_type == ResponseType.CONFIRMATION_REQUEST:
            return FlowState.AWAITING_CONFIRMATION

        return FlowState.PROCESSING

    def _determine_primary_intent(
        self, intent_sequence: List[IntentCategory]
    ) -> Optional[IntentCategory]:
        """Determine the primary intent from a sequence."""
        if not intent_sequence:
            return None

        # Filter out meta-intents
        substantive_intents = [
            i
            for i in intent_sequence
            if i
            not in (
                IntentCategory.GREETING,
                IntentCategory.FAREWELL,
                IntentCategory.CONFIRMATION,
                IntentCategory.UNKNOWN,
            )
        ]

        if not substantive_intents:
            return intent_sequence[0]

        # Return most common
        counter = Counter(substantive_intents)
        return counter.most_common(1)[0][0]

    def analyze(
        self,
        conversations: Optional[List[List[Dict[str, Any]]]] = None,
        flows: Optional[List[ConversationFlow]] = None,
    ) -> AnalysisResult:
        """
        Analyze conversation flows and generate insights.

        Args:
            conversations: Raw conversation data (list of message lists)
            flows: Pre-parsed ConversationFlow objects

        Returns:
            AnalysisResult with patterns, bottlenecks, and optimizations
        """
        # Parse conversations if provided
        if conversations:
            for i, conv in enumerate(conversations):
                flow = self.parse_conversation(conv, session_id=f"session_{i}")
                self._flows.append(flow)

        if flows:
            self._flows.extend(flows)

        if not self._flows:
            return self._empty_result()

        # Compute statistics
        total_messages = sum(len(f.messages) for f in self._flows)
        avg_turns = sum(f.turn_count for f in self._flows) / len(self._flows)
        avg_latency = sum(f.total_latency_ms for f in self._flows) / len(self._flows)
        success_rate = sum(1 for f in self._flows if f.successful) / len(self._flows)

        # Compute distributions
        intent_dist = self._compute_intent_distribution()
        response_dist = self._compute_response_distribution()

        # Extract patterns
        flow_patterns = self._extract_flow_patterns()

        # Detect bottlenecks
        bottlenecks = self._detect_bottlenecks()

        # Generate optimizations
        optimizations = self._generate_optimizations(flow_patterns, bottlenecks)

        # Find common paths
        common_paths = self._find_common_paths()

        # Analyze error recovery
        error_recovery = self._analyze_error_recovery()

        # Find cache opportunities
        cache_opportunities = self._find_cache_opportunities()

        # Calculate health score
        health_score = self._calculate_health_score(
            success_rate, avg_latency, len(bottlenecks)
        )

        return AnalysisResult(
            total_conversations=len(self._flows),
            total_messages=total_messages,
            avg_turn_count=avg_turns,
            avg_latency_ms=avg_latency,
            success_rate=success_rate,
            intent_distribution=intent_dist,
            response_type_distribution=response_dist,
            flow_patterns=flow_patterns,
            bottlenecks=bottlenecks,
            optimizations=optimizations,
            common_paths=common_paths,
            error_recovery_patterns=error_recovery,
            cache_opportunities=cache_opportunities,
            health_score=health_score,
        )

    def _empty_result(self) -> AnalysisResult:
        """Return an empty analysis result."""
        return AnalysisResult(
            total_conversations=0,
            total_messages=0,
            avg_turn_count=0.0,
            avg_latency_ms=0.0,
            success_rate=0.0,
            intent_distribution={},
            response_type_distribution={},
            flow_patterns=[],
            bottlenecks=[],
            optimizations=[],
            common_paths=[],
            error_recovery_patterns=[],
            cache_opportunities=[],
            health_score=100.0,
        )

    def _compute_intent_distribution(self) -> Dict[IntentCategory, int]:
        """Compute intent distribution across all flows."""
        dist: Dict[IntentCategory, int] = defaultdict(int)
        for flow in self._flows:
            for intent in flow.intent_sequence:
                dist[intent] += 1
        return dict(dist)

    def _compute_response_distribution(self) -> Dict[ResponseType, int]:
        """Compute response type distribution."""
        dist: Dict[ResponseType, int] = defaultdict(int)
        for flow in self._flows:
            for msg in flow.messages:
                if msg.response_type:
                    dist[msg.response_type] += 1
        return dict(dist)

    def _extract_flow_patterns(self) -> List[FlowPattern]:
        """Extract common flow patterns."""
        # Group flows by intent sequence (as tuple for hashability)
        sequence_groups: Dict[Tuple[IntentCategory, ...], List[ConversationFlow]] = (
            defaultdict(list)
        )

        for flow in self._flows:
            # Use first 5 intents as pattern key
            key = tuple(flow.intent_sequence[:5])
            if key:
                sequence_groups[key].append(flow)

        patterns: List[FlowPattern] = []
        for i, (seq, flows) in enumerate(sequence_groups.items()):
            if len(flows) >= self.min_pattern_occurrences:
                avg_turns = sum(f.turn_count for f in flows) / len(flows)
                avg_latency = sum(f.total_latency_ms for f in flows) / len(flows)
                success_rate = sum(1 for f in flows if f.successful) / len(flows)

                first_intent = seq[0].value if seq else "unknown"
                patterns.append(
                    FlowPattern(
                        pattern_id=f"pattern_{i}",
                        name=f"{seq[0].value}_flow" if seq else "unknown_flow",
                        description=f"Conversation starting with {first_intent}",
                        intent_sequence=list(seq),
                        state_sequence=[f.final_state for f in flows[:3]],
                        occurrence_count=len(flows),
                        avg_turn_count=avg_turns,
                        avg_latency_ms=avg_latency,
                        success_rate=success_rate,
                        sample_flows=[f.session_id for f in flows[:5]],
                    )
                )

        return sorted(patterns, key=lambda p: p.occurrence_count, reverse=True)

    def _detect_bottlenecks(self) -> List[Bottleneck]:
        """Detect conversation bottlenecks."""
        bottlenecks: List[Bottleneck] = []

        # Slow response detection
        slow_sessions = [
            f.session_id
            for f in self._flows
            if f.total_latency_ms > self.slow_response_threshold_ms * f.turn_count
        ]
        if len(slow_sessions) >= self.min_pattern_occurrences:
            bottlenecks.append(
                Bottleneck(
                    bottleneck_type=BottleneckType.SLOW_RESPONSE,
                    description=f"High latency detected in {len(slow_sessions)} sessions",
                    severity="medium" if len(slow_sessions) < 10 else "high",
                    occurrence_count=len(slow_sessions),
                    affected_sessions=slow_sessions[:10],
                    recommendations=[
                        "Consider caching common responses",
                        "Optimize LLM prompt length",
                        "Review tool call latency",
                    ],
                )
            )

        # Repeated clarification detection
        confused_sessions = [
            f.session_id
            for f in self._flows
            if f.clarification_count >= self.clarification_threshold
        ]
        if len(confused_sessions) >= self.min_pattern_occurrences:
            bottlenecks.append(
                Bottleneck(
                    bottleneck_type=BottleneckType.REPEATED_CLARIFICATION,
                    description=f"Excessive clarifications in {len(confused_sessions)} sessions",
                    severity="high",
                    occurrence_count=len(confused_sessions),
                    affected_sessions=confused_sessions[:10],
                    recommendations=[
                        "Improve initial intent classification",
                        "Add disambiguation prompts",
                        "Enhance context gathering",
                    ],
                )
            )

        # Error loop detection
        error_sessions = [f.session_id for f in self._flows if f.error_count > 2]
        if len(error_sessions) >= self.min_pattern_occurrences:
            bottlenecks.append(
                Bottleneck(
                    bottleneck_type=BottleneckType.ERROR_LOOP,
                    description=f"Multiple errors in {len(error_sessions)} sessions",
                    severity="critical",
                    occurrence_count=len(error_sessions),
                    affected_sessions=error_sessions[:10],
                    recommendations=[
                        "Improve error handling and recovery",
                        "Add fallback responses",
                        "Implement graceful degradation",
                    ],
                )
            )

        # Excessive turns detection
        long_sessions = [
            f.session_id
            for f in self._flows
            if f.turn_count > self.max_turns_threshold
        ]
        if len(long_sessions) >= self.min_pattern_occurrences:
            bottlenecks.append(
                Bottleneck(
                    bottleneck_type=BottleneckType.EXCESSIVE_TURNS,
                    description=f"Excessive turns in {len(long_sessions)} sessions",
                    severity="medium",
                    occurrence_count=len(long_sessions),
                    affected_sessions=long_sessions[:10],
                    recommendations=[
                        "Add workflow shortcuts",
                        "Improve single-turn completions",
                        "Reduce back-and-forth",
                    ],
                )
            )

        return bottlenecks

    def _generate_optimizations(
        self, patterns: List[FlowPattern], bottlenecks: List[Bottleneck]
    ) -> List[Optimization]:
        """Generate optimization suggestions."""
        optimizations: List[Optimization] = []

        # Caching opportunity from frequent patterns
        frequent_patterns = [p for p in patterns if p.occurrence_count >= 5]
        if frequent_patterns:
            optimizations.append(
                Optimization(
                    optimization_type=OptimizationType.CACHING,
                    description="Cache responses for frequently occurring conversation patterns",
                    impact="high",
                    effort="medium",
                    affected_patterns=[p.pattern_id for p in frequent_patterns],
                    implementation_notes="Implement response caching for common intents",
                    estimated_improvement="20-30% latency reduction",
                )
            )

        # Prompt improvement from low success patterns
        low_success_patterns = [p for p in patterns if p.success_rate < 0.5]
        if low_success_patterns:
            optimizations.append(
                Optimization(
                    optimization_type=OptimizationType.PROMPT_IMPROVEMENT,
                    description="Improve prompts for low-success conversation patterns",
                    impact="high",
                    effort="medium",
                    affected_patterns=[p.pattern_id for p in low_success_patterns],
                    implementation_notes="Review and enhance system prompts",
                    estimated_improvement="30-50% success rate increase",
                )
            )

        # Error handling from bottlenecks
        error_bottlenecks = [
            b for b in bottlenecks if b.bottleneck_type == BottleneckType.ERROR_LOOP
        ]
        if error_bottlenecks:
            optimizations.append(
                Optimization(
                    optimization_type=OptimizationType.ERROR_HANDLING,
                    description="Implement robust error recovery mechanisms",
                    impact="high",
                    effort="high",
                    affected_patterns=[],
                    implementation_notes="Add error recovery flows and fallback responses",
                    estimated_improvement="50% reduction in error loops",
                )
            )

        # Intent classification improvement
        clarification_bottlenecks = [
            b
            for b in bottlenecks
            if b.bottleneck_type == BottleneckType.REPEATED_CLARIFICATION
        ]
        if clarification_bottlenecks:
            optimizations.append(
                Optimization(
                    optimization_type=OptimizationType.INTENT_CLASSIFICATION,
                    description="Enhance intent classification accuracy",
                    impact="medium",
                    effort="medium",
                    affected_patterns=[],
                    implementation_notes="Add more intent patterns and context awareness",
                    estimated_improvement="40% reduction in clarifications",
                )
            )

        return optimizations

    def _find_common_paths(self) -> List[List[IntentCategory]]:
        """Find common conversation paths."""
        path_counter: Counter = Counter()

        for flow in self._flows:
            # Use first 3 intents as path
            path = tuple(flow.intent_sequence[:3])
            if path:
                path_counter[path] += 1

        # Return paths with minimum occurrences
        return [
            list(path)
            for path, count in path_counter.most_common(10)
            if count >= self.min_pattern_occurrences
        ]

    def _analyze_error_recovery(self) -> List[Dict[str, Any]]:
        """Analyze error recovery patterns."""
        recovery_patterns: List[Dict[str, Any]] = []

        for flow in self._flows:
            if flow.error_count > 0 and flow.successful:
                # This flow had errors but recovered
                recovery_patterns.append(
                    {
                        "session_id": flow.session_id,
                        "error_count": flow.error_count,
                        "recovery_turns": flow.turn_count,
                        "final_state": flow.final_state.value,
                        "intent_sequence": [i.value for i in flow.intent_sequence],
                    }
                )

        return recovery_patterns[:20]  # Limit to 20 examples

    def _find_cache_opportunities(self) -> List[Dict[str, Any]]:
        """Find opportunities for response caching."""
        # Group by first user message content (normalized)
        first_messages: Dict[str, List[str]] = defaultdict(list)

        for flow in self._flows:
            user_messages = [m for m in flow.messages if m.role == "user"]
            if user_messages:
                # Normalize first message
                first_msg = user_messages[0].content.lower().strip()
                first_messages[first_msg].append(flow.session_id)

        # Find frequently repeated first messages
        opportunities: List[Dict[str, Any]] = []
        for msg, sessions in first_messages.items():
            if len(sessions) >= self.min_pattern_occurrences:
                opportunities.append(
                    {
                        "message_pattern": msg[:100],  # Truncate long messages
                        "occurrence_count": len(sessions),
                        "sample_sessions": sessions[:5],
                        "cache_recommendation": "Consider caching response for this query",
                    }
                )

        return sorted(opportunities, key=lambda x: x["occurrence_count"], reverse=True)[
            :10
        ]

    def _calculate_health_score(
        self, success_rate: float, avg_latency: float, bottleneck_count: int
    ) -> float:
        """Calculate overall conversation health score (0-100)."""
        # Base score from success rate (50%)
        success_score = success_rate * 50

        # Latency score (25%) - penalize high latency
        if avg_latency <= 500:
            latency_score = 25
        elif avg_latency <= 1000:
            latency_score = 20
        elif avg_latency <= 2000:
            latency_score = 15
        elif avg_latency <= 5000:
            latency_score = 10
        else:
            latency_score = 5

        # Bottleneck score (25%) - penalize bottlenecks
        bottleneck_score = max(0, 25 - bottleneck_count * 5)

        return min(100.0, success_score + latency_score + bottleneck_score)


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_conversations(
    conversations: List[List[Dict[str, Any]]],
    min_pattern_occurrences: int = 3,
    slow_response_threshold_ms: float = 2000.0,
) -> AnalysisResult:
    """
    Analyze a list of conversations for patterns and bottlenecks.

    Args:
        conversations: List of conversations (each is a list of message dicts)
        min_pattern_occurrences: Minimum occurrences for pattern detection
        slow_response_threshold_ms: Threshold for slow response detection

    Returns:
        AnalysisResult with patterns, bottlenecks, and optimizations
    """
    analyzer = ConversationFlowAnalyzer(
        min_pattern_occurrences=min_pattern_occurrences,
        slow_response_threshold_ms=slow_response_threshold_ms,
    )
    return analyzer.analyze(conversations=conversations)


def classify_intent(message: str) -> Tuple[IntentCategory, float]:
    """
    Classify the intent of a single message.

    Args:
        message: The message to classify

    Returns:
        Tuple of (IntentCategory, confidence_score)
    """
    return IntentClassifier.classify(message)


def classify_response(response: str) -> ResponseType:
    """
    Classify the type of an assistant response.

    Args:
        response: The response to classify

    Returns:
        ResponseType
    """
    return ResponseClassifier.classify(response)


def get_intent_categories() -> List[str]:
    """Get all intent category names."""
    return [category.value for category in IntentCategory]


def get_response_types() -> List[str]:
    """Get all response type names."""
    return [resp_type.value for resp_type in ResponseType]


def get_bottleneck_types() -> List[str]:
    """Get all bottleneck type names."""
    return [bt.value for bt in BottleneckType]


def get_optimization_types() -> List[str]:
    """Get all optimization type names."""
    return [ot.value for ot in OptimizationType]
