# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Flow Analyzer

Issue #381: Extracted from conversation_flow_analyzer.py god class refactoring.
Contains the main ConversationFlowAnalyzer class that coordinates analysis.
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .classifiers import IntentClassifier, ResponseClassifier
from .types import (
    SATISFACTION_SIGNALS,
    AnalysisResult,
    Bottleneck,
    BottleneckType,
    ConversationFlow,
    ConversationMessage,
    FlowPattern,
    FlowState,
    IntentCategory,
    Optimization,
    OptimizationType,
    ResponseType,
)

logger = logging.getLogger(__name__)


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

    def _parse_single_message(
        self,
        msg: Dict[str, Any],
    ) -> Tuple[ConversationMessage, Optional[IntentCategory], int, int, Optional[str]]:
        """
        Parse a single message from raw dict into ConversationMessage.

        Issue #281: Extracted from parse_conversation to reduce function length.

        Args:
            msg: Raw message dict with role, content, etc.

        Returns:
            Tuple of:
            - ConversationMessage
            - Intent (if user message)
            - Error increment (0 or 1)
            - Clarification increment (0 or 1)
            - Satisfaction signal (or None)
        """
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp")
        latency = msg.get("latency_ms", 0.0)

        if timestamp and isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = None

        intent = None
        response_type = None
        error_inc = 0
        clarification_inc = 0
        satisfaction_signal = None

        if role == "user":
            intent, _ = IntentClassifier.classify(content)
            if intent == IntentCategory.CLARIFICATION:
                clarification_inc = 1
            # Issue #380: Use module-level frozenset for O(1) lookup
            if any(word in content.lower() for word in SATISFACTION_SIGNALS):
                satisfaction_signal = content[:100]
        elif role == "assistant":
            response_type = ResponseClassifier.classify(content)
            if response_type == ResponseType.ERROR_MESSAGE:
                error_inc = 1

        has_tool_call = bool(msg.get("tool_calls")) or "using the" in content.lower()

        parsed_msg = ConversationMessage(
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

        return parsed_msg, intent, error_inc, clarification_inc, satisfaction_signal

    def _aggregate_message_metrics(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[
        List[ConversationMessage], List[IntentCategory], float, int, int, List[str]
    ]:
        """
        Parse messages and aggregate metrics. Issue #620.

        Args:
            messages: List of raw message dicts

        Returns:
            Tuple of (parsed_messages, intent_sequence, total_latency,
                     error_count, clarification_count, satisfaction_signals)
        """
        parsed_messages: List[ConversationMessage] = []
        intent_sequence: List[IntentCategory] = []
        total_latency = 0.0
        error_count = 0
        clarification_count = 0
        user_satisfaction_signals: List[str] = []

        for msg in messages:
            (
                parsed_msg,
                intent,
                err_inc,
                clar_inc,
                sat_signal,
            ) = self._parse_single_message(msg)
            parsed_messages.append(parsed_msg)
            total_latency += parsed_msg.latency_ms or 0.0
            if intent:
                intent_sequence.append(intent)
            error_count += err_inc
            clarification_count += clar_inc
            if sat_signal:
                user_satisfaction_signals.append(sat_signal)

        return (
            parsed_messages,
            intent_sequence,
            total_latency,
            error_count,
            clarification_count,
            user_satisfaction_signals,
        )

    def _calculate_success(
        self, final_state: FlowState, error_count: int, clarification_count: int
    ) -> bool:
        """
        Calculate if conversation was successful. Issue #620.

        Args:
            final_state: Final flow state
            error_count: Number of errors
            clarification_count: Number of clarifications

        Returns:
            True if conversation was successful
        """
        if final_state not in (FlowState.COMPLETED, FlowState.INITIATED):
            return False
        if error_count > 2 or clarification_count > self.clarification_threshold:
            return False
        return True

    def parse_conversation(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "unknown",
    ) -> ConversationFlow:
        """
        Parse a raw conversation into a ConversationFlow. Issue #620.

        Args:
            messages: List of message dicts with 'role' and 'content'
            session_id: Session identifier

        Returns:
            Parsed ConversationFlow
        """
        (
            parsed_messages,
            intent_sequence,
            total_latency,
            error_count,
            clarification_count,
            user_satisfaction_signals,
        ) = self._aggregate_message_metrics(messages)

        final_state = self._determine_final_state(
            parsed_messages, error_count, clarification_count
        )
        primary_intent = self._determine_primary_intent(intent_sequence)
        successful = self._calculate_success(
            final_state, error_count, clarification_count
        )
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

    def _ingest_conversations(
        self,
        conversations: Optional[List[List[Dict[str, Any]]]] = None,
        flows: Optional[List[ConversationFlow]] = None,
    ) -> None:
        """
        Parse and ingest raw conversations and flows into internal storage.

        Args:
            conversations: Raw conversation data (list of message lists)
            flows: Pre-parsed ConversationFlow objects

        Issue #620.
        """
        if conversations:
            for i, conv in enumerate(conversations):
                flow = self.parse_conversation(conv, session_id=f"session_{i}")
                self._flows.append(flow)

        if flows:
            self._flows.extend(flows)

    def _compute_basic_statistics(self) -> Dict[str, Any]:
        """
        Compute basic statistics from analyzed flows.

        Returns:
            Dict with total_messages, avg_turns, avg_latency, success_rate

        Issue #620.
        """
        total_messages = sum(len(f.messages) for f in self._flows)
        avg_turns = sum(f.turn_count for f in self._flows) / len(self._flows)
        avg_latency = sum(f.total_latency_ms for f in self._flows) / len(self._flows)
        success_rate = sum(1 for f in self._flows if f.successful) / len(self._flows)

        return {
            "total_messages": total_messages,
            "avg_turns": avg_turns,
            "avg_latency": avg_latency,
            "success_rate": success_rate,
        }

    def _build_analysis_result(
        self,
        stats: Dict[str, Any],
        intent_dist: Dict[IntentCategory, int],
        response_dist: Dict[ResponseType, int],
        flow_patterns: List[FlowPattern],
        bottlenecks: List[Bottleneck],
        optimizations: List[Optimization],
        common_paths: List[List[IntentCategory]],
        error_recovery: List[Dict[str, Any]],
        cache_opportunities: List[Dict[str, Any]],
        health_score: float,
    ) -> AnalysisResult:
        """
        Build the final AnalysisResult from computed components.

        Issue #620.
        """
        return AnalysisResult(
            total_conversations=len(self._flows),
            total_messages=stats["total_messages"],
            avg_turn_count=stats["avg_turns"],
            avg_latency_ms=stats["avg_latency"],
            success_rate=stats["success_rate"],
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
        self._ingest_conversations(conversations, flows)

        if not self._flows:
            return self._empty_result()

        stats = self._compute_basic_statistics()
        intent_dist = self._compute_intent_distribution()
        response_dist = self._compute_response_distribution()
        flow_patterns = self._extract_flow_patterns()
        bottlenecks = self._detect_bottlenecks()
        optimizations = self._generate_optimizations(flow_patterns, bottlenecks)
        common_paths = self._find_common_paths()
        error_recovery = self._analyze_error_recovery()
        cache_opportunities = self._find_cache_opportunities()
        health_score = self._calculate_health_score(
            stats["success_rate"], stats["avg_latency"], len(bottlenecks)
        )

        return self._build_analysis_result(
            stats,
            intent_dist,
            response_dist,
            flow_patterns,
            bottlenecks,
            optimizations,
            common_paths,
            error_recovery,
            cache_opportunities,
            health_score,
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
        sequence_groups: Dict[
            Tuple[IntentCategory, ...], List[ConversationFlow]
        ] = defaultdict(list)

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

    def _create_bottleneck_if_significant(
        self,
        sessions: List[str],
        bottleneck_type: BottleneckType,
        description_template: str,
        severity: str,
        recommendations: List[str],
    ) -> Optional[Bottleneck]:
        """Create a bottleneck entry if session count is significant (Issue #665: extracted helper).

        Args:
            sessions: List of affected session IDs
            bottleneck_type: Type of bottleneck
            description_template: Description with {count} placeholder
            severity: Severity level (medium, high, critical)
            recommendations: List of recommendations

        Returns:
            Bottleneck instance if significant, None otherwise
        """
        if len(sessions) >= self.min_pattern_occurrences:
            return Bottleneck(
                bottleneck_type=bottleneck_type,
                description=description_template.format(count=len(sessions)),
                severity=severity,
                occurrence_count=len(sessions),
                affected_sessions=sessions[:10],
                recommendations=recommendations,
            )
        return None

    def _detect_bottlenecks(self) -> List[Bottleneck]:
        """Detect conversation bottlenecks.

        Issue #665: Refactored to use _create_bottleneck_if_significant helper.
        """
        bottlenecks: List[Bottleneck] = []

        # Slow response detection
        slow_sessions = [
            f.session_id
            for f in self._flows
            if f.total_latency_ms > self.slow_response_threshold_ms * f.turn_count
        ]
        slow_severity = "medium" if len(slow_sessions) < 10 else "high"
        bottleneck = self._create_bottleneck_if_significant(
            slow_sessions,
            BottleneckType.SLOW_RESPONSE,
            "High latency detected in {count} sessions",
            slow_severity,
            [
                "Consider caching common responses",
                "Optimize LLM prompt length",
                "Review tool call latency",
            ],
        )
        if bottleneck:
            bottlenecks.append(bottleneck)

        # Repeated clarification detection
        confused_sessions = [
            f.session_id
            for f in self._flows
            if f.clarification_count >= self.clarification_threshold
        ]
        bottleneck = self._create_bottleneck_if_significant(
            confused_sessions,
            BottleneckType.REPEATED_CLARIFICATION,
            "Excessive clarifications in {count} sessions",
            "high",
            [
                "Improve initial intent classification",
                "Add disambiguation prompts",
                "Enhance context gathering",
            ],
        )
        if bottleneck:
            bottlenecks.append(bottleneck)

        # Error loop detection
        error_sessions = [f.session_id for f in self._flows if f.error_count > 2]
        bottleneck = self._create_bottleneck_if_significant(
            error_sessions,
            BottleneckType.ERROR_LOOP,
            "Multiple errors in {count} sessions",
            "critical",
            [
                "Improve error handling and recovery",
                "Add fallback responses",
                "Implement graceful degradation",
            ],
        )
        if bottleneck:
            bottlenecks.append(bottleneck)

        # Excessive turns detection
        long_sessions = [
            f.session_id for f in self._flows if f.turn_count > self.max_turns_threshold
        ]
        bottleneck = self._create_bottleneck_if_significant(
            long_sessions,
            BottleneckType.EXCESSIVE_TURNS,
            "Excessive turns in {count} sessions",
            "medium",
            [
                "Add workflow shortcuts",
                "Improve single-turn completions",
                "Reduce back-and-forth",
            ],
        )
        if bottleneck:
            bottlenecks.append(bottleneck)

        return bottlenecks

    def _create_caching_optimization(
        self, patterns: List[FlowPattern]
    ) -> Optional[Optimization]:
        """
        Create caching optimization from frequent patterns. Issue #620.

        Args:
            patterns: List of flow patterns to analyze

        Returns:
            Optimization if frequent patterns exist, None otherwise
        """
        frequent = [p for p in patterns if p.occurrence_count >= 5]
        if not frequent:
            return None
        return Optimization(
            optimization_type=OptimizationType.CACHING,
            description="Cache responses for frequently occurring conversation patterns",
            impact="high",
            effort="medium",
            affected_patterns=[p.pattern_id for p in frequent],
            implementation_notes="Implement response caching for common intents",
            estimated_improvement="20-30% latency reduction",
        )

    def _create_prompt_optimization(
        self, patterns: List[FlowPattern]
    ) -> Optional[Optimization]:
        """
        Create prompt improvement optimization from low success patterns. Issue #620.

        Args:
            patterns: List of flow patterns to analyze

        Returns:
            Optimization if low success patterns exist, None otherwise
        """
        low_success = [p for p in patterns if p.success_rate < 0.5]
        if not low_success:
            return None
        return Optimization(
            optimization_type=OptimizationType.PROMPT_IMPROVEMENT,
            description="Improve prompts for low-success conversation patterns",
            impact="high",
            effort="medium",
            affected_patterns=[p.pattern_id for p in low_success],
            implementation_notes="Review and enhance system prompts",
            estimated_improvement="30-50% success rate increase",
        )

    def _create_bottleneck_optimizations(
        self, bottlenecks: List[Bottleneck]
    ) -> List[Optimization]:
        """
        Create optimizations from detected bottlenecks. Issue #620.

        Args:
            bottlenecks: List of detected bottlenecks

        Returns:
            List of optimizations addressing bottlenecks
        """
        result: List[Optimization] = []
        if any(b.bottleneck_type == BottleneckType.ERROR_LOOP for b in bottlenecks):
            result.append(
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
        if any(
            b.bottleneck_type == BottleneckType.REPEATED_CLARIFICATION
            for b in bottlenecks
        ):
            result.append(
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
        return result

    def _generate_optimizations(
        self, patterns: List[FlowPattern], bottlenecks: List[Bottleneck]
    ) -> List[Optimization]:
        """
        Generate optimization suggestions. Issue #620.

        Args:
            patterns: Detected flow patterns
            bottlenecks: Detected bottlenecks

        Returns:
            List of optimization suggestions
        """
        optimizations: List[Optimization] = []
        caching_opt = self._create_caching_optimization(patterns)
        if caching_opt:
            optimizations.append(caching_opt)
        prompt_opt = self._create_prompt_optimization(patterns)
        if prompt_opt:
            optimizations.append(prompt_opt)
        optimizations.extend(self._create_bottleneck_optimizations(bottlenecks))
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
