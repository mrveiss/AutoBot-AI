# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Graceful Degradation Strategies for Claude API
Implements comprehensive fallback mechanisms to maintain AutoBot functionality during API issues
"""

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    """Levels of service degradation"""

    NORMAL = 0  # Full functionality
    REDUCED = 1  # Limited features, cached responses
    MINIMAL = 2  # Basic cached responses only
    EMERGENCY = 3  # Static fallbacks and error messages
    OFFLINE = 4  # Complete service unavailable


class ServiceHealth(Enum):
    """Service health status indicators"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNSTABLE = "unstable"
    FAILING = "failing"
    DOWN = "down"


@dataclass
class FallbackResponse:
    """Represents a fallback response with metadata"""

    content: str
    source: str = "fallback"
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    cached: bool = False
    degradation_level: DegradationLevel = DegradationLevel.REDUCED
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceStatus:
    """Current service status and health metrics"""

    health: ServiceHealth
    degradation_level: DegradationLevel
    last_success: Optional[float] = None
    last_failure: Optional[float] = None
    consecutive_failures: int = 0
    error_rate: float = 0.0
    response_time: float = 0.0
    uptime_percentage: float = 100.0


class FallbackStrategy(ABC):
    """Abstract base class for fallback strategies"""

    @abstractmethod
    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Check if this strategy can handle the request"""

    @abstractmethod
    async def generate_response(
        self, request: str, context: Dict[str, Any]
    ) -> FallbackResponse:
        """Generate a fallback response"""

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get the name of this strategy"""


class CachedResponseStrategy(FallbackStrategy):
    """Strategy that uses cached responses from previous successful calls"""

    def __init__(self, cache_dir: str = "data/cache/claude_responses"):
        """Initialize cached response strategy with cache directory and settings."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_cache_age = 24 * 60 * 60  # 24 hours
        self.similarity_threshold = 0.7

    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Check if we have a cached response for similar request"""
        cached_response = await self._find_cached_response(request)
        return cached_response is not None

    async def generate_response(
        self, request: str, context: Dict[str, Any]
    ) -> FallbackResponse:
        """Return cached response if available"""
        cached_response = await self._find_cached_response(request)

        if cached_response:
            return FallbackResponse(
                content=cached_response["content"],
                source="cached_response",
                confidence=cached_response.get("confidence", 0.8),
                cached=True,
                degradation_level=DegradationLevel.REDUCED,
                metadata={"original_timestamp": cached_response.get("timestamp")},
            )

        return FallbackResponse(
            content=(
                "I apologize, but I'm currently unable to process your request due to service issues."
                "Please try again later."
            ),
            source="cached_response_fallback",
            confidence=0.1,
            degradation_level=DegradationLevel.MINIMAL,
        )

    def get_strategy_name(self) -> str:
        """Return the strategy identifier name."""
        return "cached_response"

    async def cache_response(
        self, request: str, response: str, confidence: float = 1.0
    ):
        """Cache a successful response for future fallback use"""
        cache_key = self._generate_cache_key(request)
        cache_file = self.cache_dir / f"{cache_key}.json"

        cache_data = {
            "request": request,
            "content": response,
            "confidence": confidence,
            "timestamp": time.time(),
        }

        try:
            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(cache_data))
            logger.debug("Cached response for key: %s", cache_key)
        except OSError as e:
            logger.warning("Failed to write cache file %s: %s", cache_file, e)
        except Exception as e:
            logger.warning("Failed to serialize cache response: %s", e)

    async def _find_cached_response(self, request: str) -> Optional[Dict[str, Any]]:
        """Find a cached response for the request"""
        cache_key = self._generate_cache_key(request)
        cache_file = self.cache_dir / f"{cache_key}.json"

        # Try exact match first
        # Issue #358 - avoid blocking
        if await asyncio.to_thread(cache_file.exists):
            try:
                async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cached_data = json.loads(content)

                # Check if cache is still valid
                age = time.time() - cached_data.get("timestamp", 0)
                if age <= self.max_cache_age:
                    return cached_data
            except OSError as e:
                logger.warning("Failed to read cache file %s: %s", cache_file, e)
            except Exception as e:
                logger.warning("Error parsing cache file %s: %s", cache_file, e)

        # Try similarity-based matching
        return await self._find_similar_cached_response(request)

    async def _find_similar_cached_response(
        self, request: str
    ) -> Optional[Dict[str, Any]]:
        """Find a cached response for similar request"""
        request_words = set(request.lower().split())
        best_match = None
        best_similarity = 0

        try:
            # Issue #358 - use lambda for proper glob() execution in thread
            cache_files = await asyncio.to_thread(lambda: list(self.cache_dir.glob("*.json")))
            for cache_file in cache_files:
                try:
                    async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        cached_data = json.loads(content)

                    # Check cache age
                    age = time.time() - cached_data.get("timestamp", 0)
                    if age > self.max_cache_age:
                        continue

                    # Calculate similarity
                    cached_words = set(cached_data["request"].lower().split())
                    if not request_words or not cached_words:
                        continue

                    intersection = request_words.intersection(cached_words)
                    union = request_words.union(cached_words)
                    similarity = len(intersection) / len(union)

                    if (
                        similarity > best_similarity
                        and similarity >= self.similarity_threshold
                    ):
                        best_similarity = similarity
                        best_match = cached_data
                        best_match["confidence"] = similarity

                except OSError as e:
                    logger.warning("Failed to read cache file %s: %s", cache_file, e)
                except Exception as e:
                    logger.warning("Error parsing cache file %s: %s", cache_file, e)

        except Exception as e:
            logger.warning("Error scanning cache directory: %s", e)

        return best_match

    def _generate_cache_key(self, request: str) -> str:
        """Generate a cache key for the request"""
        return hashlib.md5(request.encode(), usedforsecurity=False).hexdigest()


class TemplateResponseStrategy(FallbackStrategy):
    """Strategy that uses predefined templates for common request types"""

    def __init__(self):
        """Initialize template response strategy with predefined templates."""
        self.templates = {
            "code_analysis": {
                "patterns": ["analyze", "review", "check", "code", "function", "class"],
                "template": (
                    "I'm currently unable to perform detailed code analysis due to "
                    "service issues. For code review, please check for:\n"
                    "- Syntax errors\n- Logic issues\n- Performance concerns\n"
                    "- Security vulnerabilities\nPlease try again later for detailed analysis."
                ),
            },
            "explanation": {
                "patterns": ["explain", "what is", "how does", "define", "describe"],
                "template": (
                    "I'm currently experiencing service issues and cannot provide "
                    "detailed explanations. Please refer to documentation or try "
                    "again later for comprehensive information."
                ),
            },
            "troubleshooting": {
                "patterns": ["error", "problem", "issue", "bug", "fix", "troubleshoot"],
                "template": (
                    "I'm currently unable to provide detailed troubleshooting due to "
                    "service issues. Common steps to try:\n"
                    "1. Check logs for error messages\n2. Verify configuration settings\n"
                    "3. Restart the service\n4. Check network connectivity\n"
                    "Please try again later for specific guidance."
                ),
            },
            "file_operations": {
                "patterns": ["file", "read", "write", "create", "directory", "path"],
                "template": (
                    "I'm currently unable to perform file operations due to service "
                    "issues. Please use standard file management tools or try again later."
                ),
            },
            "general": {
                "patterns": [],
                "template": (
                    "I'm currently experiencing service issues and unable to provide "
                    "detailed responses. Please try again later."
                ),
            },
        }

    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Template strategy can handle any request"""
        return True

    async def generate_response(
        self, request: str, context: Dict[str, Any]
    ) -> FallbackResponse:
        """Generate template-based response"""
        request_lower = request.lower()
        best_template = self.templates["general"]
        best_score = 0

        for template_name, template_data in self.templates.items():
            if template_name == "general":
                continue

            score = sum(
                1 for pattern in template_data["patterns"] if pattern in request_lower
            )
            if score > best_score:
                best_score = score
                best_template = template_data

        confidence = min(0.6, 0.2 + (best_score * 0.1))

        return FallbackResponse(
            content=best_template["template"],
            source="template_response",
            confidence=confidence,
            degradation_level=DegradationLevel.MINIMAL,
            metadata={"template_type": template_name, "pattern_matches": best_score},
        )

    def get_strategy_name(self) -> str:
        """Return the strategy identifier name."""
        return "template_response"


class StaticResponseStrategy(FallbackStrategy):
    """Strategy that provides static emergency responses"""

    def __init__(self):
        """Initialize static response strategy with emergency response templates."""
        self.static_responses = {
            "service_unavailable": (
                "AutoBot is currently experiencing technical difficulties. Please try again later."
            ),
            "maintenance": (
                "AutoBot is currently undergoing maintenance. Service will be restored shortly."
            ),
            "emergency": (
                "AutoBot services are temporarily unavailable. Please contact support if this issue persists."
            ),
        }

    async def can_handle(self, request: str, context: Dict[str, Any]) -> bool:
        """Static strategy can always handle requests"""
        return True

    async def generate_response(
        self, request: str, context: Dict[str, Any]
    ) -> FallbackResponse:
        """Generate static emergency response"""
        response_type = context.get("emergency_type", "service_unavailable")
        content = self.static_responses.get(
            response_type, self.static_responses["emergency"]
        )

        return FallbackResponse(
            content=content,
            source="static_response",
            confidence=0.1,
            degradation_level=DegradationLevel.EMERGENCY,
            metadata={"response_type": response_type},
        )

    def get_strategy_name(self) -> str:
        """Return the strategy identifier name."""
        return "static_response"


class GracefulDegradationManager:
    """Main manager for graceful degradation strategies (thread-safe)"""

    def __init__(self, cache_dir: str = "data/cache/claude_responses"):
        """Initialize degradation manager with fallback strategies and monitoring."""
        # Initialize strategies in order of preference
        self.strategies: List[FallbackStrategy] = [
            CachedResponseStrategy(cache_dir),
            TemplateResponseStrategy(),
            StaticResponseStrategy(),
        ]

        # Lock for thread-safe access to shared state
        self._lock = asyncio.Lock()

        # Service monitoring
        self.service_status = ServiceStatus(
            health=ServiceHealth.HEALTHY, degradation_level=DegradationLevel.NORMAL
        )

        # Failure tracking
        self.failure_history: List[float] = []
        self.max_failure_history = 100
        self.health_check_interval = 60  # seconds
        self.failure_threshold = 5  # consecutive failures to trigger degradation

        # Performance metrics
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "degraded_responses": 0,
            "fallback_usage": {
                strategy.get_strategy_name(): 0 for strategy in self.strategies
            },
            "average_response_time": 0.0,
            "uptime_start": time.time(),
        }

        # Background monitoring
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown = False

    async def start_monitoring(self):
        """Start background service monitoring"""
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("Graceful degradation monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring"""
        self._shutdown = True
        if self._monitoring_task:
            await self._monitoring_task
            self._monitoring_task = None
        logger.info("Graceful degradation monitoring stopped")

    async def handle_request(
        self, request: str, context: Dict[str, Any] = None
    ) -> FallbackResponse:
        """Handle a request with graceful degradation (thread-safe)"""
        context = context or {}
        async with self._lock:
            self.metrics["total_requests"] += 1
            degradation_level = self.service_status.degradation_level
        start_time = time.time()

        try:
            # Try to determine appropriate degradation strategy
            if degradation_level == DegradationLevel.NORMAL:
                # In normal operation, this would attempt the actual API call
                # For this implementation, we'll simulate occasional failures
                if await self._should_simulate_failure():
                    raise Exception("Simulated API failure")

                # Simulate successful response
                await asyncio.sleep(0.1)
                response = f"Normal response to: {request[:50]}..."

                # Cache successful response
                if isinstance(self.strategies[0], CachedResponseStrategy):
                    await self.strategies[0].cache_response(request, response)

                async with self._lock:
                    self.metrics["successful_requests"] += 1
                await self._record_success()

                return FallbackResponse(
                    content=response,
                    source="primary_service",
                    confidence=1.0,
                    degradation_level=DegradationLevel.NORMAL,
                )

            else:
                # Service is degraded, use fallback strategies
                return await self._use_fallback_strategy(request, context)

        except Exception as e:
            logger.warning("Primary service failed: %s", e)
            await self._record_failure()
            return await self._use_fallback_strategy(request, context)

        finally:
            response_time = time.time() - start_time
            await self._update_response_time_metric(response_time)

    async def _use_fallback_strategy(
        self, request: str, context: Dict[str, Any]
    ) -> FallbackResponse:
        """Use fallback strategies to handle the request (thread-safe)"""
        async with self._lock:
            self.metrics["degraded_responses"] += 1

        for strategy in self.strategies:
            try:
                if await strategy.can_handle(request, context):
                    response = await strategy.generate_response(request, context)
                    async with self._lock:
                        self.metrics["fallback_usage"][strategy.get_strategy_name()] += 1
                    logger.info(
                        f"Used fallback strategy: {strategy.get_strategy_name()}"
                    )
                    return response
            except Exception as e:
                logger.warning(
                    f"Fallback strategy {strategy.get_strategy_name()} failed: {e}"
                )

        # Ultimate fallback
        return FallbackResponse(
            content="AutoBot is currently unavailable. Please try again later.",
            source="ultimate_fallback",
            confidence=0.0,
            degradation_level=DegradationLevel.OFFLINE,
        )

    async def _should_simulate_failure(self) -> bool:
        """Simulate occasional failures for testing"""
        import random

        return random.random() < 0.1  # 10% failure rate for simulation

    async def _record_success(self):
        """Record a successful request (thread-safe)"""
        async with self._lock:
            self.service_status.last_success = time.time()
            self.service_status.consecutive_failures = 0
        await self._update_service_health()

    async def _record_failure(self):
        """Record a failed request (thread-safe)"""
        current_time = time.time()
        async with self._lock:
            self.service_status.last_failure = current_time
            self.service_status.consecutive_failures += 1
            self.failure_history.append(current_time)

            # Trim failure history
            if len(self.failure_history) > self.max_failure_history:
                self.failure_history.pop(0)

        await self._update_service_health()

    def _determine_health_status(
        self, consecutive_failures: int, error_rate: float
    ) -> tuple[ServiceHealth, DegradationLevel]:
        """Determine health and degradation level (Issue #315 - extracted helper)."""
        # Ordered thresholds from healthiest to most degraded
        thresholds = [
            (0, 5, ServiceHealth.HEALTHY, DegradationLevel.NORMAL),
            (3, 15, ServiceHealth.DEGRADED, DegradationLevel.REDUCED),
            (5, 30, ServiceHealth.UNSTABLE, DegradationLevel.MINIMAL),
            (10, 100, ServiceHealth.FAILING, DegradationLevel.EMERGENCY),
        ]

        for max_failures, max_error, health, level in thresholds:
            if consecutive_failures < max_failures and error_rate < max_error:
                return health, level
            if consecutive_failures == 0 and error_rate < max_error:
                return health, level

        return ServiceHealth.DOWN, DegradationLevel.OFFLINE

    async def _update_service_health(self):
        """Update service health status and degradation level (Issue #315 - refactored)."""
        async with self._lock:
            consecutive_failures = self.service_status.consecutive_failures
            current_time = time.time()
            recent_failures = [f for f in self.failure_history if current_time - f <= 300]
            total_requests = self.metrics["total_requests"]
            error_rate = len(recent_failures) / max(1, total_requests) * 100

            health, level = self._determine_health_status(consecutive_failures, error_rate)
            self.service_status.health = health
            self.service_status.degradation_level = level
            self.service_status.error_rate = error_rate
            health_val = health.value
            level_name = level.name

        logger.info("Service health updated: %s (degradation: %s)", health_val, level_name)

    async def _update_response_time_metric(self, response_time: float):
        """Update average response time metric (thread-safe)"""
        async with self._lock:
            current_avg = self.metrics["average_response_time"]
            total_requests = self.metrics["total_requests"]

            if total_requests == 1:
                self.metrics["average_response_time"] = response_time
            else:
                self.metrics["average_response_time"] = (
                    current_avg * (total_requests - 1) + response_time
                ) / total_requests

            self.service_status.response_time = response_time

    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while not self._shutdown:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error("Error in monitoring loop: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY * 2)

    async def _perform_health_check(self):
        """Perform periodic health check (thread-safe)"""
        # Calculate uptime percentage based on success rate
        async with self._lock:
            total_requests = self.metrics["total_requests"]
            successful_requests = self.metrics["successful_requests"]
            if total_requests > 0:
                success_rate = (successful_requests / total_requests) * 100
                self.service_status.uptime_percentage = success_rate
            health = self.service_status.health.value
            uptime = self.service_status.uptime_percentage

        # Log health status (outside lock)
        logger.debug("Health check: %s (uptime: %.1f%%)", health, uptime)

    async def get_service_status(self) -> ServiceStatus:
        """Get current service status (thread-safe, returns snapshot)"""
        async with self._lock:
            # Return a copy to prevent external modification
            return ServiceStatus(
                health=self.service_status.health,
                degradation_level=self.service_status.degradation_level,
                last_success=self.service_status.last_success,
                last_failure=self.service_status.last_failure,
                consecutive_failures=self.service_status.consecutive_failures,
                error_rate=self.service_status.error_rate,
                response_time=self.service_status.response_time,
                uptime_percentage=self.service_status.uptime_percentage,
            )

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics (thread-safe, returns snapshot)"""
        async with self._lock:
            # Copy metrics dict to prevent external modification
            metrics_copy = dict(self.metrics)
            metrics_copy["fallback_usage"] = dict(self.metrics["fallback_usage"])
            service_status_copy = {
                "health": self.service_status.health.value,
                "degradation_level": self.service_status.degradation_level.name,
                "consecutive_failures": self.service_status.consecutive_failures,
                "error_rate": self.service_status.error_rate,
                "uptime_percentage": self.service_status.uptime_percentage,
                "last_success": self.service_status.last_success,
                "last_failure": self.service_status.last_failure,
            }
            degradation_active = (
                self.service_status.degradation_level != DegradationLevel.NORMAL
            )

        return {
            **metrics_copy,
            "service_status": service_status_copy,
            "degradation_active": degradation_active,
        }

    async def force_degradation_level(self, level: DegradationLevel):
        """Force a specific degradation level (for testing, thread-safe)"""
        async with self._lock:
            self.service_status.degradation_level = level
            level_name = level.name
        logger.info("Forced degradation level to: %s", level_name)

    async def reset_service_status(self):
        """Reset service status to healthy (for recovery, thread-safe)"""
        async with self._lock:
            self.service_status = ServiceStatus(
                health=ServiceHealth.HEALTHY, degradation_level=DegradationLevel.NORMAL
            )
            self.failure_history.clear()
        logger.info("Service status reset to healthy")


# Convenience functions and context manager
class GracefulDegradationContext:
    """Context manager for graceful degradation"""

    def __init__(self, cache_dir: str = "data/cache/claude_responses"):
        """Initialize context manager with degradation manager."""
        self.manager = GracefulDegradationManager(cache_dir)

    async def __aenter__(self):
        """Start monitoring and return the degradation manager."""
        await self.manager.start_monitoring()
        return self.manager

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop monitoring when exiting context."""
        await self.manager.stop_monitoring()


async def create_degradation_manager(
    cache_dir: str = "data/cache/claude_responses",
) -> GracefulDegradationManager:
    """Create and start a graceful degradation manager"""
    manager = GracefulDegradationManager(cache_dir)
    await manager.start_monitoring()
    return manager


# Example usage and testing
async def main():
    """Example usage of graceful degradation"""
    async with GracefulDegradationContext() as manager:
        # Test normal requests
        requests = [
            "Explain Python decorators",
            "Analyze this code: def hello(): print('world')",
            "What is the error in this code?",
            "How do I create a file in Python?",
        ]

        logger.debug("Testing graceful degradation...")

        for i, request in enumerate(requests):
            response = await manager.handle_request(request)
            logger.debug("\nRequest %s: %s", i+1, request)
            logger.debug("Response: %s...", response.content[:100])
            logger.debug("Source: %s, Confidence: %.2f", response.source, response.confidence)
            logger.debug("Degradation Level: %s", response.degradation_level.name)

            # Simulate some delay between requests
            await asyncio.sleep(0.5)

        # Test forced degradation
        logger.debug("\n" + "=" * 50)
        logger.debug("Testing forced degradation levels...")

        await manager.force_degradation_level(DegradationLevel.MINIMAL)
        response = await manager.handle_request(
            "Test request during minimal degradation"
        )
        logger.debug("Minimal degradation response: %s", response.content)

        await manager.force_degradation_level(DegradationLevel.EMERGENCY)
        response = await manager.handle_request("Test request during emergency")
        logger.debug("Emergency response: %s", response.content)

        # Print final metrics
        logger.debug("\n" + "=" * 50)
        logger.debug("Final Metrics:")
        metrics = await manager.get_metrics()
        for key, value in metrics.items():
            logger.debug("  %s: %s", key, value)


if __name__ == "__main__":
    asyncio.run(main())
