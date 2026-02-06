#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Web Research Integration Module for AutoBot Chat Workflow

This module provides a unified interface for web research capabilities,
integrating multiple research agents with proper async handling, circuit breakers,
rate limiting, and user preference management.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class ResearchType(Enum):
    """Types of research methods available"""

    BASIC = "basic"
    ADVANCED = "advanced"
    API_BASED = "api_based"


class CircuitBreakerState(Enum):
    """Circuit breaker states for research services"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, don't try
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """Circuit breaker for web research services (thread-safe)"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = TimingConstants.STANDARD_TIMEOUT):
        """Initialize circuit breaker with failure threshold and recovery timeout."""
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()  # Lock for thread-safe state access

    def call_succeeded(self):
        """Record successful call (thread-safe)"""
        with self._lock:
            self.failure_count = 0
            self.state = CircuitBreakerState.CLOSED

    def call_failed(self):
        """Record failed call (thread-safe)"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )

    def can_execute(self) -> bool:
        """Check if we can execute a call (thread-safe)"""
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True

            if self.state == CircuitBreakerState.OPEN:
                if (time.time() - self.last_failure_time) > self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to half-open")
                    return True
                return False

            # HALF_OPEN state
            return True

    def reset(self):
        """Reset circuit breaker (thread-safe)"""
        with self._lock:
            self.failure_count = 0
            self.last_failure_time = None
            self.state = CircuitBreakerState.CLOSED


class RateLimiter:
    """Rate limiter for web research requests (thread-safe)"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """Initialize rate limiter with request limit and time window."""
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []
        self._lock = asyncio.Lock()  # Lock for thread-safe request tracking

    async def acquire(self) -> bool:
        """Acquire permission for a request (thread-safe)"""
        async with self._lock:
            now = time.time()

            # Remove old requests outside the window
            self.requests = [
                req_time
                for req_time in self.requests
                if now - req_time < self.window_seconds
            ]

            if len(self.requests) >= self.max_requests:
                # Calculate wait time until next request can be made
                oldest_request = min(self.requests)
                wait_time = self.window_seconds - (now - oldest_request)

                if wait_time > 0:
                    logger.info("Rate limit reached, waiting %.2fs", wait_time)
                    # Release lock while sleeping to allow other operations
                    self._lock.release()
                    try:
                        await asyncio.sleep(wait_time)
                    finally:
                        await self._lock.acquire()
                    # Re-check after waiting (recursive call will re-acquire lock)
                    return await self._acquire_internal()

            self.requests.append(now)
            return True

    async def _acquire_internal(self) -> bool:
        """Internal acquire without lock (called when lock is already held)"""
        now = time.time()

        # Remove old requests outside the window
        self.requests = [
            req_time
            for req_time in self.requests
            if now - req_time < self.window_seconds
        ]

        if len(self.requests) >= self.max_requests:
            # Calculate wait time until next request can be made
            oldest_request = min(self.requests)
            wait_time = self.window_seconds - (now - oldest_request)

            if wait_time > 0:
                logger.info("Rate limit reached, waiting %.2fs", wait_time)
                # Release lock while sleeping to allow other operations
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()
                return await self._acquire_internal()

        self.requests.append(now)
        return True


class WebResearchIntegration:
    """
    Unified web research integration with multiple backends,
    circuit breakers, rate limiting, and user preference management.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize web research integration with config and circuit breakers."""
        self.config = config or {}

        # Initialize circuit breakers for different research methods
        self.circuit_breakers = {
            ResearchType.BASIC: CircuitBreaker(
                failure_threshold=3, recovery_timeout=TimingConstants.SHORT_TIMEOUT
            ),
            ResearchType.ADVANCED: CircuitBreaker(
                failure_threshold=5, recovery_timeout=TimingConstants.STANDARD_TIMEOUT
            ),
            ResearchType.API_BASED: CircuitBreaker(
                failure_threshold=2, recovery_timeout=45  # Custom value between SHORT and STANDARD
            ),
        }

        # Rate limiter to prevent API abuse
        self.rate_limiter = RateLimiter(
            max_requests=self.config.get("rate_limit_requests", 5),
            window_seconds=self.config.get("rate_limit_window", 60),
        )

        # Cache for recent research results
        self.cache = {}
        self.cache_ttl = self.config.get("cache_ttl", 3600)  # 1 hour

        # Research preferences
        self.enabled = self.config.get("enabled", False)
        self.preferred_method = ResearchType(
            self.config.get("preferred_method", "basic")
        )
        self.timeout_seconds = self.config.get("timeout_seconds", 30)
        self.max_results = self.config.get("max_results", 5)

        # Initialize research agents (lazy loading)
        self._basic_agent = None
        self._advanced_agent = None
        self._api_agent = None

        logger.info(
            f"WebResearchIntegration initialized - enabled: {self.enabled}, "
            f"preferred_method: {self.preferred_method.value}"
        )

    async def is_enabled(self) -> bool:
        """Check if web research is enabled"""
        return self.enabled

    async def enable_research(self, user_confirmed: bool = False) -> bool:
        """
        Enable web research with optional user confirmation.

        Args:
            user_confirmed: Whether the user has explicitly confirmed they want research

        Returns:
            True if research was enabled
        """
        if user_confirmed:
            self.enabled = True
            logger.info("Web research enabled by user confirmation")
            return True
        return False

    async def disable_research(self) -> bool:
        """Disable web research"""
        self.enabled = False
        logger.info("Web research disabled")
        return True

    def _build_disabled_response(self, query: str) -> Dict[str, Any]:
        """Build response for disabled state (Issue #281 - extracted helper)."""
        return {
            "status": "disabled",
            "message": "Web research is disabled. Enable it in settings to use this feature.",
            "query": query,
            "results": [],
            "timestamp": datetime.now().isoformat(),
        }

    def _build_rate_limited_response(self, query: str) -> Dict[str, Any]:
        """Build response for rate limited state (Issue #281 - extracted helper)."""
        return {
            "status": "rate_limited",
            "message": "Too many research requests. Please wait and try again.",
            "query": query,
            "results": [],
            "timestamp": datetime.now().isoformat(),
        }

    def _build_failure_response(
        self, query: str, methods_tried: List[ResearchType], last_error: Optional[str]
    ) -> Dict[str, Any]:
        """Build response for all methods failed (Issue #281 - extracted helper)."""
        return {
            "status": "failed",
            "message": f"All research methods failed. Last error: {last_error}",
            "query": query,
            "results": [],
            "methods_tried": [m.value for m in methods_tried],
            "timestamp": datetime.now().isoformat(),
        }

    def _get_fallback_methods(self, method: ResearchType) -> List[ResearchType]:
        """Get list of methods to try with fallbacks (Issue #281 - extracted helper)."""
        methods = [method]
        if method != ResearchType.BASIC:
            methods.append(ResearchType.BASIC)
        if method != ResearchType.ADVANCED and ResearchType.ADVANCED not in methods:
            methods.insert(-1, ResearchType.ADVANCED)
        return methods

    async def _try_research_method(
        self,
        research_method: ResearchType,
        query: str,
        max_res: int,
        timeout_secs: int,
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        """Try a single research method (Issue #281 - extracted helper).

        Returns result dict on success, None on failure.
        """
        circuit_breaker = self.circuit_breakers[research_method]

        if not circuit_breaker.can_execute():
            logger.warning("Circuit breaker open for %s, skipping", research_method.value)
            return None

        try:
            logger.info("Attempting research using %s method", research_method.value)
            research_task = asyncio.create_task(
                self._execute_research_method(research_method, query, max_res)
            )
            result = await asyncio.wait_for(research_task, timeout=timeout_secs)

            circuit_breaker.call_succeeded()
            result["method_used"] = research_method.value
            result["timestamp"] = datetime.now().isoformat()

            if result.get("status") == "success":
                self._cache_result(cache_key, result)

            logger.info("Research completed successfully using %s", research_method.value)
            return result

        except asyncio.TimeoutError:
            logger.warning("Research timed out after %ss using %s", timeout_secs, research_method.value)
            circuit_breaker.call_failed()
        except Exception as e:
            logger.error("Research failed using %s: %s", research_method.value, str(e))
            circuit_breaker.call_failed()

        return None

    async def conduct_research(
        self,
        query: str,
        research_type: Optional[ResearchType] = None,
        max_results: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Conduct web research using the best available method.

        Issue #281: Refactored to use extracted helpers.
        """
        if not self.enabled:
            return self._build_disabled_response(query)

        cache_key = self._generate_cache_key(query, research_type, max_results)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.info("Returning cached research result for query: %s...", query[:50])
            cached_result["from_cache"] = True
            return cached_result

        if not await self.rate_limiter.acquire():
            return self._build_rate_limited_response(query)

        method = research_type or self.preferred_method
        max_res = max_results or self.max_results
        timeout_secs = timeout or self.timeout_seconds
        methods_to_try = self._get_fallback_methods(method)

        for research_method in methods_to_try:
            result = await self._try_research_method(
                research_method, query, max_res, timeout_secs, cache_key
            )
            if result:
                return result

        return self._build_failure_response(query, methods_to_try, "All methods exhausted")

    async def _execute_research_method(
        self, method: ResearchType, query: str, max_results: int
    ) -> Dict[str, Any]:
        """Execute research using specified method"""

        if method == ResearchType.BASIC:
            return await self._basic_research(query, max_results)
        elif method == ResearchType.ADVANCED:
            return await self._advanced_research(query, max_results)
        elif method == ResearchType.API_BASED:
            return await self._api_based_research(query, max_results)
        else:
            raise ValueError(f"Unknown research method: {method}")

    async def _basic_research(self, query: str, max_results: int) -> Dict[str, Any]:
        """Execute basic web research"""
        if self._basic_agent is None:
            try:
                from agents.web_research_assistant import WebResearchAssistant

                self._basic_agent = WebResearchAssistant(self.config)
                logger.info("Basic research agent initialized")
            except ImportError as e:
                raise RuntimeError(f"Failed to import basic research agent: {e}")

        try:
            result = await self._basic_agent.research_query(query)

            # Format result to match expected structure
            if result.get("status") == "success":
                # Limit results
                sources = result.get("sources", [])[:max_results]
                result["sources"] = sources
                result["results_count"] = len(sources)

            return result

        except Exception as e:
            logger.error("Basic research failed: %s", e)
            raise

    async def _advanced_research(self, query: str, max_results: int) -> Dict[str, Any]:
        """Execute advanced web research with Playwright"""
        if self._advanced_agent is None:
            try:
                from agents.advanced_web_research import AdvancedWebResearcher

                self._advanced_agent = AdvancedWebResearcher(self.config)
                await self._advanced_agent.initialize()
                logger.info("Advanced research agent initialized")
            except ImportError as e:
                raise RuntimeError(f"Failed to import advanced research agent: {e}")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize advanced research agent: {e}")

        try:
            result = await self._advanced_agent.search_web(query, max_results)
            return result

        except Exception as e:
            logger.error("Advanced research failed: %s", e)
            raise

    async def _api_based_research(self, query: str, max_results: int) -> Dict[str, Any]:
        """Execute API-based web research"""
        if self._api_agent is None:
            try:
                from agents.research_agent import ResearchAgent, ResearchRequest

                self._api_agent = ResearchAgent()
                logger.info("API research agent initialized")
            except ImportError as e:
                raise RuntimeError(f"Failed to import API research agent: {e}")

        try:
            request = ResearchRequest(
                query=query, max_results=max_results, focus="general"
            )

            result = await self._api_agent.perform_research(request)

            # Convert API response to standard format
            return {
                "status": "success" if result.success else "failed",
                "query": result.query,
                "results": [r.dict() for r in result.results],
                "summary": result.summary,
                "sources_count": result.sources_count,
                "execution_time": result.execution_time,
            }

        except Exception as e:
            logger.error("API research failed: %s", e)
            raise

    def _generate_cache_key(
        self,
        query: str,
        research_type: Optional[ResearchType],
        max_results: Optional[int],
    ) -> str:
        """Generate cache key for research result"""
        method = research_type.value if research_type else "default"
        results = max_results or self.max_results
        return f"research:{hash(query)}:{method}:{results}"

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached research result if valid"""
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            cache_time = cached_data.get("cached_at", 0)

            if time.time() - cache_time < self.cache_ttl:
                return cached_data.get("result")
            else:
                # Remove expired cache entry
                del self.cache[cache_key]

        return None

    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache research result"""
        self.cache[cache_key] = {"result": result, "cached_at": time.time()}

        # Clean up old cache entries if cache gets too large
        if len(self.cache) > 100:
            self._cleanup_cache()

    def _cleanup_cache(self):
        """Clean up expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key
            for key, data in self.cache.items()
            if current_time - data.get("cached_at", 0) > self.cache_ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        logger.debug("Cleaned up %s expired cache entries", len(expired_keys))

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        return {
            method.value: {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "last_failure": breaker.last_failure_time,
            }
            for method, breaker in self.circuit_breakers.items()
        }

    def reset_circuit_breakers(self):
        """Reset all circuit breakers"""
        for breaker in self.circuit_breakers.values():
            breaker.reset()
        logger.info("All circuit breakers reset")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "cache_size": len(self.cache),
            "cache_ttl": self.cache_ttl,
            "rate_limiter": {
                "max_requests": self.rate_limiter.max_requests,
                "window_seconds": self.rate_limiter.window_seconds,
                "current_requests": len(self.rate_limiter.requests),
            },
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on research integration"""
        health_status = {
            "enabled": self.enabled,
            "preferred_method": self.preferred_method.value,
            "circuit_breakers": self.get_circuit_breaker_status(),
            "cache_stats": self.get_cache_stats(),
            "agents_status": {},
        }

        # Check basic agent
        try:
            if self._basic_agent is not None:
                health_status["agents_status"]["basic"] = "initialized"
            else:
                health_status["agents_status"]["basic"] = "not_initialized"
        except Exception as e:
            health_status["agents_status"]["basic"] = f"error: {str(e)}"

        # Check advanced agent
        try:
            if self._advanced_agent is not None:
                health_status["agents_status"]["advanced"] = "initialized"
            else:
                health_status["agents_status"]["advanced"] = "not_initialized"
        except Exception as e:
            health_status["agents_status"]["advanced"] = f"error: {str(e)}"

        # Check API agent
        try:
            if self._api_agent is not None:
                health_status["agents_status"]["api"] = "initialized"
            else:
                health_status["agents_status"]["api"] = "not_initialized"
        except Exception as e:
            health_status["agents_status"]["api"] = f"error: {str(e)}"

        return health_status


# Global research integration instance (thread-safe)
_global_research_integration = None
_global_research_integration_lock = threading.Lock()


def _load_web_research_config() -> Dict[str, Any]:
    """Load web research config from config manager (Issue #334 - extracted helper)."""
    try:
        from config import config_manager
        return config_manager.get_nested("web_research", {})
    except Exception as e:
        logger.warning("Could not load web research config: %s", e)
        return {}


def _create_research_integration(
    config: Optional[Dict[str, Any]]
) -> WebResearchIntegration:
    """Create research integration instance (Issue #334 - extracted helper)."""
    if config is None:
        config = _load_web_research_config()
    return WebResearchIntegration(config)


def get_web_research_integration(
    config: Optional[Dict[str, Any]] = None,
) -> WebResearchIntegration:
    """Get or create global web research integration instance (thread-safe)."""
    global _global_research_integration

    if _global_research_integration is not None:
        return _global_research_integration

    with _global_research_integration_lock:
        # Double-check after acquiring lock
        if _global_research_integration is None:
            _global_research_integration = _create_research_integration(config)

    return _global_research_integration


async def conduct_web_research(query: str, **kwargs) -> Dict[str, Any]:
    """
    Convenience function to conduct web research.

    Args:
        query: Search query
        **kwargs: Additional arguments for research

    Returns:
        Research results
    """
    integration = get_web_research_integration()
    return await integration.conduct_research(query, **kwargs)
