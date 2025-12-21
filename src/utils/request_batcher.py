# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Intelligent Request Batching System for Claude API Optimization
Implements sophisticated batching algorithms to reduce API calls and improve efficiency
"""

import asyncio
import hashlib
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class BatchingStrategy(Enum):
    """Available batching strategies for different use cases"""

    TIME_WINDOW = "time_window"  # Batch requests within time window
    SIZE_THRESHOLD = "size_threshold"  # Batch when reaching size limit
    SIMILARITY_BASED = "similarity_based"  # Batch similar requests
    ADAPTIVE = "adaptive"  # Dynamic strategy based on patterns
    PRIORITY_WEIGHTED = "priority_weighted"  # Consider request priorities


class RequestPriority(Enum):
    """Request priority levels for intelligent batching"""

    CRITICAL = 1  # Execute immediately
    HIGH = 2  # Prefer smaller batches
    NORMAL = 3  # Standard batching
    LOW = 4  # Aggressive batching allowed
    BACKGROUND = 5  # Maximum batching tolerance


@dataclass
class BatchableRequest:
    """Represents a request that can be batched with others"""

    id: str
    content: str
    priority: RequestPriority = RequestPriority.NORMAL
    context_type: str = "general"
    timestamp: float = field(default_factory=time.time)
    timeout: float = 30.0
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Generate unique request ID if not provided."""
        if not self.id:
            # Generate unique ID based on content and timestamp
            content_hash = hashlib.md5(self.content.encode(), usedforsecurity=False).hexdigest()[:8]
            self.id = f"req_{content_hash}_{int(self.timestamp * 1000)}"


@dataclass
class BatchResult:
    """Result from processing a batch of requests"""

    batch_id: str
    request_ids: List[str]
    combined_content: str
    response: str
    processing_time: float
    success: bool
    individual_responses: Dict[str, str] = field(default_factory=dict)
    error_message: Optional[str] = None


class RequestSimilarityAnalyzer:
    """Analyzes request similarity for intelligent batching"""

    def __init__(self):
        """Initialize analyzer with default similarity threshold and context weights."""
        self.similarity_threshold = 0.7
        self.context_weights = {
            "file_operations": 0.8,
            "code_analysis": 0.9,
            "general_questions": 0.6,
            "debug_operations": 0.7,
            "documentation": 0.5,
        }

    def calculate_similarity(
        self, req1: BatchableRequest, req2: BatchableRequest
    ) -> float:
        """Calculate similarity score between two requests"""
        try:
            # Context type similarity
            context_similarity = 1.0 if req1.context_type == req2.context_type else 0.3

            # Content similarity (simplified - could use more sophisticated NLP)
            content_similarity = self._calculate_content_similarity(
                req1.content, req2.content
            )

            # Priority compatibility
            priority_diff = abs(req1.priority.value - req2.priority.value)
            priority_similarity = max(0, 1 - (priority_diff / 4))

            # Weighted combination
            context_weight = self.context_weights.get(req1.context_type, 0.6)
            final_similarity = (
                context_similarity * context_weight
                + content_similarity * 0.4
                + priority_similarity * 0.3
            ) / (context_weight + 0.4 + 0.3)

            return min(1.0, final_similarity)

        except Exception as e:
            logger.warning("Error calculating similarity: %s", e)
            return 0.0

    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Simple content similarity calculation"""
        # Convert to sets of words for basic similarity
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def can_batch_together(self, requests: List[BatchableRequest]) -> bool:
        """Determine if requests can be batched together effectively"""
        if len(requests) < 2:
            return True

        # Check priority compatibility
        priorities = [req.priority.value for req in requests]
        if max(priorities) - min(priorities) > 2:
            return False  # Too diverse priorities

        # Check context compatibility
        contexts = set(req.context_type for req in requests)
        if len(contexts) > 2:
            return False  # Too many different contexts

        # Check pairwise similarities
        total_similarity = 0
        pairs = 0
        for i in range(len(requests)):
            for j in range(i + 1, len(requests)):
                similarity = self.calculate_similarity(requests[i], requests[j])
                total_similarity += similarity
                pairs += 1

        avg_similarity = total_similarity / pairs if pairs > 0 else 0
        return avg_similarity >= self.similarity_threshold


class AdaptiveBatchingEngine:
    """Adaptive engine that learns optimal batching patterns"""

    def __init__(self):
        """Initialize adaptive engine with history tracking and learning parameters."""
        self.batch_history: deque = deque(maxlen=1000)
        self.strategy_performance: Dict[BatchingStrategy, List[float]] = defaultdict(
            list
        )
        self.current_strategy = BatchingStrategy.ADAPTIVE
        self.learning_window = 50  # Number of batches to consider for adaptation

    def record_batch_result(self, strategy: BatchingStrategy, result: BatchResult):
        """Record batch processing result for learning"""
        # Calculate performance score (efficiency + success rate)
        efficiency_score = len(result.request_ids) / max(1, result.processing_time)
        success_score = 1.0 if result.success else 0.0
        performance_score = efficiency_score * 0.7 + success_score * 0.3

        self.strategy_performance[strategy].append(performance_score)
        self.batch_history.append(
            {
                "strategy": strategy,
                "performance": performance_score,
                "batch_size": len(result.request_ids),
                "processing_time": result.processing_time,
                "timestamp": time.time(),
            }
        )

        # Adapt strategy if needed
        if len(self.batch_history) >= self.learning_window:
            self._adapt_strategy()

    def _adapt_strategy(self):
        """Adapt batching strategy based on recent performance"""
        if len(self.batch_history) < self.learning_window:
            return

        # Analyze recent performance by strategy
        recent_batches = list(self.batch_history)[-self.learning_window :]
        strategy_scores = defaultdict(list)

        for batch in recent_batches:
            strategy_scores[batch["strategy"]].append(batch["performance"])

        # Find best performing strategy
        best_strategy = None
        best_score = 0

        for strategy, scores in strategy_scores.items():
            if len(scores) >= 5:  # Need minimum samples
                avg_score = sum(scores) / len(scores)
                if avg_score > best_score:
                    best_score = avg_score
                    best_strategy = strategy

        if best_strategy and best_strategy != self.current_strategy:
            logger.info(
                f"Adapting batching strategy from {self.current_strategy} to {best_strategy}"
            )
            self.current_strategy = best_strategy

    def get_recommended_strategy(
        self, current_load: int, queue_size: int
    ) -> BatchingStrategy:
        """Get recommended strategy based on current conditions"""
        if self.current_strategy == BatchingStrategy.ADAPTIVE:
            # Dynamic strategy selection based on current conditions
            if current_load > 10 and queue_size > 20:
                return BatchingStrategy.SIZE_THRESHOLD
            elif queue_size < 5:
                return BatchingStrategy.TIME_WINDOW
            else:
                return BatchingStrategy.SIMILARITY_BASED

        return self.current_strategy


class IntelligentRequestBatcher:
    """Main intelligent request batching system"""

    def __init__(
        self,
        max_batch_size: int = 5,
        time_window: float = 2.0,
        similarity_threshold: float = 0.7,
    ):
        """Initialize request batcher with batch size and timing parameters."""
        self.max_batch_size = max_batch_size
        self.time_window = time_window
        self.similarity_threshold = similarity_threshold

        # Core components
        self.pending_requests: Dict[str, BatchableRequest] = {}
        self.request_queues: Dict[RequestPriority, deque] = {
            priority: deque() for priority in RequestPriority
        }
        self.similarity_analyzer = RequestSimilarityAnalyzer()
        self.adaptive_engine = AdaptiveBatchingEngine()

        # Batch processing
        self.active_batches: Dict[str, asyncio.Task] = {}
        self.batch_results: Dict[str, BatchResult] = {}

        # Lock for thread-safe stats access
        self._stats_lock = asyncio.Lock()
        # Lock for task management (Issue #378)
        self._task_lock = asyncio.Lock()

        # Statistics
        self.stats = {
            "total_requests": 0,
            "total_batches": 0,
            "requests_batched": 0,
            "average_batch_size": 0,
            "efficiency_gain": 0,
            "strategy_usage": defaultdict(int),
        }

        # Background processing
        self._processing_task = None
        self._shutdown = False

    async def start(self):
        """Start the background batch processing.

        Issue #378: Uses lock to prevent race condition when multiple
        coroutines try to start the batcher simultaneously.
        """
        async with self._task_lock:
            if self._processing_task is None:
                self._processing_task = asyncio.create_task(self._batch_processing_loop())
                logger.info("Intelligent request batcher started")

    async def stop(self):
        """Stop the batch processing and wait for completion.

        Issue #378: Uses lock to safely access _processing_task.
        """
        self._shutdown = True
        async with self._task_lock:
            if self._processing_task:
                await self._processing_task
                self._processing_task = None
        logger.info("Intelligent request batcher stopped")

    async def add_request(self, request: BatchableRequest) -> str:
        """Add a request to the batching queue (thread-safe)"""
        async with self._stats_lock:
            self.stats["total_requests"] += 1
        self.pending_requests[request.id] = request
        self.request_queues[request.priority].append(request.id)

        logger.debug("Added request %s with priority %s", request.id, request.priority)
        return request.id

    async def get_result(
        self, request_id: str, timeout: float = TimingConstants.SHORT_TIMEOUT
    ) -> Optional[str]:
        """Get the result for a specific request"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if request is still pending
            if request_id in self.pending_requests:
                await asyncio.sleep(TimingConstants.MICRO_DELAY)
                continue

            # Look for result in completed batches
            for batch_result in self.batch_results.values():
                if request_id in batch_result.individual_responses:
                    return batch_result.individual_responses[request_id]

            await asyncio.sleep(TimingConstants.MICRO_DELAY)

        logger.warning("Timeout waiting for result of request %s", request_id)
        return None

    async def _batch_processing_loop(self):
        """Main batch processing loop"""
        while not self._shutdown:
            try:
                await self._process_pending_requests()
                await asyncio.sleep(TimingConstants.MICRO_DELAY)  # Small delay to prevent CPU spinning
            except Exception as e:
                logger.error("Error in batch processing loop: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)  # Longer delay on error

    async def _process_pending_requests(self):
        """Process pending requests using intelligent batching"""
        if not any(self.request_queues.values()):
            return  # No pending requests

        # Get current strategy
        current_load = len(self.active_batches)
        total_queue_size = sum(len(queue) for queue in self.request_queues.values())
        strategy = self.adaptive_engine.get_recommended_strategy(
            current_load, total_queue_size
        )

        # Process by priority (critical first)
        for priority in RequestPriority:
            if not self.request_queues[priority]:
                continue

            batch = await self._create_batch(priority, strategy)
            if batch:
                await self._execute_batch(batch, strategy)

    async def _create_batch(
        self, priority: RequestPriority, strategy: BatchingStrategy
    ) -> Optional[List[BatchableRequest]]:
        """Create a batch using the specified strategy"""
        queue = self.request_queues[priority]
        if not queue:
            return None

        batch = []

        if strategy == BatchingStrategy.TIME_WINDOW:
            batch = await self._create_time_window_batch(queue)
        elif strategy == BatchingStrategy.SIZE_THRESHOLD:
            batch = await self._create_size_threshold_batch(queue)
        elif strategy == BatchingStrategy.SIMILARITY_BASED:
            batch = await self._create_similarity_batch(queue)
        elif strategy == BatchingStrategy.PRIORITY_WEIGHTED:
            batch = await self._create_priority_weighted_batch(queue)
        else:  # ADAPTIVE or fallback
            batch = await self._create_adaptive_batch(queue)

        if batch:
            async with self._stats_lock:
                self.stats["strategy_usage"][strategy] += 1

        return batch

    async def _create_time_window_batch(self, queue: deque) -> List[BatchableRequest]:
        """Create batch based on time window"""
        batch = []
        current_time = time.time()

        while queue and len(batch) < self.max_batch_size:
            request_id = queue[0]
            request = self.pending_requests.get(request_id)

            if not request:
                queue.popleft()  # Remove invalid request
                continue

            # Check if request is within time window or batch is empty
            if not batch or (current_time - request.timestamp) <= self.time_window:
                queue.popleft()
                batch.append(request)
                del self.pending_requests[request_id]
            else:
                break  # Outside time window

        return batch

    async def _create_size_threshold_batch(
        self, queue: deque
    ) -> List[BatchableRequest]:
        """Create batch when size threshold is reached"""
        if len(queue) < self.max_batch_size:
            return []  # Wait for more requests

        batch = []
        while queue and len(batch) < self.max_batch_size:
            request_id = queue.popleft()
            request = self.pending_requests.get(request_id)

            if request:
                batch.append(request)
                del self.pending_requests[request_id]

        return batch

    async def _create_similarity_batch(self, queue: deque) -> List[BatchableRequest]:
        """Create batch based on request similarity"""
        if not queue:
            return []

        # Start with first request
        first_request_id = queue.popleft()
        first_request = self.pending_requests.get(first_request_id)

        if not first_request:
            return []

        batch = [first_request]
        del self.pending_requests[first_request_id]

        # Find similar requests
        queue_copy = list(queue)
        for request_id in queue_copy:
            if len(batch) >= self.max_batch_size:
                break

            request = self.pending_requests.get(request_id)
            if not request:
                queue.remove(request_id)
                continue

            # Check if similar to existing batch
            test_batch = batch + [request]
            if self.similarity_analyzer.can_batch_together(test_batch):
                batch.append(request)
                queue.remove(request_id)
                del self.pending_requests[request_id]

        return batch

    async def _create_priority_weighted_batch(
        self, queue: deque
    ) -> List[BatchableRequest]:
        """Create batch considering priority weights"""
        batch = []

        # For high priority requests, use smaller batches
        if queue and len(queue) > 0:
            request_id = queue[0]
            request = self.pending_requests.get(request_id)

            if request and request.priority in (
                RequestPriority.CRITICAL,
                RequestPriority.HIGH,
            ):
                # Use smaller batch for high priority
                max_size = min(2, self.max_batch_size)
            else:
                max_size = self.max_batch_size

            while queue and len(batch) < max_size:
                request_id = queue.popleft()
                request = self.pending_requests.get(request_id)

                if request:
                    batch.append(request)
                    del self.pending_requests[request_id]

        return batch

    async def _create_adaptive_batch(self, queue: deque) -> List[BatchableRequest]:
        """Create batch using adaptive strategy"""
        # Combine multiple strategies based on conditions
        if len(queue) >= self.max_batch_size:
            return await self._create_size_threshold_batch(queue)
        elif len(queue) >= 2:
            return await self._create_similarity_batch(queue)
        else:
            return await self._create_time_window_batch(queue)

    async def _execute_batch(
        self, batch: List[BatchableRequest], strategy: BatchingStrategy
    ):
        """Execute a batch of requests"""
        if not batch:
            return

        batch_id = f"batch_{int(time.time() * 1000)}"
        start_time = time.time()

        try:
            # Combine requests into single prompt
            combined_content = self._combine_requests(batch)

            # Execute combined request (placeholder - implement actual API call)
            response = await self._execute_combined_request(combined_content)

            # Parse response back to individual responses
            individual_responses = self._parse_batch_response(batch, response)

            # Create result
            result = BatchResult(
                batch_id=batch_id,
                request_ids=[req.id for req in batch],
                combined_content=combined_content,
                response=response,
                processing_time=time.time() - start_time,
                success=True,
                individual_responses=individual_responses,
            )

            self.batch_results[batch_id] = result
            await self._update_statistics(batch, result)
            self.adaptive_engine.record_batch_result(strategy, result)

            # Execute callbacks
            for request in batch:
                if request.callback:
                    try:
                        response_text = individual_responses.get(request.id, response)
                        await request.callback(response_text)
                    except Exception as e:
                        logger.error("Error executing callback for %s: %s", request.id, e)

            logger.info(
                f"Successfully executed batch {batch_id} with {len(batch)} requests"
            )

        except Exception as e:
            logger.error("Error executing batch %s: %s", batch_id, e)

            # Create error result
            result = BatchResult(
                batch_id=batch_id,
                request_ids=[req.id for req in batch],
                combined_content="",
                response="",
                processing_time=time.time() - start_time,
                success=False,
                error_message=str(e),
            )

            self.batch_results[batch_id] = result
            self.adaptive_engine.record_batch_result(strategy, result)

    def _combine_requests(self, batch: List[BatchableRequest]) -> str:
        """Combine multiple requests into a single prompt"""
        if len(batch) == 1:
            return batch[0].content

        # Build request sections using list + join (O(n)) instead of += (O(n²))
        request_sections = [
            f"Request {i} (ID: {request.id}):\n{request.content}"
            for i, request in enumerate(batch, 1)
        ]
        combined = (
            "I have multiple related requests to process:\n\n"
            + "\n\n".join(request_sections)
            + "\n\nPlease provide responses for each request separately, "
            "clearly indicating which response corresponds to which request ID."
        )

        return combined

    async def _execute_combined_request(self, content: str) -> str:
        """Execute the combined request (placeholder for actual API call)"""
        # This is where you would integrate with your actual Claude API client
        # For now, returning a placeholder response
        await asyncio.sleep(TimingConstants.MICRO_DELAY)  # Simulate API call delay
        return f"Response to combined request: {content[:100]}..."

    def _parse_batch_response(
        self, batch: List[BatchableRequest], response: str
    ) -> Dict[str, str]:
        """Parse batch response back to individual responses"""
        individual_responses = {}

        if len(batch) == 1:
            individual_responses[batch[0].id] = response
        else:
            # Simple parsing - in real implementation, use more sophisticated parsing
            for request in batch:
                # Look for request ID in response
                if request.id in response:
                    # Extract relevant portion (simplified)
                    individual_responses[request.id] = (
                        f"Response for {request.id}: {response[:200]}..."
                    )
                else:
                    individual_responses[request.id] = response

        return individual_responses

    async def _update_statistics(
        self, batch: List[BatchableRequest], result: BatchResult
    ):
        """Update batching statistics (thread-safe)"""
        async with self._stats_lock:
            self.stats["total_batches"] += 1
            self.stats["requests_batched"] += len(batch)

            # Update average batch size
            total_requests = self.stats["requests_batched"]
            total_batches = self.stats["total_batches"]
            self.stats["average_batch_size"] = (
                total_requests / total_batches if total_batches > 0 else 0
            )

            # Calculate efficiency gain (requests processed vs individual API calls)
            individual_calls = self.stats["total_requests"]
            batch_calls = self.stats["total_batches"]
            self.stats["efficiency_gain"] = (
                (individual_calls - batch_calls) / individual_calls
                if individual_calls > 0
                else 0
            )

    async def get_statistics(self) -> Dict[str, Any]:
        """Get current batching statistics (thread-safe)"""
        async with self._stats_lock:
            stats_copy = dict(self.stats)
            # Deep copy strategy_usage since it's a defaultdict
            stats_copy["strategy_usage"] = dict(self.stats["strategy_usage"])

        return {
            **stats_copy,
            "pending_requests": len(self.pending_requests),
            "active_batches": len(self.active_batches),
            "queue_sizes": {
                priority.name: len(queue)
                for priority, queue in self.request_queues.items()
            },
            "current_strategy": self.adaptive_engine.current_strategy.name,
        }


# Convenience functions for easy integration
async def create_batcher(
    max_batch_size: int = 5, time_window: float = 2.0
) -> IntelligentRequestBatcher:
    """Create and start an intelligent request batcher"""
    batcher = IntelligentRequestBatcher(max_batch_size, time_window)
    await batcher.start()
    return batcher


async def batch_request(
    batcher: IntelligentRequestBatcher,
    content: str,
    priority: RequestPriority = RequestPriority.NORMAL,
    context_type: str = "general",
    timeout: float = 30.0,
) -> Optional[str]:
    """Submit a request for batching and wait for result"""
    request = BatchableRequest(
        id="",  # Will be auto-generated
        content=content,
        priority=priority,
        context_type=context_type,
        timeout=timeout,
    )

    request_id = await batcher.add_request(request)
    return await batcher.get_result(request_id, timeout)


# Example usage
async def main():
    """Example usage of the intelligent request batcher"""
    batcher = await create_batcher(max_batch_size=3, time_window=1.0)

    try:
        # Submit multiple requests
        requests = [
            "Analyze this code snippet: def hello(): print('world')",
            "Check for syntax errors in: print('test'",
            "Explain this function: lambda x: x * 2",
            "Review this Python code: class Test: pass",
        ]

        # Submit requests with different priorities
        tasks = []
        for i, content in enumerate(requests):
            priority = RequestPriority.HIGH if i == 0 else RequestPriority.NORMAL
            task = batch_request(batcher, content, priority, "code_analysis")
            tasks.append(task)

        # Wait for all results
        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            logger.debug("Request %s result: %s", i+1, result)

        # Print statistics
        logger.debug("\nBatching Statistics:")
        stats = await batcher.get_statistics()
        for key, value in stats.items():
            logger.debug("  %s: %s", key, value)

    finally:
        await batcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
