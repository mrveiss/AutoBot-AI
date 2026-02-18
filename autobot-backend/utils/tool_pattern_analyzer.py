# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool Pattern Analyzer for Claude API Optimization

This module analyzes tool usage patterns to identify optimization opportunities
and prevent Claude API rate limiting during development sessions. It provides
comprehensive analysis of tool call patterns, frequency, timing, and efficiency.

Key features:
- Real-time tool usage pattern analysis
- API call optimization recommendations
- Tool sequence pattern detection
- Efficiency scoring and benchmarking
- Integration with TodoWrite optimizer and Claude API infrastructure
"""

import asyncio
import json
import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for tool classification (Issue #326)
READ_KEYWORDS = {"read", "list", "glob", "get"}
WRITE_KEYWORDS = {"write", "edit", "create", "update"}
SEARCH_KEYWORDS = {"grep", "search", "find"}
EXECUTION_KEYWORDS = {"bash", "execute", "run"}
COMMUNICATION_KEYWORDS = {"todo", "task", "agent"}
ANALYSIS_KEYWORDS = {"analyze", "diagnostic", "lint"}
LARGE_PATH_INDICATORS = {"/large/", "/data/", "/logs/"}
BATCH_PARAMETER_KEYS = {"recursive", "batch", "all"}

# Issue #380: Module-level frozenset for file reading tools (inefficient pattern detection)
_FILE_READING_TOOLS: FrozenSet[str] = frozenset({"Read", "Glob"})

# Issue #380: Module-level tuple for JSON-serializable primitive types
_JSON_PRIMITIVE_TYPES = (str, int, bool)


class ToolCallType(Enum):
    """Classification of tool call types"""

    READ_OPERATION = "read_operation"  # File reads, directory lists
    WRITE_OPERATION = "write_operation"  # File writes, edits
    SEARCH_OPERATION = "search_operation"  # Grep, find, glob
    EXECUTION = "execution"  # Bash commands, code execution
    ANALYSIS = "analysis"  # Code analysis, diagnostics
    COMMUNICATION = "communication"  # TodoWrite, API calls
    NAVIGATION = "navigation"  # Directory changes, file browsing


# Tool call types for optimization detection - placed after enum (Issue #326)
BATCHABLE_CALL_TYPES = {ToolCallType.READ_OPERATION, ToolCallType.WRITE_OPERATION}


class EfficiencyLevel(Enum):
    """Tool usage efficiency levels"""

    OPTIMAL = "optimal"  # Best possible efficiency
    GOOD = "good"  # Good efficiency, minor optimizations possible
    MODERATE = "moderate"  # Moderate efficiency, optimizations recommended
    POOR = "poor"  # Poor efficiency, significant optimizations needed
    CRITICAL = "critical"  # Critical inefficiency, immediate optimization required


@dataclass
class ToolCall:
    """Individual tool call record"""

    tool_name: str
    call_time: datetime
    parameters: Dict[str, Any]
    response_time: float
    success: bool
    error_message: Optional[str] = None
    api_cost: int = 1  # Estimated API cost (1-10 scale)
    call_type: Optional[ToolCallType] = None
    session_id: str = ""
    sequence_position: int = 0


@dataclass
class ToolPattern:
    """Detected tool usage pattern"""

    pattern_name: str
    tools_involved: List[str]
    frequency: int
    avg_duration: float
    efficiency_score: float
    optimization_potential: float
    last_seen: datetime
    examples: List[str] = field(default_factory=list)


@dataclass
class OptimizationOpportunity:
    """Specific optimization opportunity"""

    opportunity_type: str
    description: str
    tools_affected: List[str]
    potential_savings: int  # API calls that could be saved
    implementation_effort: str  # Low, Medium, High
    priority_score: float
    specific_recommendations: List[str] = field(default_factory=list)


class ToolPatternAnalyzer:
    """
    Main analyzer for tool usage patterns and optimization opportunities.

    Provides comprehensive analysis of tool usage to identify inefficiencies
    and optimization opportunities that can prevent Claude API rate limiting.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize tool pattern analyzer"""
        self.config = config or {}

        # Analysis settings
        self.analysis_window = self.config.get("analysis_window", 3600)  # 1 hour window
        self.pattern_min_frequency = self.config.get("pattern_min_frequency", 3)
        self.efficiency_threshold = self.config.get("efficiency_threshold", 0.7)
        self.max_call_history = self.config.get("max_call_history", 1000)

        # State tracking
        self.tool_calls: deque = deque(maxlen=self.max_call_history)
        self.detected_patterns: Dict[str, ToolPattern] = {}
        self.optimization_opportunities: List[OptimizationOpportunity] = []
        self.tool_statistics: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "total_calls": 0,
                "total_response_time": 0.0,
                "success_rate": 1.0,
                "avg_response_time": 0.0,
                "last_used": None,
                "call_frequency": 0.0,  # calls per minute
                "efficiency_level": EfficiencyLevel.OPTIMAL,
            }
        )

        # Pattern detection
        self.sequence_patterns: Dict[str, int] = defaultdict(int)
        self.temporal_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self.parameter_patterns: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Analysis results cache
        self.last_analysis_time: Optional[datetime] = None
        self.cached_analysis: Optional[Dict[str, Any]] = None
        self.cache_ttl = 300  # 5 minutes

        logger.info("Tool pattern analyzer initialized")

    def _create_tool_call_record(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        response_time: float,
        success: bool,
        error_message: Optional[str],
        session_id: str,
    ) -> ToolCall:
        """Create a ToolCall record with classification and cost estimation.

        Creates the record, classifies the call type, and estimates API cost.
        Issue #620.
        """
        tool_call = ToolCall(
            tool_name=tool_name,
            call_time=datetime.now(),
            parameters=parameters.copy(),
            response_time=response_time,
            success=success,
            error_message=error_message,
            session_id=session_id or "default",
            sequence_position=len(self.tool_calls),
        )
        tool_call.call_type = self._classify_tool_call(tool_name, parameters)
        tool_call.api_cost = self._estimate_api_cost(tool_name, parameters)
        return tool_call

    def _process_tool_call(self, tool_call: ToolCall) -> None:
        """Process a tool call by updating statistics and triggering analysis.

        Updates call history, statistics, pattern tracking, and triggers analysis.
        Issue #620.
        """
        self.tool_calls.append(tool_call)
        self._update_tool_statistics(tool_call)
        self._update_pattern_tracking(tool_call)
        if len(self.tool_calls) % 10 == 0:
            asyncio.create_task(self._analyze_patterns())

    def record_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        response_time: float,
        success: bool,
        error_message: Optional[str] = None,
        session_id: str = "",
    ) -> None:
        """Record a tool call for pattern analysis.

        Args:
            tool_name: Name of the tool that was called
            parameters: Parameters passed to the tool
            response_time: Time taken for the tool to respond
            success: Whether the tool call was successful
            error_message: Error message if tool call failed
            session_id: Session identifier for grouping related calls
        """
        try:
            tool_call = self._create_tool_call_record(
                tool_name, parameters, response_time, success, error_message, session_id
            )
            self._process_tool_call(tool_call)
            logger.debug("Recorded tool call: %s (%.2fs)", tool_name, response_time)
        except Exception as e:
            logger.error("Error recording tool call: %s", e)

    def _classify_tool_call(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> ToolCallType:
        """Classify tool call type based on tool name and parameters"""
        tool_name_lower = tool_name.lower()

        # Read operations (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in READ_KEYWORDS):
            return ToolCallType.READ_OPERATION

        # Write operations (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in WRITE_KEYWORDS):
            return ToolCallType.WRITE_OPERATION

        # Search operations (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in SEARCH_KEYWORDS):
            return ToolCallType.SEARCH_OPERATION

        # Execution (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in EXECUTION_KEYWORDS):
            return ToolCallType.EXECUTION

        # Communication tools (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in COMMUNICATION_KEYWORDS):
            return ToolCallType.COMMUNICATION

        # Analysis tools (O(1) lookup - Issue #326)
        if any(keyword in tool_name_lower for keyword in ANALYSIS_KEYWORDS):
            return ToolCallType.ANALYSIS

        # Default to navigation
        return ToolCallType.NAVIGATION

    def _estimate_api_cost(self, tool_name: str, parameters: Dict[str, Any]) -> int:
        """Estimate API cost of tool call on a 1-10 scale"""
        base_cost = 1

        # High cost tools (O(1) lookup - Issue #326)
        if any(keyword in tool_name.lower() for keyword in COMMUNICATION_KEYWORDS):
            base_cost = 8

        # Medium-high cost tools (O(1) lookup - Issue #326)
        elif any(
            keyword in tool_name.lower()
            for keyword in WRITE_KEYWORDS | EXECUTION_KEYWORDS
        ):
            base_cost = 6

        # Medium cost tools (O(1) lookup - Issue #326)
        elif any(
            keyword in tool_name.lower()
            for keyword in SEARCH_KEYWORDS | ANALYSIS_KEYWORDS
        ):
            base_cost = 4

        # Low cost tools (O(1) lookup - Issue #326)
        elif any(keyword in tool_name.lower() for keyword in READ_KEYWORDS):
            base_cost = 2

        # Adjust based on parameters
        if isinstance(parameters, dict):
            # Large file operations cost more (O(1) lookup - Issue #326)
            if "file_path" in parameters and isinstance(parameters["file_path"], str):
                if any(
                    path in parameters["file_path"] for path in LARGE_PATH_INDICATORS
                ):
                    base_cost += 1

            # Complex operations cost more
            if len(parameters) > 5:
                base_cost += 1

            # Recursive or batch operations cost more (O(1) lookup - Issue #326)
            if any(key in parameters for key in BATCH_PARAMETER_KEYS):
                base_cost += 2

        return min(10, base_cost)

    def _update_tool_statistics(self, tool_call: ToolCall) -> None:
        """Update statistics for the tool"""
        stats = self.tool_statistics[tool_call.tool_name]

        # Update counters
        stats["total_calls"] += 1
        stats["total_response_time"] += tool_call.response_time
        stats["last_used"] = tool_call.call_time

        # Update averages
        stats["avg_response_time"] = stats["total_response_time"] / stats["total_calls"]

        # Update success rate
        if tool_call.success:
            stats["success_rate"] = (
                (stats["success_rate"] * (stats["total_calls"] - 1)) + 1.0
            ) / stats["total_calls"]
        else:
            stats["success_rate"] = (
                stats["success_rate"] * (stats["total_calls"] - 1)
            ) / stats["total_calls"]

        # Calculate call frequency (calls per minute)
        recent_calls = [
            call
            for call in self.tool_calls
            if call.tool_name == tool_call.tool_name
            and (tool_call.call_time - call.call_time).seconds < 300
        ]  # Last 5 minutes
        stats["call_frequency"] = len(recent_calls) / 5.0

        # Determine efficiency level
        stats["efficiency_level"] = self._calculate_efficiency_level(stats)

    def _calculate_efficiency_level(self, stats: Dict[str, Any]) -> EfficiencyLevel:
        """Calculate efficiency level based on tool statistics"""
        # Score components (0-1 scale)
        response_time_score = max(
            0, 1 - (stats["avg_response_time"] / 5.0)
        )  # 5s as poor threshold
        success_rate_score = stats["success_rate"]
        frequency_score = max(
            0, 1 - (stats["call_frequency"] / 10.0)
        )  # 10 calls/min as excessive

        # Weighted combination
        efficiency_score = (
            response_time_score * 0.4 + success_rate_score * 0.4 + frequency_score * 0.2
        )

        # Map to efficiency levels
        if efficiency_score >= 0.9:
            return EfficiencyLevel.OPTIMAL
        elif efficiency_score >= 0.75:
            return EfficiencyLevel.GOOD
        elif efficiency_score >= 0.5:
            return EfficiencyLevel.MODERATE
        elif efficiency_score >= 0.25:
            return EfficiencyLevel.POOR
        else:
            return EfficiencyLevel.CRITICAL

    def _update_pattern_tracking(self, tool_call: ToolCall) -> None:
        """Update pattern tracking data"""
        # Sequence pattern tracking
        if len(self.tool_calls) >= 2:
            prev_call = self.tool_calls[-2]
            sequence = f"{prev_call.tool_name}->{tool_call.tool_name}"
            self.sequence_patterns[sequence] += 1

        # Temporal pattern tracking
        self.temporal_patterns[tool_call.tool_name].append(tool_call.call_time)

        # Parameter pattern tracking
        if isinstance(tool_call.parameters, dict):
            for key, value in tool_call.parameters.items():
                if isinstance(value, _JSON_PRIMITIVE_TYPES):  # Issue #380
                    self.parameter_patterns[tool_call.tool_name][f"{key}:{value}"] += 1

    async def _analyze_patterns(self) -> None:
        """Analyze current tool usage patterns"""
        try:
            # Clear previous analysis
            self.detected_patterns.clear()
            self.optimization_opportunities.clear()

            # Detect sequence patterns
            await self._detect_sequence_patterns()

            # Detect repetitive patterns
            await self._detect_repetitive_patterns()

            # Detect inefficient patterns
            await self._detect_inefficient_patterns()

            # Identify optimization opportunities
            await self._identify_optimization_opportunities()

            # Cache analysis results
            self.last_analysis_time = datetime.now()
            self.cached_analysis = self._build_analysis_summary()

            logger.info(
                "Pattern analysis complete. Found %d patterns and %d optimization opportunities",
                len(self.detected_patterns),
                len(self.optimization_opportunities),
            )

        except Exception as e:
            logger.error("Error during pattern analysis: %s", e)

    async def _detect_sequence_patterns(self) -> None:
        """Detect common tool call sequences"""
        # Find frequent sequences
        frequent_sequences = {
            seq: count
            for seq, count in self.sequence_patterns.items()
            if count >= self.pattern_min_frequency
        }

        for sequence, frequency in frequent_sequences.items():
            tools = sequence.split("->")

            # Calculate efficiency metrics
            sequence_calls = []
            for i in range(len(self.tool_calls) - 1):
                if (
                    self.tool_calls[i].tool_name == tools[0]
                    and self.tool_calls[i + 1].tool_name == tools[1]
                ):
                    sequence_calls.extend([self.tool_calls[i], self.tool_calls[i + 1]])

            if sequence_calls:
                avg_duration = statistics.mean(
                    call.response_time for call in sequence_calls
                )
                success_rate = sum(1 for call in sequence_calls if call.success) / len(
                    sequence_calls
                )
                efficiency_score = success_rate * (1 / max(1, avg_duration))

                pattern = ToolPattern(
                    pattern_name=f"Sequence: {sequence}",
                    tools_involved=tools,
                    frequency=frequency,
                    avg_duration=avg_duration,
                    efficiency_score=efficiency_score,
                    optimization_potential=self._calculate_pattern_optimization_potential(
                        sequence_calls
                    ),
                    last_seen=max(call.call_time for call in sequence_calls),
                    examples=[
                        f"{calls[0].tool_name} -> {calls[1].tool_name}"
                        for calls in zip(sequence_calls[::2], sequence_calls[1::2])
                    ][:3],
                )

                self.detected_patterns[f"sequence_{sequence}"] = pattern

    async def _detect_repetitive_patterns(self) -> None:
        """Detect repetitive tool usage patterns"""
        # Group calls by tool and analyze repetition
        tool_groups = defaultdict(list)
        for call in self.tool_calls:
            tool_groups[call.tool_name].append(call)

        for tool_name, calls in tool_groups.items():
            if len(calls) >= self.pattern_min_frequency:
                # Check for rapid repetition
                rapid_calls = []
                for i in range(len(calls) - 1):
                    time_diff = (
                        calls[i + 1].call_time - calls[i].call_time
                    ).total_seconds()
                    if time_diff < 5:  # Less than 5 seconds apart
                        rapid_calls.extend([calls[i], calls[i + 1]])

                if len(rapid_calls) >= 4:  # At least 2 rapid sequences
                    avg_duration = statistics.mean(
                        call.response_time for call in rapid_calls
                    )
                    efficiency_score = 1 / max(
                        1, len(rapid_calls) / 10
                    )  # Penalty for excessive repetition

                    pattern = ToolPattern(
                        pattern_name=f"Repetitive: {tool_name}",
                        tools_involved=[tool_name],
                        frequency=len(rapid_calls),
                        avg_duration=avg_duration,
                        efficiency_score=efficiency_score,
                        optimization_potential=0.8,  # High potential due to repetition
                        last_seen=max(call.call_time for call in rapid_calls),
                        examples=[
                            f"Rapid {tool_name} calls"
                            for _ in range(min(3, len(rapid_calls) // 2))
                        ],
                    )

                    self.detected_patterns[f"repetitive_{tool_name}"] = pattern

    async def _detect_inefficient_patterns(self) -> None:
        """Detect inefficient tool usage patterns"""
        # Analyze tool combinations that could be optimized
        recent_calls = [
            call
            for call in self.tool_calls
            if (datetime.now() - call.call_time).seconds < self.analysis_window
        ]

        # Look for Read -> Write -> Read patterns (inefficient)
        for i in range(len(recent_calls) - 2):
            if (
                recent_calls[i].call_type == ToolCallType.READ_OPERATION
                and recent_calls[i + 1].call_type == ToolCallType.WRITE_OPERATION
                and recent_calls[i + 2].call_type == ToolCallType.READ_OPERATION
            ):
                # Check if reading same file
                if recent_calls[i].parameters.get("file_path") == recent_calls[
                    i + 2
                ].parameters.get("file_path"):
                    pattern = ToolPattern(
                        pattern_name="Inefficient Read-Write-Read",
                        tools_involved=[
                            recent_calls[i].tool_name,
                            recent_calls[i + 1].tool_name,
                            recent_calls[i + 2].tool_name,
                        ],
                        frequency=1,
                        avg_duration=sum(
                            call.response_time for call in recent_calls[i : i + 3]
                        ),
                        efficiency_score=0.3,  # Low efficiency
                        optimization_potential=0.9,  # High optimization potential
                        last_seen=recent_calls[i + 2].call_time,
                        examples=[
                            f"Read {recent_calls[i].parameters.get('file_path', 'file')} -> Write -> Read again"
                        ],
                    )

                    self.detected_patterns[f"inefficient_rwr_{i}"] = pattern

    def _calculate_pattern_optimization_potential(self, calls: List[ToolCall]) -> float:
        """Calculate optimization potential for a pattern"""
        if not calls:
            return 0.0

        # Factors that increase optimization potential
        avg_response_time = statistics.mean(call.response_time for call in calls)
        error_rate = 1 - (sum(1 for call in calls if call.success) / len(calls))
        frequency_score = min(1.0, len(calls) / 20)  # Normalize frequency
        cost_score = statistics.mean(call.api_cost for call in calls) / 10

        # Weighted combination
        optimization_potential = (
            (avg_response_time / 5.0) * 0.3  # Response time impact
            + error_rate * 0.3  # Error rate impact
            + frequency_score * 0.2  # Frequency impact
            + cost_score * 0.2  # API cost impact
        )

        return min(1.0, optimization_potential)

    async def _identify_optimization_opportunities(self) -> None:
        """Identify specific optimization opportunities (Issue #665: refactored)."""
        self._check_batching_opportunity()
        self._check_caching_opportunity()
        self._check_sequence_optimization()
        self._check_todowrite_optimization()

    def _check_batching_opportunity(self) -> None:
        """Check for batching optimization opportunity (Issue #665: extracted helper)."""
        similar_operations = self._find_similar_operations()
        if similar_operations:
            self.optimization_opportunities.append(
                OptimizationOpportunity(
                    opportunity_type="batching",
                    description="Batch similar operations to reduce API calls",
                    tools_affected=list(similar_operations.keys()),
                    potential_savings=sum(
                        len(ops) - 1 for ops in similar_operations.values()
                    ),
                    implementation_effort="Medium",
                    priority_score=0.8,
                    specific_recommendations=[
                        f"Batch {len(ops)} {tool} operations"
                        for tool, ops in similar_operations.items()
                    ],
                )
            )

    def _check_caching_opportunity(self) -> None:
        """Check for caching optimization opportunity (Issue #665: extracted helper)."""
        frequent_reads = self._find_frequent_reads()
        if frequent_reads:
            self.optimization_opportunities.append(
                OptimizationOpportunity(
                    opportunity_type="caching",
                    description="Cache frequently read files to reduce redundant operations",
                    tools_affected=["Read", "Glob", "List"],
                    potential_savings=len(frequent_reads),
                    implementation_effort="Low",
                    priority_score=0.6,
                    specific_recommendations=[
                        f"Cache {file_path} (read {count} times)"
                        for file_path, count in frequent_reads.items()
                    ],
                )
            )

    def _check_sequence_optimization(self) -> None:
        """Check for sequence optimization opportunity (Issue #665: extracted helper)."""
        inefficient_sequences = self._find_inefficient_sequences()
        if inefficient_sequences:
            self.optimization_opportunities.append(
                OptimizationOpportunity(
                    opportunity_type="sequence_optimization",
                    description="Optimize inefficient tool call sequences",
                    tools_affected=[
                        tool
                        for seq in inefficient_sequences
                        for tool in seq.split("->")
                    ],
                    potential_savings=len(inefficient_sequences) * 2,
                    implementation_effort="High",
                    priority_score=0.9,
                    specific_recommendations=[
                        f"Optimize sequence: {seq}" for seq in inefficient_sequences
                    ],
                )
            )

    def _check_todowrite_optimization(self) -> None:
        """Check for TodoWrite optimization opportunity (Issue #665: extracted helper)."""
        todowrite_calls = [
            call for call in self.tool_calls if "todo" in call.tool_name.lower()
        ]
        if len(todowrite_calls) > 10:
            self.optimization_opportunities.append(
                OptimizationOpportunity(
                    opportunity_type="todowrite_optimization",
                    description="Reduce TodoWrite call frequency through batching",
                    tools_affected=["TodoWrite"],
                    potential_savings=len(todowrite_calls) // 2,
                    implementation_effort="Low",
                    priority_score=0.95,
                    specific_recommendations=[
                        "Enable TodoWrite batching and consolidation",
                        "Use pending todo queue instead of immediate writes",
                        "Implement similarity-based deduplication",
                    ],
                )
            )

    def _find_similar_operations(self) -> Dict[str, List[ToolCall]]:
        """Find operations that could be batched together"""
        similar_ops = defaultdict(list)

        # Group by tool and similar parameters (O(1) lookup - Issue #326)
        for call in self.tool_calls:
            if call.call_type in BATCHABLE_CALL_TYPES:
                # Group by tool name and operation type
                key = f"{call.tool_name}_{call.call_type.value}"
                similar_ops[key].append(call)

        # Filter to only groups with multiple operations
        return {key: ops for key, ops in similar_ops.items() if len(ops) > 2}

    def _find_frequent_reads(self) -> Dict[str, int]:
        """Find frequently read files that could benefit from caching"""
        file_reads = defaultdict(int)

        for call in self.tool_calls:
            if (
                call.call_type == ToolCallType.READ_OPERATION
                and "file_path" in call.parameters
            ):
                file_path = call.parameters["file_path"]
                file_reads[file_path] += 1

        # Return files read more than 2 times
        return {path: count for path, count in file_reads.items() if count > 2}

    def _find_inefficient_sequences(self) -> List[str]:
        """Find inefficient tool call sequences"""
        inefficient = []

        for sequence, count in self.sequence_patterns.items():
            if count >= 3:  # Frequent sequence
                tools = sequence.split("->")

                # Check for inefficient patterns
                if (
                    len(tools) == 2
                    and tools[0] in _FILE_READING_TOOLS
                    and tools[1] in _FILE_READING_TOOLS
                ):
                    inefficient.append(sequence)

        return inefficient

    def _build_analysis_summary(self) -> Dict[str, Any]:
        """Build comprehensive analysis summary"""
        return {
            "analysis_timestamp": datetime.now().isoformat(),
            "total_tool_calls": len(self.tool_calls),
            "analysis_window_hours": self.analysis_window / 3600,
            "patterns_detected": len(self.detected_patterns),
            "optimization_opportunities": len(self.optimization_opportunities),
            "tool_statistics": {
                name: {
                    "total_calls": stats["total_calls"],
                    "avg_response_time": stats["avg_response_time"],
                    "success_rate": stats["success_rate"],
                    "call_frequency": stats["call_frequency"],
                    "efficiency_level": stats["efficiency_level"].value,
                }
                for name, stats in self.tool_statistics.items()
            },
            "top_patterns": sorted(
                [
                    {"name": pattern.pattern_name, "score": pattern.efficiency_score}
                    for pattern in self.detected_patterns.values()
                ],
                key=lambda x: x["score"],
                reverse=True,
            )[:5],
            "priority_opportunities": sorted(
                [
                    {
                        "type": opp.opportunity_type,
                        "savings": opp.potential_savings,
                        "priority": opp.priority_score,
                    }
                    for opp in self.optimization_opportunities
                ],
                key=lambda x: x["priority"],
                reverse=True,
            )[:5],
        }

    def get_analysis_results(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get current analysis results"""
        # Check cache validity
        if (
            not force_refresh
            and self.cached_analysis
            and self.last_analysis_time
            and (datetime.now() - self.last_analysis_time).seconds < self.cache_ttl
        ):
            return self.cached_analysis

        # Trigger new analysis
        asyncio.create_task(self._analyze_patterns())

        # Return current cached results or basic stats
        return self.cached_analysis or self._build_basic_stats()

    def _build_basic_stats(self) -> Dict[str, Any]:
        """Build basic statistics when full analysis is not available"""
        return {
            "total_tool_calls": len(self.tool_calls),
            "unique_tools": len(self.tool_statistics),
            "avg_response_time": (
                statistics.mean(call.response_time for call in self.tool_calls)
                if self.tool_calls
                else 0
            ),
            "success_rate": (
                sum(1 for call in self.tool_calls if call.success)
                / len(self.tool_calls)
                if self.tool_calls
                else 1
            ),
            "analysis_pending": True,
        }

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get prioritized optimization recommendations"""
        recommendations = []

        # Sort opportunities by priority
        sorted_opportunities = sorted(
            self.optimization_opportunities,
            key=lambda opp: opp.priority_score,
            reverse=True,
        )

        for opp in sorted_opportunities:
            recommendations.append(
                {
                    "type": opp.opportunity_type,
                    "description": opp.description,
                    "tools_affected": opp.tools_affected,
                    "potential_savings": opp.potential_savings,
                    "implementation_effort": opp.implementation_effort,
                    "priority_score": opp.priority_score,
                    "specific_recommendations": opp.specific_recommendations,
                }
            )

        return recommendations

    def get_tool_efficiency_report(self) -> Dict[str, Any]:
        """Get detailed efficiency report for all tools"""
        efficiency_report = {}

        for tool_name, stats in self.tool_statistics.items():
            efficiency_report[tool_name] = {
                "efficiency_level": stats["efficiency_level"].value,
                "total_calls": stats["total_calls"],
                "avg_response_time": stats["avg_response_time"],
                "success_rate": stats["success_rate"],
                "call_frequency": stats["call_frequency"],
                "last_used": (
                    stats["last_used"].isoformat() if stats["last_used"] else None
                ),
                "recommendations": self._get_tool_recommendations(tool_name, stats),
            }

        return efficiency_report

    def _get_tool_recommendations(
        self, tool_name: str, stats: Dict[str, Any]
    ) -> List[str]:
        """Get specific recommendations for a tool"""
        recommendations = []

        if stats["efficiency_level"] == EfficiencyLevel.CRITICAL:
            recommendations.append(
                "URGENT: Critical inefficiency detected - immediate optimization required"
            )

        if stats["avg_response_time"] > 3.0:
            recommendations.append(
                "High response time - consider caching or alternative approaches"
            )

        if stats["success_rate"] < 0.8:
            recommendations.append(
                "Low success rate - review parameters and error handling"
            )

        if stats["call_frequency"] > 5.0:
            recommendations.append(
                "Very high call frequency - consider batching operations"
            )

        if "todo" in tool_name.lower() and stats["call_frequency"] > 2.0:
            recommendations.append("Enable TodoWrite optimization to reduce API calls")

        return recommendations

    def export_analysis_report(self, file_path: str) -> bool:
        """Export comprehensive analysis report to file"""
        try:
            report = {
                "analysis_metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "analysis_window_hours": self.analysis_window / 3600,
                    "total_tool_calls_analyzed": len(self.tool_calls),
                },
                "tool_statistics": self.tool_statistics,
                "detected_patterns": {
                    name: {
                        "pattern_name": pattern.pattern_name,
                        "tools_involved": pattern.tools_involved,
                        "frequency": pattern.frequency,
                        "avg_duration": pattern.avg_duration,
                        "efficiency_score": pattern.efficiency_score,
                        "optimization_potential": pattern.optimization_potential,
                        "examples": pattern.examples,
                    }
                    for name, pattern in self.detected_patterns.items()
                },
                "optimization_opportunities": [
                    {
                        "type": opp.opportunity_type,
                        "description": opp.description,
                        "tools_affected": opp.tools_affected,
                        "potential_savings": opp.potential_savings,
                        "implementation_effort": opp.implementation_effort,
                        "priority_score": opp.priority_score,
                        "recommendations": opp.specific_recommendations,
                    }
                    for opp in self.optimization_opportunities
                ],
                "efficiency_report": self.get_tool_efficiency_report(),
                "recommendations": self.get_optimization_recommendations(),
            }

            with open(file_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            logger.info("Analysis report exported to %s", file_path)
            return True

        except Exception as e:
            logger.error("Error exporting analysis report: %s", e)
            return False

    def reset_analysis(self) -> None:
        """Reset all analysis data"""
        self.tool_calls.clear()
        self.detected_patterns.clear()
        self.optimization_opportunities.clear()
        self.tool_statistics.clear()
        self.sequence_patterns.clear()
        self.temporal_patterns.clear()
        self.parameter_patterns.clear()
        self.cached_analysis = None
        self.last_analysis_time = None

        logger.info("Tool pattern analyzer reset")


# Global analyzer instance (thread-safe)
import threading

_global_analyzer: Optional[ToolPatternAnalyzer] = None
_global_analyzer_lock = threading.Lock()


def get_tool_pattern_analyzer(
    config: Optional[Dict[str, Any]] = None,
) -> ToolPatternAnalyzer:
    """Get global tool pattern analyzer instance (thread-safe)"""
    global _global_analyzer
    if _global_analyzer is None:
        with _global_analyzer_lock:
            # Double-check after acquiring lock
            if _global_analyzer is None:
                _global_analyzer = ToolPatternAnalyzer(config)
    return _global_analyzer


# Integration functions
def record_tool_usage(
    tool_name: str,
    parameters: Dict[str, Any],
    response_time: float,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    """Convenience function to record tool usage"""
    analyzer = get_tool_pattern_analyzer()
    analyzer.record_tool_call(
        tool_name, parameters, response_time, success, error_message
    )


async def get_optimization_insights() -> Dict[str, Any]:
    """Get comprehensive optimization insights"""
    analyzer = get_tool_pattern_analyzer()

    analysis_results = analyzer.get_analysis_results()
    optimization_recommendations = analyzer.get_optimization_recommendations()
    efficiency_report = analyzer.get_tool_efficiency_report()

    return {
        "analysis_results": analysis_results,
        "optimization_recommendations": optimization_recommendations,
        "efficiency_report": efficiency_report,
        "summary": {
            "total_optimization_opportunities": len(optimization_recommendations),
            "critical_tools": [
                tool
                for tool, stats in efficiency_report.items()
                if stats["efficiency_level"] == "critical"
            ],
            "high_priority_opportunities": [
                opp
                for opp in optimization_recommendations
                if opp["priority_score"] > 0.8
            ],
        },
    }


# Example usage
if __name__ == "__main__":

    async def example():
        """Demonstrate tool pattern analyzer usage with sample data."""
        analyzer = get_tool_pattern_analyzer(
            {"analysis_window": 1800, "pattern_min_frequency": 2}  # 30 minutes
        )

        # Simulate tool calls
        analyzer.record_tool_call("Read", {"file_path": "/test/file.py"}, 0.5, True)
        analyzer.record_tool_call(
            "TodoWrite", {"todos": [{"content": "test"}]}, 1.2, True
        )
        analyzer.record_tool_call(
            "Read", {"file_path": "/test/file.py"}, 0.3, True
        )  # Repeated read

        # Get insights
        insights = await get_optimization_insights()
        print(json.dumps(insights, indent=2, default=str))

    asyncio.run(example())
