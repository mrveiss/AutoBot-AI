# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Claude API Integration with Intelligent Request Batching
Integrates the batching system with AutoBot's existing Claude API infrastructure
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from constants.threshold_constants import RetryConfig, TimingConstants

from .conversation_rate_limiter import ConversationRateLimiter
from .payload_optimizer import PayloadOptimizer
from .request_batcher import (
    BatchableRequest,
    IntelligentRequestBatcher,
    RequestPriority,
    create_batcher,
)

# Import our components


logger = logging.getLogger(__name__)


@dataclass
class ClaudeAPIConfig:
    """Configuration for Claude API integration"""

    max_batch_size: int = 4
    time_window: float = 1.5
    enable_batching: bool = True
    enable_rate_limiting: bool = True
    enable_payload_optimization: bool = True
    fallback_to_individual: bool = True
    max_retries: int = RetryConfig.DEFAULT_RETRIES
    base_delay: float = 1.0


class ClaudeAPIBatchManager:
    """Manages Claude API calls with intelligent batching and optimization"""

    def __init__(self, config: ClaudeAPIConfig = None):
        """Initialize batch manager with configuration and tracking state."""
        self.config = config or ClaudeAPIConfig()

        # Core components
        self.batcher: Optional[IntelligentRequestBatcher] = None
        self.rate_limiter = (
            ConversationRateLimiter() if self.config.enable_rate_limiting else None
        )
        self.payload_optimizer = (
            PayloadOptimizer() if self.config.enable_payload_optimization else None
        )

        # Lock for thread-safe access to shared state
        self._lock = asyncio.Lock()

        # State tracking
        self.is_running = False
        self.request_count = 0
        self.batch_count = 0
        self.fallback_count = 0

        # Performance metrics
        self.metrics = {
            "total_requests": 0,
            "batched_requests": 0,
            "individual_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0.0,
            "batch_efficiency": 0.0,
            "rate_limit_hits": 0,
            "payload_optimizations": 0,
        }

    async def start(self):
        """Start the batch manager"""
        if self.is_running:
            return

        if self.config.enable_batching:
            self.batcher = await create_batcher(
                max_batch_size=self.config.max_batch_size,
                time_window=self.config.time_window,
            )

        self.is_running = True
        logger.info("Claude API Batch Manager started")

    async def stop(self):
        """Stop the batch manager"""
        if not self.is_running:
            return

        if self.batcher:
            await self.batcher.stop()
            self.batcher = None

        self.is_running = False
        logger.info("Claude API Batch Manager stopped")

    async def _increment_metric(self, metric_name: str) -> None:
        """Thread-safely increment a metric (Issue #315: extracted)."""
        async with self._lock:
            self.metrics[metric_name] += 1

    async def _try_batched_request(
        self,
        content: str,
        priority: RequestPriority,
        context_type: str,
        timeout: float,
        metadata: Dict[str, Any],
    ) -> str | None:
        """Try to process request with batching (Issue #315: extracted).

        Returns:
            Response string if successful, None if batching failed and fallback needed
        """
        try:
            response = await self._process_with_batching(
                content, priority, context_type, timeout, metadata
            )
            await self._increment_metric("batched_requests")
            return response
        except Exception as e:
            logger.warning("Batching failed, falling back to individual: %s", e)
            if not self.config.fallback_to_individual:
                raise
            return None  # Signal to use fallback

    async def _process_with_fallback(
        self,
        content: str,
        priority: RequestPriority,
        context_type: str,
        timeout: float,
        metadata: Dict[str, Any],
    ) -> str:
        """Process request with batching or fallback (Issue #315: extracted).

        Returns:
            Response string
        """
        # Try batching if appropriate
        if (
            self.config.enable_batching
            and self.batcher
            and self._should_batch_request(priority, context_type)
        ):
            response = await self._try_batched_request(
                content, priority, context_type, timeout, metadata
            )
            if response is not None:
                return response

            # Fallback to individual processing
            response = await self._process_individual_request(content, timeout)
            await self._increment_metric("individual_requests")
            async with self._lock:
                self.fallback_count += 1
            return response

        # Process individually (no batching)
        response = await self._process_individual_request(content, timeout)
        await self._increment_metric("individual_requests")
        return response

    async def _check_and_apply_rate_limit(self) -> bool:
        """Check rate limit and update metrics if exceeded (Issue #315: extracted).

        Returns:
            True if request can proceed, False if rate limited
        """
        if not self.rate_limiter:
            return True

        if await self._check_rate_limit():
            return True

        await self._increment_metric("rate_limit_hits")
        return False

    async def _optimize_payload_if_enabled(self, content: str) -> str:
        """Optimize payload if optimizer is enabled (Issue #315: extracted).

        Returns:
            Optimized content string
        """
        if not self.payload_optimizer:
            return content

        optimization_result = self.payload_optimizer.optimize_payload(content)
        if not optimization_result.optimized:
            return content

        await self._increment_metric("payload_optimizations")
        logger.debug(
            f"Payload optimized: {optimization_result.size_reduction}% reduction"
        )
        return optimization_result.optimized_content

    async def submit_request(
        self,
        content: str,
        priority: RequestPriority = RequestPriority.NORMAL,
        context_type: str = "general",
        timeout: float = 30.0,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Submit a request for processing with batching optimization (thread-safe).

        Issue #315: Refactored to use helper methods for reduced nesting depth.
        """
        if not self.is_running:
            await self.start()

        start_time = time.time()
        await self._increment_metric("total_requests")

        try:
            # Apply rate limiting (uses helper)
            if not await self._check_and_apply_rate_limit():
                raise Exception("Rate limit exceeded")

            # Optimize payload if enabled (uses helper)
            optimized_content = await self._optimize_payload_if_enabled(content)

            # Process request with batching or fallback (uses helper)
            response = await self._process_with_fallback(
                optimized_content, priority, context_type, timeout, metadata or {}
            )

            # Update metrics
            response_time = time.time() - start_time
            await self._update_response_time_metric(response_time)

            # Record successful request for rate limiter
            if self.rate_limiter:
                self.rate_limiter.record_request(len(content))

            return response

        except Exception as e:
            await self._increment_metric("failed_requests")
            logger.error("Request failed: %s", e)
            raise

    async def _check_rate_limit(self) -> bool:
        """Check if request can proceed based on rate limits"""
        if not self.rate_limiter:
            return True

        return self.rate_limiter.can_make_request()

    def _should_batch_request(
        self, priority: RequestPriority, context_type: str
    ) -> bool:
        """Determine if request should be batched"""
        # Critical requests should not be batched
        if priority == RequestPriority.CRITICAL:
            return False

        # Some context types benefit more from batching
        batchable_contexts = {
            "code_analysis",
            "file_operations",
            "documentation",
            "general_questions",
            "debug_operations",
        }

        return context_type in batchable_contexts

    async def _process_with_batching(
        self,
        content: str,
        priority: RequestPriority,
        context_type: str,
        timeout: float,
        metadata: Dict[str, Any],
    ) -> str:
        """Process request using the batching system"""
        request = BatchableRequest(
            id="",  # Auto-generated
            content=content,
            priority=priority,
            context_type=context_type,
            timeout=timeout,
            metadata=metadata or {},
        )

        request_id = await self.batcher.add_request(request)
        result = await self.batcher.get_result(request_id, timeout)

        if result is None:
            raise Exception("Timeout waiting for batched request result")

        return result

    async def _process_individual_request(self, content: str, timeout: float) -> str:
        """Process request individually (fallback method)"""
        # This is where you would integrate with your actual Claude API client
        # For now, simulating the API call

        await asyncio.sleep(0.2)  # Simulate API delay

        # Mock response - replace with actual Claude API integration
        response = f"Mock response to: {content[:50]}..."

        return response

    async def _update_response_time_metric(self, response_time: float):
        """Update average response time metric (thread-safe)"""
        async with self._lock:
            current_avg = self.metrics["average_response_time"]
            total_requests = self.metrics["total_requests"]

            if total_requests == 1:
                self.metrics["average_response_time"] = response_time
            else:
                # Rolling average
                self.metrics["average_response_time"] = (
                    current_avg * (total_requests - 1) + response_time
                ) / total_requests

    async def submit_multiple_requests(
        self, requests: List[Dict[str, Any]], parallel: bool = True
    ) -> List[str]:
        """Submit multiple requests efficiently"""
        if parallel:
            # Submit all requests in parallel
            tasks = []
            for req in requests:
                task = self.submit_request(
                    content=req["content"],
                    priority=req.get("priority", RequestPriority.NORMAL),
                    context_type=req.get("context_type", "general"),
                    timeout=req.get("timeout", 30.0),
                    metadata=req.get("metadata", {}),
                )
                tasks.append(task)

            return await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # Submit requests sequentially
            results = []
            for req in requests:
                result = await self.submit_request(
                    content=req["content"],
                    priority=req.get("priority", RequestPriority.NORMAL),
                    context_type=req.get("context_type", "general"),
                    timeout=req.get("timeout", 30.0),
                    metadata=req.get("metadata", {}),
                )
                results.append(result)

            return results

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics (thread-safe, returns snapshot)"""
        async with self._lock:
            # Copy metrics under lock
            metrics_copy = dict(self.metrics)
            fallback = self.fallback_count
            running = self.is_running

        batch_efficiency = 0.0
        if metrics_copy["total_requests"] > 0:
            batched_ratio = (
                metrics_copy["batched_requests"] / metrics_copy["total_requests"]
            )
            batch_efficiency = batched_ratio * 100

        batcher_stats = {}
        if self.batcher:
            batcher_stats = await self.batcher.get_statistics()

        return {
            **metrics_copy,
            "batch_efficiency": batch_efficiency,
            "fallback_count": fallback,
            "is_running": running,
            "batcher_stats": batcher_stats,
            "rate_limiter_stats": (
                self.rate_limiter.get_usage_statistics() if self.rate_limiter else {}
            ),
        }

    async def reset_metrics(self):
        """Reset all metrics (thread-safe)"""
        async with self._lock:
            self.metrics = {
                "total_requests": 0,
                "batched_requests": 0,
                "individual_requests": 0,
                "failed_requests": 0,
                "average_response_time": 0.0,
                "batch_efficiency": 0.0,
                "rate_limit_hits": 0,
                "payload_optimizations": 0,
            }
            self.fallback_count = 0
        logger.info("Metrics reset")


class ClaudeAPIContextManager:
    """Context manager for Claude API batch processing"""

    def __init__(self, config: ClaudeAPIConfig = None):
        """Initialize context manager with optional configuration."""
        self.manager = ClaudeAPIBatchManager(config)

    async def __aenter__(self):
        """Start the batch manager and return it for context usage."""
        await self.manager.start()
        return self.manager

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop the batch manager when exiting context."""
        await self.manager.stop()


# Convenience functions for easy integration
async def create_claude_api_manager(
    config: ClaudeAPIConfig = None,
) -> ClaudeAPIBatchManager:
    """Create and start a Claude API batch manager"""
    manager = ClaudeAPIBatchManager(config)
    await manager.start()
    return manager


async def batch_claude_request(
    content: str,
    priority: RequestPriority = RequestPriority.NORMAL,
    context_type: str = "general",
    timeout: float = 30.0,
    manager: ClaudeAPIBatchManager = None,
) -> str:
    """Submit a single Claude API request with batching"""
    if manager is None:
        # Create temporary manager
        async with ClaudeAPIContextManager() as temp_manager:
            return await temp_manager.submit_request(
                content, priority, context_type, timeout
            )
    else:
        return await manager.submit_request(content, priority, context_type, timeout)


async def batch_claude_requests(
    requests: List[Dict[str, Any]],
    parallel: bool = True,
    config: ClaudeAPIConfig = None,
) -> List[str]:
    """Submit multiple Claude API requests with batching"""
    async with ClaudeAPIContextManager(config) as manager:
        return await manager.submit_multiple_requests(requests, parallel)


# Integration with AutoBot's existing infrastructure
class AutoBotClaudeAPIAdapter:
    """Adapter to integrate with AutoBot's existing Claude API usage"""

    def __init__(self):
        """Initialize adapter with empty manager and uninitialized state."""
        self.manager: Optional[ClaudeAPIBatchManager] = None
        self._initialized = False

    async def initialize(self, config: ClaudeAPIConfig = None):
        """Initialize the adapter"""
        if not self._initialized:
            self.manager = await create_claude_api_manager(config)
            self._initialized = True

    async def process_chat_request(self, message: str, context: str = "chat") -> str:
        """Process a chat request through the batching system"""
        if not self._initialized:
            await self.initialize()

        return await self.manager.submit_request(
            content=message,
            priority=RequestPriority.NORMAL,
            context_type=context,
            timeout=TimingConstants.SHORT_TIMEOUT,
        )

    async def process_code_analysis(
        self, code: str, analysis_type: str = "general"
    ) -> str:
        """Process code analysis with appropriate batching"""
        if not self._initialized:
            await self.initialize()

        return await self.manager.submit_request(
            content=f"Analyze this code:\n{code}",
            priority=RequestPriority.HIGH,
            context_type="code_analysis",
            timeout=45.0,
        )

    async def process_file_operations(self, operation: str, files: List[str]) -> str:
        """Process file operations with batching optimization"""
        if not self._initialized:
            await self.initialize()

        content = f"Perform {operation} on files: {', '.join(files)}"
        return await self.manager.submit_request(
            content=content,
            priority=RequestPriority.NORMAL,
            context_type="file_operations",
            timeout=TimingConstants.STANDARD_TIMEOUT,
        )

    async def shutdown(self):
        """Shutdown the adapter"""
        if self.manager:
            await self.manager.stop()
            self.manager = None
        self._initialized = False

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics (thread-safe)"""
        if self.manager:
            return await self.manager.get_metrics()
        return {}


# Global adapter instance for AutoBot integration
autobot_claude_adapter = AutoBotClaudeAPIAdapter()


# Example usage and testing
async def main():
    """Example usage of the Claude API integration"""
    config = ClaudeAPIConfig(
        max_batch_size=3,
        time_window=1.0,
        enable_batching=True,
        enable_rate_limiting=True,
        enable_payload_optimization=True,
    )

    async with ClaudeAPIContextManager(config) as manager:
        # Test individual request
        response1 = await manager.submit_request(
            "Explain Python decorators",
            priority=RequestPriority.HIGH,
            context_type="documentation",
        )
        logger.debug("Response 1: %s", response1)

        # Test multiple requests
        requests = [
            {"content": "What is a lambda function?", "context_type": "documentation"},
            {"content": "Explain list comprehensions", "context_type": "documentation"},
            {"content": "How do generators work?", "context_type": "documentation"},
        ]

        responses = await manager.submit_multiple_requests(requests, parallel=True)
        for i, response in enumerate(responses):
            logger.debug("Response %s: %s", i + 2, response)

        # Print metrics
        logger.debug("\nPerformance Metrics:")
        metrics = await manager.get_metrics()
        for key, value in metrics.items():
            logger.debug("  %s: %s", key, value)


if __name__ == "__main__":
    asyncio.run(main())
