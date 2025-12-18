# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Analysis Types

Issue #381: Extracted from conversation_flow_analyzer.py god class refactoring.
Contains enums and data classes for conversation flow analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Issue #380: Module-level frozensets for satisfaction signal detection
SATISFACTION_SIGNALS = frozenset({"thanks", "great", "perfect", "excellent", "helpful"})


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
