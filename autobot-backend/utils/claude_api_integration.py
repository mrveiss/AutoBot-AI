# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Claude API Integration with Intelligent Request Batching

Canonical optimization module for AutoBot's Claude/LLM request path.
Provides rate limiting, payload optimization, intelligent batching,
graceful degradation, TodoWrite optimization, and tool pattern analysis.

Supersedes the now-retired claude_api_optimization_suite.py (#10796).
Wire-in point: initialization/lifespan._init_claude_api_integration()
is called during Phase 2 startup; get_autobot_claude_adapter() is the
production singleton used by LLMService and other callers.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot_config
from constants.threshold_constants import RetryConfig, TimingConstants
from utils.async_initializable import AsyncInitializable

from .conversation_rate_limiter import ConversationRateLimiter
from .graceful_degradation import GracefulDegradationManager
from .payload_optimizer import PayloadOptimizer
from .request_batcher import (
    BatchableRequest,
    IntelligentRequestBatcher,
    RequestPriority,
    create_batcher,
)
from .todowrite_optimizer import get_todowrite_optimizer
from .tool_pattern_analyzer import get_tool_pattern_analyzer

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Optimization mode (folded from retired claude_api_optimization_suite, #10796)
# ---------------------------------------------------------------------------


class OptimizationMode(Enum):
    """Optimization modes that drive automatic rate-limit reconfiguration."""

    CONSERVATIVE = "conservative"  # Light touch; 60 req/min, 2500/hour
    BALANCED = "balanced"  # Default; 50 req/min, 2000/hour
    AGGRESSIVE = "aggressive"  # High-frequency; 30 req/min, 1500/hour
    EMERGENCY = "emergency"  # Recovery; 15 req/min, 800/hour


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


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
    # Optimization-mode and optional component toggles (folded from suite, #10796)
    mode: OptimizationMode = OptimizationMode.BALANCED
    enable_graceful_degradation: bool = True
    enable_todowrite_optimization: bool = True
    enable_pattern_analysis: bool = True
    todowrite_consolidation_window: int = 30
    todowrite_similarity_threshold: float = 0.8
    pattern_analysis_interval: int = 300


@dataclass
class OptimizationMetrics:
    """Snapshot metrics for optimization performance (folded from suite, #10796)."""

    total_requests: int = 0
    batched_requests: int = 0
    individual_requests: int = 0
    failed_requests: int = 0
    rate_limit_hits: int = 0
    payload_optimizations: int = 0
    average_response_time: float = 0.0
    conversation_crashes_prevented: int = 0
    fallback_count: int = 0
    last_reset_time: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# Rate-limit ceilings per mode (folded from suite's _MODE_RATE_LIMITS, #10796)
_MODE_RATE_LIMITS: Dict[OptimizationMode, tuple[int, int]] = {
    OptimizationMode.CONSERVATIVE: (60, 2500),
    OptimizationMode.BALANCED: (50, 2000),
    OptimizationMode.AGGRESSIVE: (30, 1500),
    OptimizationMode.EMERGENCY: (15, 800),
}


# ---------------------------------------------------------------------------
# Core batch-manager
# ---------------------------------------------------------------------------


class ClaudeAPIBatchManager:
    """Manages Claude API calls with intelligent batching and optimization."""

    def __init__(self, config: ClaudeAPIConfig = None):
        """Initialize batch manager with configuration and tracking state."""
        self.config = config or ClaudeAPIConfig()

        # Core components
        self.batcher: IntelligentRequestBatcher | None = None
        self.rate_limiter = ConversationRateLimiter() if self.config.enable_rate_limiting else None
        self.payload_optimizer = PayloadOptimizer() if self.config.enable_payload_optimization else None

        # Optional components (folded from suite, #10796)
        self.degradation_manager = GracefulDegradationManager() if self.config.enable_graceful_degradation else None
        self.todowrite_optimizer = (
            get_todowrite_optimizer(
                {
                    "consolidation_window": self.config.todowrite_consolidation_window,
                    "similarity_threshold": self.config.todowrite_similarity_threshold,
                }
            )
            if self.config.enable_todowrite_optimization
            else None
        )
        self.pattern_analyzer = (
            get_tool_pattern_analyzer({"analysis_window": self.config.pattern_analysis_interval})
            if self.config.enable_pattern_analysis
            else None
        )

        # Lock for thread-safe access to shared state
        self._lock = asyncio.Lock()

        # State
        self.is_running = False
        self.current_mode = self.config.mode
        self._background_tasks: List[asyncio.Task] = []

        # Flat metrics store
        self._metrics = OptimizationMetrics()

    async def start(self):
        """Start the batch manager and optional background analysis tasks."""
        if self.is_running:
            return

        if self.config.enable_batching:
            self.batcher = await create_batcher(
                max_batch_size=self.config.max_batch_size,
                time_window=self.config.time_window,
            )

        if self.config.enable_pattern_analysis and self.pattern_analyzer:
            task = asyncio.create_task(self._background_pattern_analysis())
            self._background_tasks.append(task)

        self.is_running = True
        logger.info(
            "Claude API Batch Manager started in %s mode",
            self.current_mode.value,
        )

    async def stop(self):
        """Stop the batch manager and cancel background tasks."""
        if not self.is_running:
            return

        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        if self.batcher:
            await self.batcher.stop()
            self.batcher = None

        self.is_running = False
        logger.info("Claude API Batch Manager stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _increment_metric(self, field_name: str) -> None:
        """Thread-safely increment a named metric field."""
        async with self._lock:
            setattr(self._metrics, field_name, getattr(self._metrics, field_name) + 1)

    async def _try_batched_request(
        self,
        content: str,
        priority: RequestPriority,
        context_type: str,
        timeout: float,
        metadata: Dict[str, Any],
    ) -> str | None:
        """Try to process request with batching; return None to signal fallback needed."""
        try:
            response = await self._process_with_batching(content, priority, context_type, timeout, metadata)
            await self._increment_metric("batched_requests")
            return response
        except Exception as e:
            logger.warning("Batching failed, falling back to individual: %s", e)
            if not self.config.fallback_to_individual:
                raise
            return None

    async def _process_with_fallback(
        self,
        content: str,
        priority: RequestPriority,
        context_type: str,
        timeout: float,
        metadata: Dict[str, Any],
    ) -> str:
        """Process request with batching or individual fallback."""
        if self.config.enable_batching and self.batcher and self._should_batch_request(priority, context_type):
            response = await self._try_batched_request(content, priority, context_type, timeout, metadata)
            if response is not None:
                return response
            # Fallback to individual
            response = await self._process_individual_request(content, timeout)
            await self._increment_metric("individual_requests")
            async with self._lock:
                self._metrics.fallback_count += 1
            return response

        response = await self._process_individual_request(content, timeout)
        await self._increment_metric("individual_requests")
        return response

    async def _check_and_apply_rate_limit(self) -> bool:
        """Return True if request can proceed; False if rate-limited.

        ``ConversationRateLimiter.can_make_request()`` returns a Dict; the
        ``can_proceed`` key governs whether the request may proceed (#10849).
        """
        if not self.rate_limiter:
            return True
        result = self.rate_limiter.can_make_request()
        if isinstance(result, dict):
            can_proceed = bool(result.get("can_proceed", True))
        else:
            can_proceed = bool(result)
        if can_proceed:
            return True
        await self._increment_metric("rate_limit_hits")
        async with self._lock:
            self._metrics.conversation_crashes_prevented += 1
        return False

    async def _optimize_payload_if_enabled(self, content: str) -> str:
        """Return payload-optimized content string when optimizer is enabled."""
        if not self.payload_optimizer:
            return content
        optimization_result = self.payload_optimizer.optimize_payload(content)
        if not optimization_result.optimized:
            return content
        await self._increment_metric("payload_optimizations")
        logger.debug("Payload optimized: %s%% reduction", optimization_result.size_reduction)
        return optimization_result.optimized_content

    # ------------------------------------------------------------------
    # Public request API
    # ------------------------------------------------------------------

    async def submit_request(
        self,
        content: str,
        priority: RequestPriority = RequestPriority.NORMAL,
        context_type: str = "general",
        timeout: float = _ssot_config.timeout.default_request,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """Submit a request for processing with batching optimization (thread-safe)."""
        if not self.is_running:
            await self.start()

        start_time = time.time()
        await self._increment_metric("total_requests")

        try:
            if not await self._check_and_apply_rate_limit():
                # Attempt graceful degradation before hard-failing
                if self.degradation_manager:
                    fallback = await self.degradation_manager.handle_request(content, {"type": context_type})
                    if fallback.success:
                        return str(fallback.response)
                raise Exception("Rate limit exceeded")

            optimized_content = await self._optimize_payload_if_enabled(content)

            response = await self._process_with_fallback(
                optimized_content, priority, context_type, timeout, metadata or {}
            )

            response_time = time.time() - start_time
            await self._update_response_time_metric(response_time)

            if self.pattern_analyzer:
                self.pattern_analyzer.record_tool_call(
                    tool_name=context_type,
                    parameters={"content_len": len(content)},
                    response_time=response_time,
                    success=True,
                )

            if self.rate_limiter:
                self.rate_limiter.record_request(len(content))

            return response

        except Exception as e:
            await self._increment_metric("failed_requests")
            if self.pattern_analyzer:
                self.pattern_analyzer.record_tool_call(
                    tool_name=context_type,
                    parameters={"content_len": len(content)},
                    response_time=time.time() - start_time,
                    success=False,
                    error_message=str(e),
                )
            logger.error("Request failed: %s", e)
            raise

    async def submit_todowrite(self, todos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Optimize and submit a TodoWrite batch (folded from suite, #10796)."""
        if self.todowrite_optimizer:
            count = 0
            for todo in todos:
                ok = self.todowrite_optimizer.add_todo_for_optimization(
                    content=todo.get("content", ""),
                    status=todo.get("status", "pending"),
                    active_form=todo.get("activeForm", ""),
                    priority=todo.get("priority", 5),
                )
                if ok:
                    count += 1
            if count:
                return {"status": "optimized", "todos_queued": count}

        # Fallback: submit as plain text
        content = "\n".join(t.get("content", "") for t in todos)
        await self.submit_request(content, context_type="todowrite")
        return {"status": "submitted", "todos_queued": len(todos)}

    def _should_batch_request(self, priority: RequestPriority, context_type: str) -> bool:
        """Return True when request type is suitable for batching."""
        if priority == RequestPriority.CRITICAL:
            return False
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
        """Process request using the batching system."""
        request = BatchableRequest(
            id="",
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
        """Process request individually (integration point for real Claude API client)."""
        await asyncio.sleep(TimingConstants.DEBOUNCE_INTERVAL_S)
        return f"Mock response to: {content[:50]}..."

    async def _update_response_time_metric(self, response_time: float):
        """Update rolling-average response time metric (thread-safe)."""
        async with self._lock:
            total = self._metrics.total_requests
            cur = self._metrics.average_response_time
            self._metrics.average_response_time = (
                response_time if total <= 1 else (cur * (total - 1) + response_time) / total
            )

    # ------------------------------------------------------------------
    # Mode management (folded from suite, #10796)
    # ------------------------------------------------------------------

    async def set_mode(self, mode: OptimizationMode) -> None:
        """Dynamically switch optimization mode and reconfigure rate limits."""
        async with self._lock:
            if mode == self.current_mode:
                return
            self.current_mode = mode

        if self.rate_limiter and mode in _MODE_RATE_LIMITS:
            per_minute, per_hour = _MODE_RATE_LIMITS[mode]
            self.rate_limiter.requests_per_minute = per_minute
            self.rate_limiter.requests_per_hour = per_hour

        logger.info("Optimization mode set to %s", mode.value)

    # ------------------------------------------------------------------
    # Metrics and status
    # ------------------------------------------------------------------

    async def get_metrics(self) -> Dict[str, Any]:
        """Return a thread-safe snapshot of all metrics."""
        async with self._lock:
            m = self._metrics
            return {
                "total_requests": m.total_requests,
                "batched_requests": m.batched_requests,
                "individual_requests": m.individual_requests,
                "failed_requests": m.failed_requests,
                "rate_limit_hits": m.rate_limit_hits,
                "payload_optimizations": m.payload_optimizations,
                "average_response_time": m.average_response_time,
                "conversation_crashes_prevented": m.conversation_crashes_prevented,
                "fallback_count": m.fallback_count,
                "batch_efficiency": ((m.batched_requests / max(1, m.total_requests)) * 100),
                "is_running": self.is_running,
                "current_mode": self.current_mode.value,
            }

    async def get_optimization_status(self) -> Dict[str, Any]:
        """Return combined metrics with component health status."""
        metrics = await self.get_metrics()

        component_status: Dict[str, Any] = {}
        if self.rate_limiter:
            component_status["rate_limiter"] = self.rate_limiter.get_usage_statistics()
        if self.todowrite_optimizer:
            component_status["todowrite_optimizer"] = self.todowrite_optimizer.get_optimization_stats()
        if self.pattern_analyzer:
            component_status["pattern_analyzer"] = self.pattern_analyzer.get_analysis_results()
        if self.batcher:
            component_status["batcher"] = await self.batcher.get_statistics()

        return {
            "metrics": metrics,
            "component_status": component_status,
            "config": {
                "batching_enabled": self.config.enable_batching,
                "rate_limiting_enabled": self.config.enable_rate_limiting,
                "payload_optimization_enabled": self.config.enable_payload_optimization,
                "graceful_degradation_enabled": self.config.enable_graceful_degradation,
                "todowrite_optimization_enabled": self.config.enable_todowrite_optimization,
                "pattern_analysis_enabled": self.config.enable_pattern_analysis,
            },
        }

    async def reset_metrics(self):
        """Reset all metrics (thread-safe)."""
        async with self._lock:
            self._metrics = OptimizationMetrics()
        logger.info("Metrics reset")

    # ------------------------------------------------------------------
    # Background tasks (folded from suite, #10796)
    # ------------------------------------------------------------------

    async def _background_pattern_analysis(self):
        """Periodic background task that checks for critical optimization opportunities."""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.pattern_analysis_interval)
                if not self.pattern_analyzer:
                    continue
                self.pattern_analyzer.get_analysis_results(force_refresh=True)
                recommendations = self.pattern_analyzer.get_optimization_recommendations()
                critical = [r for r in recommendations if r.get("priority_score", 0) > 0.8]
                if len(critical) > 3:
                    await self.set_mode(OptimizationMode.AGGRESSIVE)
            except Exception as e:
                logger.error("Background pattern analysis error: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_TIMEOUT)

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    async def submit_multiple_requests(self, requests: List[Dict[str, Any]], parallel: bool = True) -> List[str]:
        """Submit multiple requests efficiently."""
        if parallel:
            tasks = [
                self.submit_request(
                    content=req["content"],
                    priority=req.get("priority", RequestPriority.NORMAL),
                    context_type=req.get("context_type", "general"),
                    timeout=req.get("timeout", 30.0),
                    metadata=req.get("metadata", {}),
                )
                for req in requests
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)

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


# ---------------------------------------------------------------------------
# Context manager wrapper
# ---------------------------------------------------------------------------


class ClaudeAPIContextManager:
    """Async context manager for Claude API batch processing."""

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


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------


async def create_claude_api_manager(config: ClaudeAPIConfig = None) -> ClaudeAPIBatchManager:
    """Create and start a Claude API batch manager."""
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
    """Submit a single Claude API request with batching."""
    if manager is None:
        async with ClaudeAPIContextManager() as temp_manager:
            return await temp_manager.submit_request(content, priority, context_type, timeout)
    return await manager.submit_request(content, priority, context_type, timeout)


async def batch_claude_requests(
    requests: List[Dict[str, Any]],
    parallel: bool = True,
    config: ClaudeAPIConfig = None,
) -> List[str]:
    """Submit multiple Claude API requests with batching."""
    async with ClaudeAPIContextManager(config) as manager:
        return await manager.submit_multiple_requests(requests, parallel)


# ---------------------------------------------------------------------------
# AutoBot production adapter (singleton, AsyncInitializable)
# ---------------------------------------------------------------------------


class AutoBotClaudeAPIAdapter(AsyncInitializable):
    """
    Adapter to integrate with AutoBot's existing Claude API usage.

    Issue #3390: Migrated to AsyncInitializable lazy-init pattern.
    Issue #10796: Module promoted to canonical optimization module; wired into
    backend startup via initialization/lifespan._init_claude_api_integration().
    The module-level singleton is created lazily via get_autobot_claude_adapter().
    """

    _instance: "AutoBotClaudeAPIAdapter" | None = None

    def __init__(self):
        """Initialize adapter with empty manager; real init deferred to _initialize_impl."""
        super().__init__(component_name="autobot_claude_adapter")
        self.manager: ClaudeAPIBatchManager | None = None
        self._adapter_config: ClaudeAPIConfig | None = None

    async def _initialize_impl(self) -> bool:
        """Create the Claude API batch manager on first use."""
        self.manager = await create_claude_api_manager(self._adapter_config)
        return True

    async def _cleanup_impl(self) -> None:
        """Shut down the batch manager on initialization failure."""
        if self.manager:
            await self.manager.stop()
            self.manager = None

    async def process_chat_request(self, message: str, context: str = "chat") -> str:
        """Process a chat request through the batching system."""
        await self.ensure_initialized()
        return await self.manager.submit_request(
            content=message,
            priority=RequestPriority.NORMAL,
            context_type=context,
            timeout=TimingConstants.SHORT_TIMEOUT,
        )

    async def process_code_analysis(self, code: str, analysis_type: str = "general") -> str:
        """Process code analysis with appropriate batching."""
        await self.ensure_initialized()
        return await self.manager.submit_request(
            content=f"Analyze this code:\n{code}",
            priority=RequestPriority.HIGH,
            context_type="code_analysis",
            timeout=45.0,
        )

    async def process_file_operations(self, operation: str, files: List[str]) -> str:
        """Process file operations with batching optimization."""
        await self.ensure_initialized()
        content = f"Perform {operation} on files: {', '.join(files)}"
        return await self.manager.submit_request(
            content=content,
            priority=RequestPriority.NORMAL,
            context_type="file_operations",
            timeout=TimingConstants.STANDARD_TIMEOUT,
        )

    async def submit_todowrite(self, todos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Optimize a TodoWrite batch via the manager (folded from suite, #10796)."""
        await self.ensure_initialized()
        return await self.manager.submit_todowrite(todos)

    async def optimize_for_send(
        self,
        content: str,
        context_type: str = "general",
    ) -> str:
        """Apply rate-limit check and payload optimization before an outbound send.

        Called by provider implementations (e.g. AnthropicProvider) before
        dispatching to the upstream API.  Returns the (possibly optimized)
        content string.  When rate-limited and graceful degradation is not
        available, logs a warning and returns the original content so the
        caller's normal send path proceeds (fail-safe, not fail-closed).

        Issue #10849: wires live outbound Claude requests through the adapter's
        optimization pipeline (rate-limiter, payload optimizer, metric recording).
        """
        await self.ensure_initialized()
        if not self.manager or not self.manager.is_running:
            return content
        await self.manager._increment_metric("total_requests")
        if not await self.manager._check_and_apply_rate_limit():
            if self.manager.degradation_manager:
                try:
                    fallback = await self.manager.degradation_manager.handle_request(content, {"type": context_type})
                    if fallback.success:
                        logger.debug(
                            "Claude adapter: graceful degradation applied for context=%s",
                            context_type,
                        )
                except Exception as _deg_err:
                    logger.debug("Degradation manager error (ignored): %s", _deg_err)
            logger.warning(
                "Claude adapter: rate limit exceeded for context=%s; " "proceeding with original payload (fail-safe)",
                context_type,
            )
            return content
        optimized = await self.manager._optimize_payload_if_enabled(content)
        if self.manager.rate_limiter:
            self.manager.rate_limiter.record_request(len(content))
        return optimized

    async def record_send_result(
        self,
        context_type: str,
        content_len: int,
        response_time: float,
        success: bool,
        error_message: str = "",
    ) -> None:
        """Record post-send metrics and pattern analysis for an outbound call.

        Called by provider implementations after the upstream API responds.
        Issue #10849: feeds live send results into the adapter's metrics and
        the tool-pattern analyzer so optimization recommendations reflect real
        traffic.
        """
        if not self.manager or not self.manager.is_running:
            return
        if success:
            await self.manager._increment_metric("individual_requests")
            await self.manager._update_response_time_metric(response_time)
        else:
            await self.manager._increment_metric("failed_requests")
        if self.manager.pattern_analyzer:
            self.manager.pattern_analyzer.record_tool_call(
                tool_name=context_type,
                parameters={"content_len": content_len},
                response_time=response_time,
                success=success,
                error_message=error_message if not success else "",
            )

    async def shutdown(self):
        """Shutdown the adapter."""
        if self.manager:
            await self.manager.stop()
            self.manager = None
        self._initialized = False

    async def get_performance_stats(self) -> Dict[str, Any]:
        """Return combined performance statistics and optimization status."""
        if self.manager:
            return await self.manager.get_optimization_status()
        return {}

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None


# Lock that serialises singleton creation in get_autobot_claude_adapter().
_claude_adapter_lock = asyncio.Lock()


async def get_autobot_claude_adapter(
    adapter_config: ClaudeAPIConfig | None = None,
) -> "AutoBotClaudeAPIAdapter":
    """Get and lazily initialize the global AutoBotClaudeAPIAdapter singleton."""
    async with _claude_adapter_lock:
        if AutoBotClaudeAPIAdapter._instance is None:
            AutoBotClaudeAPIAdapter._instance = AutoBotClaudeAPIAdapter()
            AutoBotClaudeAPIAdapter._instance._adapter_config = adapter_config
    await AutoBotClaudeAPIAdapter._instance.initialize()
    return AutoBotClaudeAPIAdapter._instance


# Backward-compatible module-level name; instance is NOT initialized until first await.
# Use `await get_autobot_claude_adapter()` for production code.
autobot_claude_adapter: "AutoBotClaudeAPIAdapter" | None = None


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------


async def main():
    """Example usage of the Claude API integration."""
    config = ClaudeAPIConfig(
        max_batch_size=3,
        time_window=1.0,
        enable_batching=True,
        enable_rate_limiting=True,
        enable_payload_optimization=True,
    )

    async with ClaudeAPIContextManager(config) as manager:
        response1 = await manager.submit_request(
            "Explain Python decorators",
            priority=RequestPriority.HIGH,
            context_type="documentation",
        )
        logger.debug("Response 1: %s", response1)

        requests = [
            {"content": "What is a lambda function?", "context_type": "documentation"},
            {"content": "Explain list comprehensions", "context_type": "documentation"},
            {"content": "How do generators work?", "context_type": "documentation"},
        ]
        responses = await manager.submit_multiple_requests(requests, parallel=True)
        for i, response in enumerate(responses):
            logger.debug("Response %s: %s", i + 2, response)

        metrics = await manager.get_metrics()
        logger.debug("Metrics: %s", metrics)


if __name__ == "__main__":
    run_or_schedule(main())
