# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Flow Analyzer API (Issue #227)
Analyzes AutoBot conversation patterns, intent flows, and interaction metrics
"""

import asyncio
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from auth_middleware import check_admin_permission
from backend.constants.path_constants import PATH
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversation-flow", "analytics"])

# Performance optimization: O(1) lookup for sentiment indicators (Issue #326)
SUCCESS_INDICATORS = {"thanks", "perfect", "great", "works", "solved"}
FRUSTRATION_INDICATORS = {"not working", "still", "again", "wrong", "frustrated"}


def _parse_timestamp(ts_value: Any) -> Optional[datetime]:
    """Parse timestamp from various formats (Issue #315)."""
    if not ts_value:
        return None
    try:
        if isinstance(ts_value, str):
            return datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
        return ts_value
    except (ValueError, TypeError):
        return None


def _parse_session_timestamp(created: Any) -> Optional[datetime]:
    """Parse session timestamp from various formats (Issue #315)."""
    if not created:
        return None
    try:
        if isinstance(created, str):
            return datetime.fromisoformat(created.replace("Z", "+00:00"))
        return created
    except (ValueError, TypeError):
        return None


def _is_session_in_range(session: Dict[str, Any], cutoff: datetime) -> bool:
    """Check if session is within the time range (Issue #315)."""
    created = session.get("created_at") or session.get("timestamp")
    ts = _parse_session_timestamp(created)
    if ts is None:
        return True  # Include if can't parse date
    return ts.replace(tzinfo=None) >= cutoff


# ============================================================================
# Pydantic Models
# ============================================================================


class IntentPattern(BaseModel):
    """Represents a detected user intent pattern"""

    intent_id: str
    intent_name: str
    pattern_regex: str
    occurrences: int
    success_rate: float
    avg_turns_to_resolve: float
    sample_queries: List[str] = Field(default_factory=list, max_length=5)


class ConversationFlow(BaseModel):
    """Represents a conversation flow path"""

    flow_id: str
    path: List[str]  # Sequence of intents
    frequency: int
    avg_duration_seconds: float
    completion_rate: float
    drop_off_point: Optional[str] = None


class ConversationMetrics(BaseModel):
    """Aggregated conversation metrics"""

    total_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    avg_conversation_duration_seconds: float
    user_satisfaction_estimate: float
    resolution_rate: float
    escalation_rate: float


class FlowBottleneck(BaseModel):
    """Represents a bottleneck in conversation flows"""

    bottleneck_id: str
    location: str
    description: str
    impact_score: float  # 0-100
    affected_conversations: int
    suggested_improvements: List[str]


class ConversationAnalysisResult(BaseModel):
    """Full conversation analysis result"""

    metrics: ConversationMetrics
    intent_patterns: List[IntentPattern]
    common_flows: List[ConversationFlow]
    bottlenecks: List[FlowBottleneck]
    hourly_distribution: Dict[str, int]
    analysis_period: str
    conversations_analyzed: int


# ============================================================================
# Intent Detection Patterns
# ============================================================================

# Common user intent patterns for AutoBot
INTENT_PATTERNS = [
    # Code-related intents
    (
        "code_review",
        r"\b(review|check|analyze)\b.*\b(code|file|function)\b",
        "Code Review Request",
    ),
    (
        "code_generation",
        r"\b(create|write|generate|implement)\b.*\b(code|function|class|script)\b",
        "Code Generation",
    ),
    (
        "code_fix",
        r"\b(fix|debug|resolve|solve)\b.*\b(bug|error|issue|problem)\b",
        "Bug Fix Request",
    ),
    (
        "code_explain",
        r"\b(explain|understand|what does)\b.*\b(code|function|this)\b",
        "Code Explanation",
    ),
    (
        "code_refactor",
        r"\b(refactor|improve|optimize|clean)\b.*\b(code|function)\b",
        "Code Refactoring",
    ),
    # File operations
    ("file_read", r"\b(read|show|display|open)\b.*\b(file|content)\b", "File Reading"),
    ("file_write", r"\b(write|create|save)\b.*\b(file)\b", "File Writing"),
    (
        "file_search",
        r"\b(find|search|locate|where)\b.*\b(file|function|class)\b",
        "File Search",
    ),
    # System operations
    (
        "system_status",
        r"\b(status|health|check)\b.*\b(system|service|server)\b",
        "System Status",
    ),
    (
        "system_restart",
        r"\b(restart|reboot|reload)\b.*\b(service|server|system)\b",
        "System Restart",
    ),
    # Knowledge operations
    ("knowledge_search", r"\b(what|how|why|when|where)\b.*\?", "Knowledge Query"),
    (
        "knowledge_add",
        r"\b(add|store|remember|save)\b.*\b(knowledge|fact|info)\b",
        "Knowledge Addition",
    ),
    # Terminal/Command operations
    ("terminal_command", r"\b(run|execute|command)\b", "Terminal Command"),
    (
        "terminal_output",
        r"\b(output|result|response)\b.*\b(command|terminal)\b",
        "Terminal Output",
    ),
    # Git operations
    ("git_status", r"\b(git)\b.*\b(status|diff|log)\b", "Git Status"),
    ("git_commit", r"\b(commit|push|pull)\b", "Git Operations"),
    # General assistance
    ("help_request", r"\b(help|assist|support)\b", "Help Request"),
    ("greeting", r"^(hi|hello|hey|good morning|good afternoon)\b", "Greeting"),
    ("thanks", r"\b(thank|thanks|appreciate)\b", "Appreciation"),
    (
        "clarification",
        r"\b(what do you mean|clarify|explain more)\b",
        "Clarification Request",
    ),
]

# O(1) lookup for intent names by ID (Issue #315 + #326)
INTENT_ID_TO_NAME = {pid: name for pid, _, name in INTENT_PATTERNS}


def _get_intent_name(intent_id: str) -> str:
    """Get intent name by ID using O(1) lookup. (Issue #315 - extracted)"""
    return INTENT_ID_TO_NAME.get(intent_id, "Unknown")


def _collect_user_samples(
    messages: List[Dict], intent_stats: Dict, analyzer: "ConversationAnalyzer"
) -> None:
    """Collect sample messages for each intent. (Issue #315 - extracted)"""
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        intent_id, _ = analyzer.detect_intent(content)
        if len(intent_stats[intent_id]["samples"]) < 3:
            intent_stats[intent_id]["samples"].append(content[:200])


# ============================================================================
# Conversation Analyzer Engine
# ============================================================================


class ConversationAnalyzer:
    """Engine for analyzing conversation patterns"""

    def __init__(self):
        """Initialize conversation analyzer with intent cache."""
        self.intent_cache: Dict[str, str] = {}

    def detect_intent(self, message: str) -> Tuple[str, str]:
        """Detect the intent of a message"""
        message_lower = message.lower()

        for intent_id, pattern, intent_name in INTENT_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return intent_id, intent_name

        return "unknown", "Unknown Intent"

    def _process_message_for_extraction(
        self,
        msg: Dict[str, Any],
        intents: List[str],
        timestamps: List[datetime],
    ) -> Tuple[int, int]:
        """
        Process a single message and extract intent/sentiment data.

        Returns tuple of (success_count, frustration_count).
        Issue #620.
        """
        content = msg.get("content", "")
        role = msg.get("role", "")
        timestamp = msg.get("timestamp")
        success_count = 0
        frustration_count = 0

        # Parse timestamp
        if timestamp:
            ts = _parse_timestamp(timestamp)
            if ts:
                timestamps.append(ts)

        # Process user messages for intent and sentiment
        if role == "user":
            intent_id, _ = self.detect_intent(content)
            intents.append(intent_id)

            content_lower = content.lower()
            if any(word in content_lower for word in SUCCESS_INDICATORS):
                success_count = 1
            if any(word in content_lower for word in FRUSTRATION_INDICATORS):
                frustration_count = 1

        return success_count, frustration_count

    def extract_conversation_data(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract structured data from a conversation.

        Issue #620: Refactored using Extract Method pattern.
        """
        if not messages:
            return {
                "turns": 0,
                "intents": [],
                "duration_seconds": 0,
                "success_indicators": 0,
                "frustration_indicators": 0,
            }

        intents: List[str] = []
        timestamps: List[datetime] = []
        success_indicators = 0
        frustration_indicators = 0

        for msg in messages:
            success, frustration = self._process_message_for_extraction(
                msg, intents, timestamps
            )
            success_indicators += success
            frustration_indicators += frustration

        duration = 0
        if len(timestamps) >= 2:
            duration = (max(timestamps) - min(timestamps)).total_seconds()

        return {
            "turns": len(messages),
            "intents": intents,
            "duration_seconds": duration,
            "success_indicators": success_indicators,
            "frustration_indicators": frustration_indicators,
        }

    def _track_conversation_intents(
        self,
        conv: Dict[str, Any],
        intent_transitions: Dict[str, Dict[str, int]],
        intent_failures: Dict[str, int],
        intent_repetitions: Dict[str, int],
    ) -> None:
        """
        Track intent transitions, repetitions and failures for a conversation.

        Issue #620.
        """
        intents = conv.get("intents", [])
        frustration = conv.get("frustration_indicators", 0)

        # Track transitions and repetitions
        for i in range(len(intents) - 1):
            intent_transitions[intents[i]][intents[i + 1]] += 1
            if intents[i] == intents[i + 1]:
                intent_repetitions[intents[i]] += 1

        # Track failures
        if frustration > 0 and intents:
            intent_failures[intents[-1]] += frustration

    def _build_repetition_bottlenecks(
        self,
        intent_repetitions: Dict[str, int],
    ) -> List[FlowBottleneck]:
        """
        Build bottleneck objects for repeated intent patterns.

        Issue #620.
        """
        bottlenecks = []
        for intent_id, count in intent_repetitions.items():
            if count >= 3:
                bottlenecks.append(
                    FlowBottleneck(
                        bottleneck_id=f"repetition_{intent_id}",
                        location=intent_id,
                        description=f"Users frequently repeat '{intent_id}' requests, indicating unclear responses",
                        impact_score=min(100, count * 10),
                        affected_conversations=count,
                        suggested_improvements=[
                            "Improve response clarity",
                            "Add confirmation prompts",
                            "Provide step-by-step guidance",
                        ],
                    )
                )
        return bottlenecks

    def _build_failure_bottlenecks(
        self,
        intent_failures: Dict[str, int],
    ) -> List[FlowBottleneck]:
        """
        Build bottleneck objects for high-frustration intent patterns.

        Issue #620.
        """
        bottlenecks = []
        for intent_id, failure_count in intent_failures.items():
            if failure_count >= 2:
                bottlenecks.append(
                    FlowBottleneck(
                        bottleneck_id=f"failure_{intent_id}",
                        location=intent_id,
                        description=f"High frustration indicators after '{intent_id}' requests",
                        impact_score=min(100, failure_count * 15),
                        affected_conversations=failure_count,
                        suggested_improvements=[
                            f"Review {intent_id} handling logic",
                            "Add better error messages",
                            "Provide alternative approaches",
                        ],
                    )
                )
        return bottlenecks

    def identify_bottlenecks(
        self, conversations: List[Dict[str, Any]]
    ) -> List[FlowBottleneck]:
        """
        Identify bottlenecks in conversation flows.

        Issue #620: Refactored using Extract Method pattern.
        """
        intent_transitions: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        intent_failures: Dict[str, int] = defaultdict(int)
        intent_repetitions: Dict[str, int] = defaultdict(int)

        # Track intent data for all conversations
        for conv in conversations:
            self._track_conversation_intents(
                conv, intent_transitions, intent_failures, intent_repetitions
            )

        # Build bottleneck lists
        bottlenecks = self._build_repetition_bottlenecks(intent_repetitions)
        bottlenecks.extend(self._build_failure_bottlenecks(intent_failures))

        # Sort by impact score and return top 10
        bottlenecks.sort(key=lambda b: b.impact_score, reverse=True)
        return bottlenecks[:10]

    def _update_intent_tracking(
        self,
        conv_data: Dict[str, Any],
        intent_counts: Counter,
        intent_success: Dict[str, List[float]],
        flow_counts: Counter,
    ) -> None:
        """
        Update intent tracking counters for a conversation.

        Issue #620: Extracted from _process_conversation_data.

        Args:
            conv_data: Processed conversation data
            intent_counts: Counter for intent occurrences
            intent_success: Dict mapping intent to success rates
            flow_counts: Counter for flow paths
        """
        # Count intents
        for intent in conv_data["intents"]:
            intent_counts[intent] += 1

        # Track intent success
        if conv_data["intents"]:
            success_rate = conv_data["success_indicators"] / max(
                1, len(conv_data["intents"])
            )
            for intent in set(conv_data["intents"]):
                intent_success[intent].append(success_rate)

        # Track flow paths
        if len(conv_data["intents"]) >= 2:
            flow_path = tuple(conv_data["intents"][:5])  # First 5 intents
            flow_counts[flow_path] += 1

    def _update_hourly_distribution(
        self,
        messages: List[Dict[str, Any]],
        hourly_dist: Counter,
    ) -> None:
        """
        Update hourly distribution counter from message timestamps.

        Issue #620: Extracted from _process_conversation_data.

        Args:
            messages: List of conversation messages
            hourly_dist: Counter for hourly distribution
        """
        if not messages or not messages[0].get("timestamp"):
            return

        try:
            ts_str = messages[0]["timestamp"]
            if isinstance(ts_str, str):
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                hourly_dist[ts.strftime("%H:00")] += 1
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Failed to parse conversation timestamp: %s", e)

    def _process_conversation_data(
        self,
        conversations: List[Dict[str, Any]],
    ) -> Tuple[
        List[Dict],
        Counter,
        Dict[str, List[float]],
        Counter,
        Counter,
        int,
        int,
        int,
        int,
    ]:
        """
        Process all conversations and extract aggregated data.

        Issue #281: Extracted helper for conversation processing.
        Issue #620: Further refactored with helper methods.
        """
        processed_convs = []
        intent_counts: Counter = Counter()
        intent_success: Dict[str, List[float]] = defaultdict(list)
        flow_counts: Counter = Counter()
        hourly_dist: Counter = Counter()
        totals = {"messages": 0, "duration": 0, "success": 0, "frustration": 0}

        for conv in conversations:
            messages = conv.get("messages", [])
            conv_data = self.extract_conversation_data(messages)
            processed_convs.append(conv_data)

            totals["messages"] += conv_data["turns"]
            totals["duration"] += conv_data["duration_seconds"]
            totals["success"] += conv_data["success_indicators"]
            totals["frustration"] += conv_data["frustration_indicators"]

            self._update_intent_tracking(
                conv_data, intent_counts, intent_success, flow_counts
            )
            self._update_hourly_distribution(messages, hourly_dist)

        return (
            processed_convs,
            intent_counts,
            intent_success,
            flow_counts,
            hourly_dist,
            totals["messages"],
            totals["duration"],
            totals["success"],
            totals["frustration"],
        )

    def _build_intent_patterns(
        self,
        intent_counts: Counter,
        intent_success: Dict[str, List[float]],
        total_messages: int,
    ) -> List["IntentPattern"]:
        """
        Build intent pattern list from aggregated data.

        Issue #281: Extracted helper for intent pattern building.

        Args:
            intent_counts: Counter of intent occurrences
            intent_success: Dict mapping intent to success rates
            total_messages: Total message count

        Returns:
            List of IntentPattern objects
        """
        intent_patterns = []
        for intent_id, count in intent_counts.most_common(15):
            success_rates = intent_success.get(intent_id, [0.5])
            avg_success = sum(success_rates) / len(success_rates)

            # Find intent name
            intent_name = "Unknown"
            for pid, _, name in INTENT_PATTERNS:
                if pid == intent_id:
                    intent_name = name
                    break

            intent_patterns.append(
                IntentPattern(
                    intent_id=intent_id,
                    intent_name=intent_name,
                    pattern_regex="",  # Don't expose regex
                    occurrences=count,
                    success_rate=round(avg_success * 100, 1),
                    avg_turns_to_resolve=round(total_messages / max(1, count), 1),
                    sample_queries=[],
                )
            )
        return intent_patterns

    def _build_common_flows(self, flow_counts: Counter) -> List["ConversationFlow"]:
        """
        Build common flows list from flow counts.

        Issue #281: Extracted helper for flow building.

        Args:
            flow_counts: Counter of flow path occurrences

        Returns:
            List of ConversationFlow objects
        """
        common_flows = []
        for flow_path, freq in flow_counts.most_common(10):
            common_flows.append(
                ConversationFlow(
                    flow_id=f"flow_{'_'.join(flow_path[:3])}",
                    path=list(flow_path),
                    frequency=freq,
                    avg_duration_seconds=0,  # Would need per-flow tracking
                    completion_rate=80.0,  # Estimated
                    drop_off_point=None,
                )
            )
        return common_flows

    def _create_empty_analysis_result(self) -> ConversationAnalysisResult:
        """
        Create an empty analysis result for when no conversations exist.

        Issue #620.
        """
        return ConversationAnalysisResult(
            metrics=ConversationMetrics(
                total_conversations=0,
                total_messages=0,
                avg_messages_per_conversation=0,
                avg_conversation_duration_seconds=0,
                user_satisfaction_estimate=0,
                resolution_rate=0,
                escalation_rate=0,
            ),
            intent_patterns=[],
            common_flows=[],
            bottlenecks=[],
            hourly_distribution={},
            analysis_period="N/A",
            conversations_analyzed=0,
        )

    def _calculate_metrics(
        self,
        n_convs: int,
        processed_convs: List[Dict],
        total_messages: int,
        total_duration: int,
        total_success: int,
        total_frustration: int,
    ) -> ConversationMetrics:
        """
        Calculate conversation metrics from aggregated data.

        Issue #620.
        """
        satisfaction = (total_success / max(1, total_success + total_frustration)) * 100
        resolution_rate = (
            sum(1 for c in processed_convs if c["success_indicators"] > 0)
            / max(1, n_convs)
            * 100
        )

        return ConversationMetrics(
            total_conversations=n_convs,
            total_messages=total_messages,
            avg_messages_per_conversation=round(total_messages / max(1, n_convs), 1),
            avg_conversation_duration_seconds=round(
                total_duration / max(1, n_convs), 1
            ),
            user_satisfaction_estimate=round(satisfaction, 1),
            resolution_rate=round(resolution_rate, 1),
            escalation_rate=round(total_frustration / max(1, n_convs) * 100, 1),
        )

    async def analyze_conversations(
        self,
        conversations: List[Dict[str, Any]],
    ) -> ConversationAnalysisResult:
        """
        Perform full conversation analysis.

        Issue #281: Refactored from 136 lines to use extracted helper methods.
        Issue #620: Further refactored with Extract Method pattern.
        """
        if not conversations:
            return self._create_empty_analysis_result()

        # Process all conversations
        (
            processed_convs,
            intent_counts,
            intent_success,
            flow_counts,
            hourly_dist,
            total_messages,
            total_duration,
            total_success,
            total_frustration,
        ) = self._process_conversation_data(conversations)

        n_convs = len(conversations)

        # Calculate metrics using helper
        metrics = self._calculate_metrics(
            n_convs,
            processed_convs,
            total_messages,
            total_duration,
            total_success,
            total_frustration,
        )

        # Build result components
        intent_patterns = self._build_intent_patterns(
            intent_counts, intent_success, total_messages
        )
        common_flows = self._build_common_flows(flow_counts)
        bottlenecks = self.identify_bottlenecks(processed_convs)

        return ConversationAnalysisResult(
            metrics=metrics,
            intent_patterns=intent_patterns,
            common_flows=common_flows,
            bottlenecks=bottlenecks,
            hourly_distribution=dict(sorted(hourly_dist.items())),
            analysis_period="Last 24 hours",
            conversations_analyzed=n_convs,
        )


# Global analyzer instance
conversation_analyzer = ConversationAnalyzer()


# ============================================================================
# Data Loading Utilities
# ============================================================================


async def load_chat_sessions(hours: int = 24) -> List[Dict[str, Any]]:
    """Load chat sessions from storage (Issue #315 - reduced nesting)."""
    import json

    sessions = []
    cutoff = datetime.now() - timedelta(hours=hours)

    # Try to load from chat history files
    chat_dir = (
        PATH.DATA_DIR / "chat_history"
        if hasattr(PATH, "DATA_DIR")
        else Path("data/chat_history")
    )

    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(chat_dir.exists):
        return sessions

    # Issue #358 - avoid blocking with lambda for proper glob() execution in thread
    session_files = await asyncio.to_thread(lambda: list(chat_dir.glob("*.json")))
    for session_file in session_files:
        try:
            async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
                content = await f.read()
                session = json.loads(content)

                if _is_session_in_range(session, cutoff):
                    sessions.append(session)
        except OSError as e:
            logger.debug("Failed to read session file %s: %s", session_file, e)
        except Exception as e:
            logger.debug("Error loading session %s: %s", session_file, e)

    return sessions


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_conversations",
    error_code_prefix="CONVFLOW",
)
@router.get("/analyze", response_model=ConversationAnalysisResult)
async def analyze_conversations(
    hours: int = Query(
        24, ge=1, le=168, description="Hours of conversations to analyze"
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze conversation patterns and flows.

    Discovers user intents, common conversation paths, bottlenecks,
    and calculates key metrics.

    Issue #744: Requires admin authentication.
    """
    try:
        # Load conversations
        conversations = await load_chat_sessions(hours)

        if not conversations:
            # Return empty result with appropriate message
            return ConversationAnalysisResult(
                metrics=ConversationMetrics(
                    total_conversations=0,
                    total_messages=0,
                    avg_messages_per_conversation=0,
                    avg_conversation_duration_seconds=0,
                    user_satisfaction_estimate=0,
                    resolution_rate=0,
                    escalation_rate=0,
                ),
                intent_patterns=[],
                common_flows=[],
                bottlenecks=[],
                hourly_distribution={},
                analysis_period=f"Last {hours} hours (no data)",
                conversations_analyzed=0,
            )

        # Perform analysis
        result = await conversation_analyzer.analyze_conversations(conversations)
        result.analysis_period = f"Last {hours} hours"

        return result

    except Exception as e:
        logger.error("Error analyzing conversations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_intent_stats",
    error_code_prefix="CONVFLOW",
)
@router.get("/intents")
async def get_intent_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get detailed intent statistics.

    Issue #744: Requires admin authentication.
    """
    try:
        conversations = await load_chat_sessions(hours)

        intent_stats: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "samples": [], "success_count": 0}
        )

        for conv in conversations:
            messages = conv.get("messages", [])
            conv_data = conversation_analyzer.extract_conversation_data(messages)

            for intent in conv_data["intents"]:
                intent_stats[intent]["count"] += 1
                if conv_data["success_indicators"] > 0:
                    intent_stats[intent]["success_count"] += 1

            # Collect samples using helper (Issue #315 - reduces nesting)
            _collect_user_samples(messages, intent_stats, conversation_analyzer)

        # Format results using O(1) lookup (Issue #315 + #326)
        results = []
        for intent_id, stats in sorted(
            intent_stats.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            results.append(
                {
                    "intent_id": intent_id,
                    "intent_name": _get_intent_name(intent_id),
                    "count": stats["count"],
                    "success_rate": round(
                        stats["success_count"] / max(1, stats["count"]) * 100, 1
                    ),
                    "samples": stats["samples"],
                }
            )

        return {
            "intents": results,
            "total_intents_detected": sum(s["count"] for s in intent_stats.values()),
            "unique_intents": len(intent_stats),
            "analysis_hours": hours,
        }

    except Exception as e:
        logger.error("Error getting intent stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_flow_paths",
    error_code_prefix="CONVFLOW",
)
@router.get("/flows")
async def get_flow_paths(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    min_frequency: int = Query(2, ge=1, description="Minimum flow frequency"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get common conversation flow paths.

    Issue #744: Requires admin authentication.
    """
    try:
        conversations = await load_chat_sessions(hours)

        flow_data: Dict[Tuple, Dict] = defaultdict(
            lambda: {"count": 0, "durations": [], "successes": 0}
        )

        for conv in conversations:
            messages = conv.get("messages", [])
            conv_data = conversation_analyzer.extract_conversation_data(messages)

            if len(conv_data["intents"]) >= 2:
                flow_path = tuple(conv_data["intents"][:5])
                flow_data[flow_path]["count"] += 1
                flow_data[flow_path]["durations"].append(conv_data["duration_seconds"])
                if conv_data["success_indicators"] > 0:
                    flow_data[flow_path]["successes"] += 1

        # Filter and format
        flows = []
        for path, data in sorted(
            flow_data.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            if data["count"] >= min_frequency:
                avg_duration = (
                    sum(data["durations"]) / len(data["durations"])
                    if data["durations"]
                    else 0
                )
                flows.append(
                    {
                        "path": list(path),
                        "frequency": data["count"],
                        "avg_duration_seconds": round(avg_duration, 1),
                        "completion_rate": round(
                            data["successes"] / data["count"] * 100, 1
                        ),
                        "path_display": " → ".join(path),
                    }
                )

        return {
            "flows": flows[:20],
            "total_unique_flows": len(flow_data),
            "analysis_hours": hours,
        }

    except Exception as e:
        logger.error("Error getting flow paths: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_bottlenecks",
    error_code_prefix="CONVFLOW",
)
@router.get("/bottlenecks")
async def get_bottlenecks(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get identified conversation bottlenecks.

    Issue #744: Requires admin authentication.
    """
    try:
        conversations = await load_chat_sessions(hours)

        # Process conversations
        processed = []
        for conv in conversations:
            messages = conv.get("messages", [])
            conv_data = conversation_analyzer.extract_conversation_data(messages)
            processed.append(conv_data)

        bottlenecks = conversation_analyzer.identify_bottlenecks(processed)

        return {
            "bottlenecks": [b.model_dump() for b in bottlenecks],
            "total_identified": len(bottlenecks),
            "conversations_analyzed": len(conversations),
            "analysis_hours": hours,
        }

    except Exception as e:
        logger.error("Error getting bottlenecks: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hourly_distribution",
    error_code_prefix="CONVFLOW",
)
@router.get("/distribution")
async def get_hourly_distribution(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get conversation distribution by hour (Issue #315: depth 6→3).

    Issue #744: Requires admin authentication.
    """
    try:
        conversations = await load_chat_sessions(hours)

        hourly: Counter = Counter()
        daily: Counter = Counter()

        for conv in conversations:
            messages = conv.get("messages", [])
            if not messages:
                continue
            ts = _parse_timestamp(messages[0].get("timestamp"))
            if not ts:
                continue
            hourly[ts.strftime("%H:00")] += 1
            daily[ts.strftime("%A")] += 1

        return {
            "hourly_distribution": dict(sorted(hourly.items())),
            "daily_distribution": dict(daily.most_common()),
            "peak_hour": hourly.most_common(1)[0][0] if hourly else None,
            "peak_day": daily.most_common(1)[0][0] if daily else None,
            "analysis_hours": hours,
        }

    except Exception as e:
        logger.error("Error getting distribution: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_intent",
    error_code_prefix="CONVFLOW",
)
@router.post("/detect-intent")
async def detect_intent(
    message: str = Query(..., description="Message to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Detect intent from a single message.

    Issue #744: Requires admin authentication.
    """
    try:
        intent_id, intent_name = conversation_analyzer.detect_intent(message)

        return {
            "message": message[:200],
            "detected_intent": intent_id,
            "intent_name": intent_name,
            "confidence": 0.85 if intent_id != "unknown" else 0.0,
        }

    except Exception as e:
        logger.error("Error detecting intent: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
