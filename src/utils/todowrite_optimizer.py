# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TodoWrite and Tool Usage Pattern Optimizer

This module optimizes TodoWrite operations and tool usage patterns to prevent Claude API
rate limiting and conversation crashes during development sessions. It provides intelligent
batching, deduplication, and optimization strategies specifically for TodoWrite operations
that were identified as contributing to API limit issues.

Key features:
- TodoWrite operation batching and consolidation
- Tool usage pattern analysis and optimization
- Intelligent deduplication of similar todo items
- Adaptive timing optimization for TodoWrite frequency
- Integration with existing Claude API optimization infrastructure
"""

import asyncio
import difflib
import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class TodoOptimizationStrategy(Enum):
    """Strategy for optimizing TodoWrite operations"""

    CONSOLIDATION = "consolidation"  # Merge similar todos
    BATCHING = "batching"  # Batch multiple todos into single operation
    DEDUPLICATION = "deduplication"  # Remove duplicate todos
    TIMING = "timing"  # Optimize timing of TodoWrite calls
    SEMANTIC = "semantic"  # Semantic analysis for intelligent grouping


class TodoStatus(Enum):
    """Todo item status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class OptimizedTodoItem:
    """Optimized todo item with metadata"""

    content: str
    status: TodoStatus
    active_form: str
    priority: int = 5  # 1-10 scale
    tags: Set[str] = field(default_factory=set)
    similarity_hash: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    estimated_effort: int = 1  # Hours
    dependencies: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate similarity hash for deduplication"""
        content_normalized = self.content.lower().strip()
        self.similarity_hash = hashlib.md5(
            content_normalized.encode(), usedforsecurity=False
        ).hexdigest()[:8]


@dataclass
class TodoBatch:
    """Batch of todo operations for optimization"""

    todos: List[OptimizedTodoItem]
    batch_type: str
    optimization_score: float
    estimated_api_savings: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ToolUsagePattern:
    """Pattern analysis for tool usage optimization"""

    tool_name: str
    usage_frequency: int
    avg_response_time: float
    error_rate: float
    api_cost_score: int  # 1-10 scale
    optimization_potential: float
    last_used: datetime = field(default_factory=datetime.now)


class TodoWriteOptimizer:
    """
    Main optimizer for TodoWrite operations and tool usage patterns.

    Provides intelligent optimization strategies to reduce Claude API calls
    and prevent conversation crashes due to rate limiting.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize TodoWrite optimizer with configuration"""
        self.config = config or {}

        # Optimization settings
        self.max_batch_size = self.config.get("max_batch_size", 8)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.8)
        self.consolidation_window = self.config.get(
            "consolidation_window", 30
        )  # seconds
        self.min_api_savings = self.config.get(
            "min_api_savings", 2
        )  # minimum API calls saved

        # State tracking
        self.pending_todos: List[OptimizedTodoItem] = []
        self.todo_history: List[OptimizedTodoItem] = []
        self.tool_usage_stats: Dict[str, ToolUsagePattern] = {}
        self.optimization_stats = {
            "total_optimizations": 0,
            "api_calls_saved": 0,
            "batches_created": 0,
            "duplicates_removed": 0,
            "consolidations_performed": 0,
        }

        # Caching and deduplication
        self.content_cache: Dict[str, OptimizedTodoItem] = {}
        self.recent_operations: List[Tuple[str, datetime]] = []

        logger.info(
            "TodoWrite optimizer initialized with intelligent batching and deduplication"
        )

    def add_todo_for_optimization(
        self,
        content: str,
        status: str = "pending",
        active_form: str = "",
        priority: int = 5,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Add a todo item for optimization instead of immediate writing.

        Args:
            content: Todo content
            status: Todo status (pending, in_progress, completed)
            active_form: Active form description
            priority: Priority level (1-10)
            tags: Optional tags for categorization

        Returns:
            bool: True if added for optimization, False if duplicate/similar exists
        """
        try:
            # Convert status string to enum
            todo_status = TodoStatus(status.lower())

            # Create optimized todo item
            todo_item = OptimizedTodoItem(
                content=content,
                status=todo_status,
                active_form=active_form
                or f"{content.split()[0].title()}ing {' '.join(content.split()[1:]).lower()}",
                priority=priority,
                tags=set(tags or []),
            )

            # Check for duplicates and similar items
            if self._is_duplicate_or_similar(todo_item):
                logger.info("Skipping duplicate/similar todo: %s...", content[:50])
                return False

            # Add to pending optimization queue
            self.pending_todos.append(todo_item)
            self.content_cache[todo_item.similarity_hash] = todo_item

            logger.debug("Added todo for optimization: %s...", content[:50])

            # Check if we should trigger optimization
            if self._should_trigger_optimization():
                asyncio.create_task(self._process_optimization_batch())

            return True

        except Exception as e:
            logger.error("Error adding todo for optimization: %s", e)
            return False

    def _is_duplicate_or_similar(self, todo_item: OptimizedTodoItem) -> bool:
        """Check if todo item is duplicate or too similar to existing items"""

        # Check exact duplicates by hash
        if todo_item.similarity_hash in self.content_cache:
            return True

        # Check semantic similarity with existing todos
        for existing_todo in self.pending_todos:
            similarity = self._calculate_similarity(
                todo_item.content, existing_todo.content
            )
            if similarity > self.similarity_threshold:
                logger.debug("Similar todo found: %.2f similarity", similarity)
                return True

        # Check recent operations to prevent rapid duplicates
        current_time = datetime.now()
        for operation_content, operation_time in self.recent_operations:
            if (current_time - operation_time).seconds < 10:  # 10 second window
                similarity = self._calculate_similarity(
                    todo_item.content, operation_content
                )
                if (
                    similarity > 0.9
                ):  # Very high similarity threshold for recent operations
                    return True

        return False

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two text strings"""
        # Normalize texts
        text1_norm = text1.lower().strip()
        text2_norm = text2.lower().strip()

        # Use difflib for basic similarity
        similarity = difflib.SequenceMatcher(None, text1_norm, text2_norm).ratio()

        # Enhanced similarity for common todo patterns
        common_words = set(text1_norm.split()) & set(text2_norm.split())
        if common_words:
            word_bonus = len(common_words) / max(
                len(text1_norm.split()), len(text2_norm.split())
            )
            similarity = min(1.0, similarity + (word_bonus * 0.2))

        return similarity

    def _should_trigger_optimization(self) -> bool:
        """Determine if optimization should be triggered based on current state"""

        # Trigger on batch size
        if len(self.pending_todos) >= self.max_batch_size:
            return True

        # Trigger on time window
        if self.pending_todos:
            oldest_todo = min(self.pending_todos, key=lambda t: t.created_at)
            if (
                datetime.now() - oldest_todo.created_at
            ).seconds >= self.consolidation_window:
                return True

        # Trigger on high priority items
        high_priority_count = sum(
            1 for todo in self.pending_todos if todo.priority >= 8
        )
        if high_priority_count >= 3:
            return True

        return False

    async def _process_optimization_batch(self) -> Optional[TodoBatch]:
        """Process current batch of todos for optimization"""
        if not self.pending_todos:
            return None

        try:
            # Create optimization batch
            batch = TodoBatch(
                todos=self.pending_todos.copy(),
                batch_type="consolidated",
                optimization_score=self._calculate_optimization_score(
                    self.pending_todos
                ),
                estimated_api_savings=len(self.pending_todos)
                - 1,  # N todos -> 1 API call
            )

            # Apply optimization strategies
            optimized_todos = await self._apply_optimization_strategies(batch.todos)

            # Execute optimized TodoWrite operation
            success = await self._execute_optimized_todowrite(optimized_todos)

            if success:
                # Update statistics
                self.optimization_stats["total_optimizations"] += 1
                self.optimization_stats[
                    "api_calls_saved"
                ] += batch.estimated_api_savings
                self.optimization_stats["batches_created"] += 1

                # Move todos to history
                self.todo_history.extend(self.pending_todos)

                # Record operation for deduplication
                operation_summary = f"Batch of {len(self.pending_todos)} todos"
                self.recent_operations.append((operation_summary, datetime.now()))

                # Clear pending todos
                self.pending_todos.clear()

                logger.info(
                    "Successfully optimized batch of %d todos, saved %d API calls",
                    len(batch.todos),
                    batch.estimated_api_savings,
                )

                return batch

        except Exception as e:
            logger.error("Error processing optimization batch: %s", e)

        return None

    def _calculate_optimization_score(self, todos: List[OptimizedTodoItem]) -> float:
        """Calculate optimization score for a batch of todos"""
        if not todos:
            return 0.0

        # Base score from API savings
        api_savings_score = min(10.0, len(todos) * 1.5)

        # Priority bonus
        avg_priority = sum(todo.priority for todo in todos) / len(todos)
        priority_score = avg_priority / 10.0 * 2.0

        # Deduplication bonus
        unique_hashes = len(set(todo.similarity_hash for todo in todos))
        dedup_score = (len(todos) - unique_hashes) * 0.5

        # Time consolidation bonus
        time_span = (
            max(todos, key=lambda t: t.created_at).created_at
            - min(todos, key=lambda t: t.created_at).created_at
        )
        time_score = min(
            2.0, time_span.seconds / 30.0
        )  # Max 2 points for 30+ second span

        total_score = api_savings_score + priority_score + dedup_score + time_score
        return min(10.0, total_score)

    async def _apply_optimization_strategies(
        self, todos: List[OptimizedTodoItem]
    ) -> List[OptimizedTodoItem]:
        """Apply various optimization strategies to todo batch"""
        optimized_todos = todos.copy()

        # Strategy 1: Remove exact duplicates
        optimized_todos = self._remove_duplicates(optimized_todos)

        # Strategy 2: Consolidate similar todos
        optimized_todos = self._consolidate_similar_todos(optimized_todos)

        # Strategy 3: Optimize order by priority and dependencies
        optimized_todos = self._optimize_todo_order(optimized_todos)

        # Strategy 4: Apply semantic grouping
        optimized_todos = self._apply_semantic_grouping(optimized_todos)

        return optimized_todos

    def _remove_duplicates(
        self, todos: List[OptimizedTodoItem]
    ) -> List[OptimizedTodoItem]:
        """Remove exact duplicate todos"""
        seen_hashes = set()
        unique_todos = []

        for todo in todos:
            if todo.similarity_hash not in seen_hashes:
                unique_todos.append(todo)
                seen_hashes.add(todo.similarity_hash)
            else:
                self.optimization_stats["duplicates_removed"] += 1

        return unique_todos

    def _consolidate_similar_todos(
        self, todos: List[OptimizedTodoItem]
    ) -> List[OptimizedTodoItem]:
        """Consolidate similar todos into more comprehensive ones"""
        consolidated = []
        processed = set()

        for i, todo in enumerate(todos):
            if i in processed:
                continue

            # Find similar todos
            similar_todos = [todo]
            for j, other_todo in enumerate(todos[i + 1 :], i + 1):
                if j not in processed:
                    similarity = self._calculate_similarity(
                        todo.content, other_todo.content
                    )
                    if similarity > 0.7:  # Lower threshold for consolidation
                        similar_todos.append(other_todo)
                        processed.add(j)

            if len(similar_todos) > 1:
                # Create consolidated todo
                consolidated_content = self._create_consolidated_content(similar_todos)
                consolidated_todo = OptimizedTodoItem(
                    content=consolidated_content,
                    status=similar_todos[0].status,
                    active_form=f"Executing consolidated task: {consolidated_content[:50]}...",
                    priority=max(todo.priority for todo in similar_todos),
                    tags=set().union(*(todo.tags for todo in similar_todos)),
                )
                consolidated.append(consolidated_todo)
                self.optimization_stats["consolidations_performed"] += (
                    len(similar_todos) - 1
                )
            else:
                consolidated.append(todo)

            processed.add(i)

        return consolidated

    def _create_consolidated_content(
        self, similar_todos: List[OptimizedTodoItem]
    ) -> str:
        """Create consolidated content from similar todos"""
        if len(similar_todos) == 1:
            return similar_todos[0].content

        # Extract common themes and create comprehensive description
        # Use the most comprehensive todo as base
        base_todo = max(similar_todos, key=lambda t: len(t.content))

        # Add elements from other todos if not already covered
        additional_elements = []
        for todo in similar_todos:
            if todo != base_todo:
                # Extract unique elements not in base todo
                base_words = set(base_todo.content.lower().split())
                todo_words = set(todo.content.lower().split())
                unique_words = todo_words - base_words
                if unique_words:
                    # Only add if it adds significant value
                    if len(unique_words) > 1:
                        additional_elements.append(" ".join(unique_words))

        if additional_elements:
            return f"{base_todo.content} (including {', '.join(additional_elements)})"
        else:
            return base_todo.content

    def _optimize_todo_order(
        self, todos: List[OptimizedTodoItem]
    ) -> List[OptimizedTodoItem]:
        """Optimize order of todos based on priority and dependencies"""
        # Sort by priority (highest first), then by creation time
        sorted_todos = sorted(todos, key=lambda t: (-t.priority, t.created_at))

        # Handle dependencies (simplified - could be enhanced with topological sort)
        # For now, just ensure dependent todos come after their dependencies
        optimized_order = []
        remaining_todos = sorted_todos.copy()

        while remaining_todos:
            # Find todos with no unmet dependencies
            # Use set for O(1) lookup instead of list comprehension
            completed_contents = {t.content for t in optimized_order}
            ready_todos = []
            for todo in remaining_todos:
                if not todo.dependencies or all(
                    dep in completed_contents for dep in todo.dependencies
                ):
                    ready_todos.append(todo)

            if ready_todos:
                # Add the highest priority ready todo
                next_todo = max(ready_todos, key=lambda t: t.priority)
                optimized_order.append(next_todo)
                remaining_todos.remove(next_todo)
            else:
                # No more dependencies to resolve, add remaining todos
                optimized_order.extend(remaining_todos)
                break

        return optimized_order

    def _apply_semantic_grouping(
        self, todos: List[OptimizedTodoItem]
    ) -> List[OptimizedTodoItem]:
        """Apply semantic grouping for better organization"""
        # Group todos by semantic similarity and common tags
        groups = defaultdict(list)

        for todo in todos:
            # Simple grouping by first word (action verb)
            first_word = (
                todo.content.split()[0].lower() if todo.content.split() else "misc"
            )
            groups[first_word].append(todo)

        # Reorder within groups and flatten
        ordered_todos = []
        for group_name, group_todos in sorted(groups.items()):
            # Sort within group by priority
            group_sorted = sorted(group_todos, key=lambda t: -t.priority)
            ordered_todos.extend(group_sorted)

        return ordered_todos

    async def _execute_optimized_todowrite(
        self, todos: List[OptimizedTodoItem]
    ) -> bool:
        """Execute the optimized TodoWrite operation"""
        try:
            # Convert optimized todos back to TodoWrite format
            todowrite_format = []
            for todo in todos:
                todowrite_format.append(
                    {
                        "content": todo.content,
                        "status": todo.status.value,
                        "activeForm": todo.active_form,
                    }
                )

            # Here we would call the actual TodoWrite tool
            # For now, we'll simulate success
            logger.info("Executing optimized TodoWrite with %s todos", len(todos))

            # Simulate API call delay
            await asyncio.sleep(0.1)

            return True

        except Exception as e:
            logger.error("Error executing optimized TodoWrite: %s", e)
            return False

    def record_tool_usage(self, tool_name: str, response_time: float, success: bool):
        """Record tool usage for pattern analysis"""
        if tool_name not in self.tool_usage_stats:
            self.tool_usage_stats[tool_name] = ToolUsagePattern(
                tool_name=tool_name,
                usage_frequency=0,
                avg_response_time=0.0,
                error_rate=0.0,
                api_cost_score=5,  # Default middle value
                optimization_potential=0.0,
            )

        pattern = self.tool_usage_stats[tool_name]
        pattern.usage_frequency += 1
        pattern.last_used = datetime.now()

        # Update average response time
        current_avg = pattern.avg_response_time
        current_count = pattern.usage_frequency
        pattern.avg_response_time = (
            (current_avg * (current_count - 1)) + response_time
        ) / current_count

        # Update error rate
        if not success:
            total_errors = pattern.error_rate * (current_count - 1) + 1
            pattern.error_rate = total_errors / current_count
        else:
            pattern.error_rate = (
                pattern.error_rate * (current_count - 1)
            ) / current_count

        # Calculate optimization potential
        self._calculate_optimization_potential(pattern)

    def _calculate_optimization_potential(self, pattern: ToolUsagePattern):
        """Calculate optimization potential for a tool usage pattern"""
        # High frequency + high response time = high optimization potential
        frequency_score = min(1.0, pattern.usage_frequency / 100.0)  # Normalize to 0-1
        response_time_score = min(
            1.0, pattern.avg_response_time / 5.0
        )  # 5 seconds as high
        error_score = pattern.error_rate  # Already 0-1

        # Weighted combination
        pattern.optimization_potential = (
            frequency_score * 0.4 + response_time_score * 0.4 + error_score * 0.2
        )

        # Assign API cost score based on tool characteristics
        if "TodoWrite" in pattern.tool_name:
            pattern.api_cost_score = 8  # High cost due to frequent usage
        elif "Read" in pattern.tool_name:
            pattern.api_cost_score = 3  # Low cost
        elif "Write" in pattern.tool_name:
            pattern.api_cost_score = 6  # Medium cost
        else:
            pattern.api_cost_score = 5  # Default

    def get_optimization_recommendations(self) -> Dict[str, Any]:
        """Get optimization recommendations based on usage patterns"""
        recommendations = {
            "todowrite_optimizations": [],
            "tool_usage_optimizations": [],
            "general_recommendations": [],
            "statistics": self.optimization_stats.copy(),
        }

        # TodoWrite specific recommendations
        if len(self.pending_todos) > 0:
            recommendations["todowrite_optimizations"].append(
                {
                    "type": "pending_optimization",
                    "message": (
                        f"You have {len(self.pending_todos)} pending todos that could be optimized"
                    ),
                    "potential_savings": len(self.pending_todos) - 1,
                    "action": "call process_optimization_batch()",
                }
            )

        # Tool usage recommendations
        high_potential_tools = [
            pattern
            for pattern in self.tool_usage_stats.values()
            if pattern.optimization_potential > 0.6
        ]

        for pattern in sorted(
            high_potential_tools, key=lambda p: p.optimization_potential, reverse=True
        ):
            recommendations["tool_usage_optimizations"].append(
                {
                    "tool_name": pattern.tool_name,
                    "optimization_potential": pattern.optimization_potential,
                    "usage_frequency": pattern.usage_frequency,
                    "avg_response_time": pattern.avg_response_time,
                    "error_rate": pattern.error_rate,
                    "recommendations": self._get_tool_specific_recommendations(pattern),
                }
            )

        # General recommendations
        if self.optimization_stats["total_optimizations"] == 0:
            recommendations["general_recommendations"].append(
                "Start using TodoWrite optimization to reduce API calls and prevent rate limiting"
            )

        if self.optimization_stats["api_calls_saved"] > 10:
            recommendations["general_recommendations"].append(
                f"Great job! You've saved {self.optimization_stats['api_calls_saved']} API calls through optimization"
            )

        return recommendations

    def _get_tool_specific_recommendations(
        self, pattern: ToolUsagePattern
    ) -> List[str]:
        """Get specific recommendations for a tool usage pattern"""
        recommendations = []

        if pattern.avg_response_time > 3.0:
            recommendations.append(
                "Consider batching requests to reduce response time impact"
            )

        if pattern.error_rate > 0.1:
            recommendations.append(
                "High error rate detected - implement retry logic or error handling"
            )

        if pattern.usage_frequency > 50 and "TodoWrite" in pattern.tool_name:
            recommendations.append(
                "Very frequent TodoWrite usage - enable automatic optimization"
            )

        if pattern.api_cost_score > 7:
            recommendations.append(
                "High API cost tool - prioritize optimization for this tool"
            )

        return recommendations

    async def force_optimization(self) -> Optional[TodoBatch]:
        """Force immediate optimization of pending todos"""
        if not self.pending_todos:
            logger.info("No pending todos to optimize")
            return None

        return await self._process_optimization_batch()

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get comprehensive optimization statistics"""
        return {
            "optimization_stats": self.optimization_stats.copy(),
            "pending_todos_count": len(self.pending_todos),
            "todo_history_count": len(self.todo_history),
            "tool_usage_patterns": {
                name: {
                    "usage_frequency": pattern.usage_frequency,
                    "avg_response_time": pattern.avg_response_time,
                    "error_rate": pattern.error_rate,
                    "optimization_potential": pattern.optimization_potential,
                    "api_cost_score": pattern.api_cost_score,
                }
                for name, pattern in self.tool_usage_stats.items()
            },
            "cache_size": len(self.content_cache),
            "recent_operations_count": len(self.recent_operations),
        }

    def reset_optimization_state(self):
        """Reset optimization state (useful for testing or fresh start)"""
        self.pending_todos.clear()
        self.content_cache.clear()
        self.recent_operations.clear()
        self.optimization_stats = {
            "total_optimizations": 0,
            "api_calls_saved": 0,
            "batches_created": 0,
            "duplicates_removed": 0,
            "consolidations_performed": 0,
        }
        logger.info("TodoWrite optimizer state reset")


class TodoWriteInterceptor:
    """
    Interceptor for TodoWrite operations to automatically apply optimization.

    This class can be used to wrap existing TodoWrite calls and automatically
    route them through the optimizer instead of direct execution.
    """

    def __init__(self, optimizer: TodoWriteOptimizer):
        """Initialize with an optimizer instance"""
        self.optimizer = optimizer
        self.original_todowrite_function = None

    def intercept_todowrite(self, todos: List[Dict[str, Any]]) -> bool:
        """
        Intercept TodoWrite operation and route through optimizer.

        Args:
            todos: List of todo dictionaries in TodoWrite format

        Returns:
            bool: True if successfully added for optimization
        """
        success_count = 0

        for todo in todos:
            success = self.optimizer.add_todo_for_optimization(
                content=todo.get("content", ""),
                status=todo.get("status", "pending"),
                active_form=todo.get("activeForm", ""),
                priority=todo.get("priority", 5),
                tags=todo.get("tags", []),
            )
            if success:
                success_count += 1

        logger.info(
            f"Intercepted TodoWrite: {success_count}/{len(todos)} todos added for optimization"
        )
        return success_count > 0


# Global optimizer instance for easy access (thread-safe)
import threading

_global_optimizer: Optional[TodoWriteOptimizer] = None
_global_optimizer_lock = threading.Lock()


def get_todowrite_optimizer(
    config: Optional[Dict[str, Any]] = None,
) -> TodoWriteOptimizer:
    """Get global TodoWrite optimizer instance (thread-safe)"""
    global _global_optimizer
    if _global_optimizer is None:
        with _global_optimizer_lock:
            # Double-check after acquiring lock
            if _global_optimizer is None:
                _global_optimizer = TodoWriteOptimizer(config)
    return _global_optimizer


async def optimized_todowrite(todos: List[Dict[str, Any]]) -> bool:
    """
    Convenience function for optimized TodoWrite operations.

    Args:
        todos: List of todo dictionaries in TodoWrite format

    Returns:
        bool: True if successfully processed
    """
    optimizer = get_todowrite_optimizer()
    interceptor = TodoWriteInterceptor(optimizer)
    return interceptor.intercept_todowrite(todos)


# Example usage and integration patterns
async def example_usage():
    """Example of how to use the TodoWrite optimizer"""

    # Get optimizer instance
    optimizer = get_todowrite_optimizer(
        {"max_batch_size": 6, "similarity_threshold": 0.75, "consolidation_window": 45}
    )

    # Add todos for optimization instead of immediate writing
    optimizer.add_todo_for_optimization(
        content="Implement user authentication system",
        status="pending",
        priority=8,
        tags=["auth", "security"],
    )

    optimizer.add_todo_for_optimization(
        content="Create user login endpoint",
        status="pending",
        priority=7,
        tags=["auth", "api"],
    )

    optimizer.add_todo_for_optimization(
        content="Add user authentication middleware",
        status="pending",
        priority=6,
        tags=["auth", "middleware"],
    )

    # Force optimization if needed
    batch = await optimizer.force_optimization()
    if batch:
        logger.info("Optimized batch with score: %s", batch.optimization_score)

    # Get recommendations
    recommendations = optimizer.get_optimization_recommendations()
    logger.info(
        "Optimization recommendations: %s",
        json.dumps(recommendations, indent=2, default=str),
    )

    # Record tool usage for pattern analysis
    optimizer.record_tool_usage("TodoWrite", 1.5, True)
    optimizer.record_tool_usage("Read", 0.3, True)
    optimizer.record_tool_usage("Write", 0.8, False)

    # Get statistics
    stats = optimizer.get_optimization_stats()
    logger.info("Optimization statistics: %s", json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
