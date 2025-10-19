"""
Claude API Optimization Suite - Integration Layer

This module provides a unified interface that integrates all Claude API optimization
components to prevent conversation crashes due to rate limiting. It coordinates
the conversation rate limiter, payload optimizer, API monitor, request batcher,
graceful degradation, TodoWrite optimizer, and tool pattern analyzer.

This is the main integration point for the comprehensive Claude API optimization solution.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from src.constants.network_constants import NetworkConstants

from ..monitoring.claude_api_monitor import ClaudeAPIMonitor

# Import all optimization components
from .conversation_rate_limiter import ConversationRateLimiter, RateLimitExceededError
from .graceful_degradation import FallbackResponse, GracefulDegradationManager
from .payload_optimizer import OptimizationResult, PayloadOptimizer
from .request_batcher import BatchableRequest, IntelligentRequestBatcher
from .todowrite_optimizer import TodoWriteOptimizer, get_todowrite_optimizer
from .tool_pattern_analyzer import ToolPatternAnalyzer, get_tool_pattern_analyzer

logger = logging.getLogger(__name__)


class OptimizationMode(Enum):
    """Optimization modes for different scenarios"""

    CONSERVATIVE = "conservative"  # Light optimization, minimal interference
    BALANCED = "balanced"  # Balanced optimization for normal development
    AGGRESSIVE = "aggressive"  # Maximum optimization for high-frequency usage
    EMERGENCY = "emergency"  # Emergency mode for when rate limits are exceeded


@dataclass
class OptimizationConfig:
    """Configuration for the optimization suite"""

    mode: OptimizationMode = OptimizationMode.BALANCED
    enable_rate_limiting: bool = True
    enable_payload_optimization: bool = True
    enable_request_batching: bool = True
    enable_graceful_degradation: bool = True
    enable_todowrite_optimization: bool = True
    enable_pattern_analysis: bool = True

    # Rate limiting settings
    max_requests_per_minute: int = 50
    max_requests_per_hour: int = 2000

    # Payload optimization settings
    max_payload_size: int = 1048576  # 1MB
    enable_compression: bool = True

    # Batching settings
    max_batch_size: int = 5
    batch_time_window: float = 2.0

    # TodoWrite optimization settings
    todowrite_consolidation_window: int = 30
    todowrite_similarity_threshold: float = 0.8

    # Pattern analysis settings
    pattern_analysis_interval: int = 300  # 5 minutes

    # Graceful degradation settings
    enable_caching: bool = True
    cache_ttl: int = 300  # 5 minutes


@dataclass
class OptimizationMetrics:
    """Metrics for optimization performance"""

    total_requests_processed: int = 0
    requests_rate_limited: int = 0
    requests_optimized: int = 0
    requests_batched: int = 0
    requests_cached: int = 0
    api_calls_saved: int = 0
    total_response_time_saved: float = 0.0
    conversation_crashes_prevented: int = 0
    last_reset_time: datetime = field(default_factory=datetime.now)


class ClaudeAPIOptimizationSuite:
    """
    Main optimization suite that coordinates all Claude API optimization components.

    This class provides a unified interface for preventing Claude conversation crashes
    due to API rate limiting during development sessions.
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize the optimization suite with all components"""
        self.config = config or OptimizationConfig()

        # Initialize all optimization components
        self._initialize_components()

        # Performance metrics
        self.metrics = OptimizationMetrics()

        # State tracking
        self.is_active = False
        self.current_mode = self.config.mode
        self.optimization_history: List[Dict[str, Any]] = []

        # Async task management
        self._background_tasks: List[asyncio.Task] = []

        logger.info(
            f"Claude API Optimization Suite initialized in {self.config.mode.value} mode"
        )

    def _initialize_components(self):
        """Initialize all optimization components based on configuration"""

        # Rate limiter
        if self.config.enable_rate_limiting:
            self.rate_limiter = ConversationRateLimiter(
                max_requests_per_minute=self.config.max_requests_per_minute,
                max_requests_per_hour=self.config.max_requests_per_hour,
            )
        else:
            self.rate_limiter = None

        # Payload optimizer
        if self.config.enable_payload_optimization:
            self.payload_optimizer = PayloadOptimizer(
                max_size=self.config.max_payload_size,
                enable_compression=self.config.enable_compression,
            )
        else:
            self.payload_optimizer = None

        # Request batcher
        if self.config.enable_request_batching:
            self.request_batcher = IntelligentRequestBatcher(
                max_batch_size=self.config.max_batch_size,
                time_window=self.config.batch_time_window,
            )
        else:
            self.request_batcher = None

        # Graceful degradation manager
        if self.config.enable_graceful_degradation:
            self.degradation_manager = GracefulDegradationManager(
                {
                    "enable_caching": self.config.enable_caching,
                    "cache_ttl": self.config.cache_ttl,
                }
            )
        else:
            self.degradation_manager = None

        # TodoWrite optimizer
        if self.config.enable_todowrite_optimization:
            self.todowrite_optimizer = get_todowrite_optimizer(
                {
                    "consolidation_window": self.config.todowrite_consolidation_window,
                    "similarity_threshold": self.config.todowrite_similarity_threshold,
                }
            )
        else:
            self.todowrite_optimizer = None

        # Tool pattern analyzer
        if self.config.enable_pattern_analysis:
            self.pattern_analyzer = get_tool_pattern_analyzer(
                {"analysis_window": self.config.pattern_analysis_interval}
            )
        else:
            self.pattern_analyzer = None

        # API monitor
        self.api_monitor = ClaudeAPIMonitor()

    async def start_optimization(self) -> bool:
        """Start the optimization suite"""
        try:
            if self.is_active:
                logger.warning("Optimization suite is already active")
                return True

            self.is_active = True

            # Start background monitoring tasks
            if self.config.enable_pattern_analysis:
                task = asyncio.create_task(self._background_pattern_analysis())
                self._background_tasks.append(task)

            # Start API monitoring
            monitoring_task = asyncio.create_task(self._background_api_monitoring())
            self._background_tasks.append(monitoring_task)

            # Start degradation monitoring
            if self.degradation_manager:
                degradation_task = asyncio.create_task(
                    self._background_degradation_monitoring()
                )
                self._background_tasks.append(degradation_task)

            logger.info("Claude API Optimization Suite started successfully")
            return True

        except Exception as e:
            logger.error(f"Error starting optimization suite: {e}")
            self.is_active = False
            return False

    async def stop_optimization(self) -> bool:
        """Stop the optimization suite"""
        try:
            if not self.is_active:
                logger.warning("Optimization suite is not active")
                return True

            self.is_active = False

            # Cancel background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)

            self._background_tasks.clear()

            logger.info("Claude API Optimization Suite stopped")
            return True

        except Exception as e:
            logger.error(f"Error stopping optimization suite: {e}")
            return False

    async def optimize_request(
        self, request_data: Dict[str, Any], request_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Optimize a Claude API request through the complete optimization pipeline.

        Args:
            request_data: The request data to optimize
            request_type: Type of request (todowrite, tool_call, etc.)

        Returns:
            Optimized request data or fallback response
        """
        start_time = time.time()
        optimization_applied = []

        try:
            self.metrics.total_requests_processed += 1

            # Step 1: Rate limiting check
            if self.rate_limiter and not await self._check_rate_limits(request_data):
                self.metrics.requests_rate_limited += 1
                self.metrics.conversation_crashes_prevented += 1

                # Try graceful degradation
                if self.degradation_manager:
                    fallback = await self.degradation_manager.handle_request(
                        str(request_data), {"type": request_type}
                    )
                    if fallback.success:
                        self.metrics.requests_cached += 1
                        return {
                            "status": "fallback",
                            "data": fallback.response,
                            "source": fallback.source,
                        }

                return {"status": "rate_limited", "retry_after": 60}

            # Step 2: TodoWrite optimization (special handling)
            if request_type == "todowrite" and self.todowrite_optimizer:
                optimized = await self._optimize_todowrite_request(request_data)
                if optimized:
                    optimization_applied.append("todowrite_optimization")
                    self.metrics.requests_optimized += 1
                    return optimized

            # Step 3: Payload optimization
            if self.payload_optimizer:
                optimization_result = await self.payload_optimizer.optimize_payload(
                    request_data
                )
                if optimization_result.optimized:
                    request_data = optimization_result.optimized_payload
                    optimization_applied.append("payload_optimization")
                    self.metrics.total_response_time_saved += (
                        optimization_result.size_reduction / 1000
                    )  # Estimate time saved

            # Step 4: Request batching
            if self.request_batcher and self._should_batch_request(request_type):
                batched = await self._attempt_request_batching(
                    request_data, request_type
                )
                if batched:
                    optimization_applied.append("request_batching")
                    self.metrics.requests_batched += 1
                    self.metrics.api_calls_saved += 1
                    return batched

            # Step 5: Record tool usage for pattern analysis
            if self.pattern_analyzer:
                self.pattern_analyzer.record_tool_call(
                    tool_name=request_type,
                    parameters=request_data,
                    response_time=time.time() - start_time,
                    success=True,
                )

            # Step 6: Execute request (simulated - in real implementation this would call Claude API)
            response = await self._execute_optimized_request(request_data, request_type)

            # Step 7: Cache successful response for degradation
            if self.degradation_manager and response.get("status") == "success":
                await self.degradation_manager._cache_response(
                    str(request_data), response["data"]
                )

            # Update metrics
            if optimization_applied:
                self.metrics.requests_optimized += 1

            # Record optimization history
            self.optimization_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "request_type": request_type,
                    "optimizations_applied": optimization_applied,
                    "response_time": time.time() - start_time,
                    "success": True,
                }
            )

            return {
                "status": "success",
                "data": response.get("data"),
                "optimizations_applied": optimization_applied,
                "response_time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Error optimizing request: {e}")

            # Record pattern analysis for failed request
            if self.pattern_analyzer:
                self.pattern_analyzer.record_tool_call(
                    tool_name=request_type,
                    parameters=request_data,
                    response_time=time.time() - start_time,
                    success=False,
                    error_message=str(e),
                )

            # Try graceful degradation for errors
            if self.degradation_manager:
                fallback = await self.degradation_manager.handle_request(
                    str(request_data), {"type": request_type, "error": str(e)}
                )
                if fallback.success:
                    return {
                        "status": "fallback",
                        "data": fallback.response,
                        "source": fallback.source,
                    }

            return {"status": "error", "error": str(e)}

    async def _check_rate_limits(self, request_data: Dict[str, Any]) -> bool:
        """Check if request can proceed based on rate limits"""
        try:
            can_proceed = await self.rate_limiter.can_make_request(
                payload_size=len(str(request_data))
            )
            return can_proceed
        except RateLimitExceededError:
            return False

    async def _optimize_todowrite_request(
        self, request_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle TodoWrite optimization specifically"""
        try:
            todos = request_data.get("todos", [])
            if not todos:
                return None

            # Add todos to optimizer instead of immediate execution
            optimized_count = 0
            for todo in todos:
                success = self.todowrite_optimizer.add_todo_for_optimization(
                    content=todo.get("content", ""),
                    status=todo.get("status", "pending"),
                    active_form=todo.get("activeForm", ""),
                    priority=todo.get("priority", 5),
                )
                if success:
                    optimized_count += 1

            if optimized_count > 0:
                self.metrics.api_calls_saved += (
                    len(todos) - 1
                )  # N todos -> 1 optimized call
                return {
                    "status": "optimized",
                    "message": f"{optimized_count} todos added for optimization",
                    "optimization_type": "todowrite_batching",
                }

            return None

        except Exception as e:
            logger.error(f"Error optimizing TodoWrite request: {e}")
            return None

    def _should_batch_request(self, request_type: str) -> bool:
        """Determine if request type should be considered for batching"""
        batchable_types = ["read", "search", "analyze", "tool_call"]
        return any(btype in request_type.lower() for btype in batchable_types)

    async def _attempt_request_batching(
        self, request_data: Dict[str, Any], request_type: str
    ) -> Optional[Dict[str, Any]]:
        """Attempt to batch the request with similar pending requests"""
        try:
            batchable_request = BatchableRequest(
                request_id=f"{request_type}_{int(time.time())}",
                request_type=request_type,
                content=str(request_data),
                parameters=request_data,
                priority=5,
            )

            batch_result = await self.request_batcher.add_request(batchable_request)

            if batch_result and batch_result.get("batched"):
                return {
                    "status": "batched",
                    "batch_id": batch_result.get("batch_id"),
                    "optimization_type": "request_batching",
                }

            return None

        except Exception as e:
            logger.error(f"Error attempting request batching: {e}")
            return None

    async def _execute_optimized_request(
        self, request_data: Dict[str, Any], request_type: str
    ) -> Dict[str, Any]:
        """Execute the optimized request (simulation for this implementation)"""
        # In a real implementation, this would make the actual Claude API call
        # For now, we simulate a successful response
        await asyncio.sleep(0.1)  # Simulate API response time

        return {
            "status": "success",
            "data": {"message": "Request processed successfully", "type": request_type},
            "response_time": 0.1,
        }

    async def _background_pattern_analysis(self):
        """Background task for pattern analysis"""
        while self.is_active:
            try:
                await asyncio.sleep(self.config.pattern_analysis_interval)

                if self.pattern_analyzer:
                    # Trigger pattern analysis
                    analysis_results = self.pattern_analyzer.get_analysis_results(
                        force_refresh=True
                    )

                    # Check for critical inefficiencies
                    recommendations = (
                        self.pattern_analyzer.get_optimization_recommendations()
                    )
                    critical_recommendations = [
                        rec
                        for rec in recommendations
                        if rec.get("priority_score", 0) > 0.8
                    ]

                    if critical_recommendations:
                        logger.warning(
                            f"Found {len(critical_recommendations)} critical optimization opportunities"
                        )

                        # Auto-adjust mode if needed
                        if len(critical_recommendations) > 3:
                            await self._adjust_optimization_mode(
                                OptimizationMode.AGGRESSIVE
                            )

            except Exception as e:
                logger.error(f"Error in background pattern analysis: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _background_api_monitoring(self):
        """Background task for API monitoring"""
        while self.is_active:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Get API usage statistics
                usage_stats = self.api_monitor.get_usage_statistics()

                # Check for approaching rate limits
                rate_limit_risk = self.api_monitor.predict_rate_limit_risk()

                if rate_limit_risk > 0.8:  # High risk
                    logger.warning(
                        f"High rate limit risk detected: {rate_limit_risk:.2f}"
                    )
                    await self._adjust_optimization_mode(OptimizationMode.AGGRESSIVE)

                elif rate_limit_risk > 0.6:  # Moderate risk
                    logger.info(f"Moderate rate limit risk: {rate_limit_risk:.2f}")
                    await self._adjust_optimization_mode(OptimizationMode.BALANCED)

            except Exception as e:
                logger.error(f"Error in background API monitoring: {e}")
                await asyncio.sleep(60)

    async def _background_degradation_monitoring(self):
        """Background task for degradation monitoring"""
        while self.is_active:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if self.degradation_manager:
                    status = self.degradation_manager.get_service_status()

                    # Adjust optimization based on service health
                    if status["degradation_level"] == "EMERGENCY":
                        await self._adjust_optimization_mode(OptimizationMode.EMERGENCY)
                    elif status["degradation_level"] == "MINIMAL":
                        await self._adjust_optimization_mode(
                            OptimizationMode.AGGRESSIVE
                        )

            except Exception as e:
                logger.error(f"Error in degradation monitoring: {e}")
                await asyncio.sleep(60)

    async def _adjust_optimization_mode(self, new_mode: OptimizationMode):
        """Dynamically adjust optimization mode based on conditions"""
        if new_mode != self.current_mode:
            logger.info(
                f"Adjusting optimization mode from {self.current_mode.value} to {new_mode.value}"
            )

            old_mode = self.current_mode
            self.current_mode = new_mode

            # Adjust component settings based on new mode
            await self._reconfigure_components_for_mode(new_mode)

            # Record mode change in history
            self.optimization_history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "event": "mode_change",
                    "old_mode": old_mode.value,
                    "new_mode": new_mode.value,
                    "reason": "automatic_adjustment",
                }
            )

    async def _reconfigure_components_for_mode(self, mode: OptimizationMode):
        """Reconfigure components for the new optimization mode"""
        if mode == OptimizationMode.CONSERVATIVE:
            # Light optimization settings
            if self.rate_limiter:
                self.rate_limiter.requests_per_minute = 60
                self.rate_limiter.requests_per_hour = 2500

        elif mode == OptimizationMode.BALANCED:
            # Default settings
            if self.rate_limiter:
                self.rate_limiter.requests_per_minute = 50
                self.rate_limiter.requests_per_hour = 2000

        elif mode == OptimizationMode.AGGRESSIVE:
            # Maximum optimization settings
            if self.rate_limiter:
                self.rate_limiter.requests_per_minute = 30
                self.rate_limiter.requests_per_hour = 1500

        elif mode == OptimizationMode.EMERGENCY:
            # Emergency settings
            if self.rate_limiter:
                self.rate_limiter.requests_per_minute = 15
                self.rate_limiter.requests_per_hour = 800

    def get_optimization_status(self) -> Dict[str, Any]:
        """Get current optimization status and metrics"""
        return {
            "is_active": self.is_active,
            "current_mode": self.current_mode.value,
            "config": {
                "rate_limiting_enabled": self.config.enable_rate_limiting,
                "payload_optimization_enabled": self.config.enable_payload_optimization,
                "request_batching_enabled": self.config.enable_request_batching,
                "graceful_degradation_enabled": self.config.enable_graceful_degradation,
                "todowrite_optimization_enabled": self.config.enable_todowrite_optimization,
                "pattern_analysis_enabled": self.config.enable_pattern_analysis,
            },
            "metrics": {
                "total_requests_processed": self.metrics.total_requests_processed,
                "requests_rate_limited": self.metrics.requests_rate_limited,
                "requests_optimized": self.metrics.requests_optimized,
                "requests_batched": self.metrics.requests_batched,
                "requests_cached": self.metrics.requests_cached,
                "api_calls_saved": self.metrics.api_calls_saved,
                "total_response_time_saved": self.metrics.total_response_time_saved,
                "conversation_crashes_prevented": self.metrics.conversation_crashes_prevented,
                "optimization_efficiency": (
                    (
                        self.metrics.api_calls_saved
                        / max(1, self.metrics.total_requests_processed)
                    )
                    * 100
                ),
            },
            "component_status": self._get_component_status(),
        }

    def _get_component_status(self) -> Dict[str, Any]:
        """Get status of all optimization components"""
        status = {}

        if self.rate_limiter:
            rate_stats = self.rate_limiter.get_usage_statistics()
            status["rate_limiter"] = {
                "active": True,
                "current_usage": rate_stats["current_minute_count"],
                "hourly_usage": rate_stats["current_hour_count"],
            }

        if self.todowrite_optimizer:
            todowrite_stats = self.todowrite_optimizer.get_optimization_stats()
            status["todowrite_optimizer"] = {
                "active": True,
                "pending_todos": todowrite_stats["pending_todos_count"],
                "total_optimizations": todowrite_stats["optimization_stats"][
                    "total_optimizations"
                ],
            }

        if self.pattern_analyzer:
            pattern_stats = self.pattern_analyzer.get_analysis_results()
            status["pattern_analyzer"] = {
                "active": True,
                "total_patterns": pattern_stats.get("patterns_detected", 0),
                "optimization_opportunities": pattern_stats.get(
                    "optimization_opportunities", 0
                ),
            }

        if self.degradation_manager:
            degradation_status = self.degradation_manager.get_service_status()
            status["degradation_manager"] = {
                "active": True,
                "degradation_level": degradation_status["degradation_level"],
                "service_health": degradation_status["health_score"],
            }

        return status

    def get_comprehensive_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report"""
        report = {
            "report_generated_at": datetime.now().isoformat(),
            "optimization_suite_status": self.get_optimization_status(),
            "detailed_metrics": self.metrics.__dict__,
            "optimization_history": self.optimization_history[-20:],  # Last 20 events
            "component_reports": {},
        }

        # Add component-specific reports
        if self.todowrite_optimizer:
            report["component_reports"][
                "todowrite_optimizer"
            ] = self.todowrite_optimizer.get_optimization_recommendations()

        if self.pattern_analyzer:
            report["component_reports"][
                "pattern_analyzer"
            ] = self.pattern_analyzer.get_optimization_recommendations()

        if self.api_monitor:
            report["component_reports"][
                "api_monitor"
            ] = self.api_monitor.get_optimization_recommendations()

        return report

    async def force_optimization_analysis(self) -> Dict[str, Any]:
        """Force immediate optimization analysis across all components"""
        analysis_results = {}

        try:
            # Force TodoWrite optimization
            if self.todowrite_optimizer:
                batch_result = await self.todowrite_optimizer.force_optimization()
                analysis_results["todowrite_optimization"] = {
                    "batch_processed": batch_result is not None,
                    "batch_score": (
                        batch_result.optimization_score if batch_result else 0
                    ),
                }

            # Force pattern analysis
            if self.pattern_analyzer:
                pattern_results = self.pattern_analyzer.get_analysis_results(
                    force_refresh=True
                )
                analysis_results["pattern_analysis"] = pattern_results

            # Get fresh API monitoring insights
            if self.api_monitor:
                api_insights = self.api_monitor.get_optimization_recommendations()
                analysis_results["api_monitoring"] = api_insights

            # Update metrics
            self.metrics.requests_optimized += 1

            return {
                "status": "success",
                "analysis_results": analysis_results,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error during forced optimization analysis: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def reset_metrics(self):
        """Reset all optimization metrics"""
        self.metrics = OptimizationMetrics()
        self.optimization_history.clear()
        logger.info("Optimization metrics reset")

    async def export_optimization_report(self, file_path: str) -> bool:
        """Export comprehensive optimization report to file"""
        try:
            report = self.get_comprehensive_report()

            with open(file_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"Optimization report exported to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting optimization report: {e}")
            return False


# Global optimization suite instance
_global_optimization_suite: Optional[ClaudeAPIOptimizationSuite] = None


def get_optimization_suite(
    config: Optional[OptimizationConfig] = None,
) -> ClaudeAPIOptimizationSuite:
    """Get global optimization suite instance"""
    global _global_optimization_suite
    if _global_optimization_suite is None:
        _global_optimization_suite = ClaudeAPIOptimizationSuite(config)
    return _global_optimization_suite


async def initialize_claude_api_optimization(
    config: Optional[OptimizationConfig] = None,
) -> bool:
    """Initialize and start the Claude API optimization suite"""
    suite = get_optimization_suite(config)
    return await suite.start_optimization()


async def shutdown_claude_api_optimization() -> bool:
    """Shutdown the Claude API optimization suite"""
    global _global_optimization_suite
    if _global_optimization_suite:
        result = await _global_optimization_suite.stop_optimization()
        _global_optimization_suite = None
        return result
    return True


# Convenience functions for common operations
async def optimize_claude_request(
    request_data: Dict[str, Any], request_type: str = "general"
) -> Dict[str, Any]:
    """Optimize a Claude API request using the global optimization suite"""
    suite = get_optimization_suite()
    return await suite.optimize_request(request_data, request_type)


async def optimize_todowrite(todos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Optimize TodoWrite operation specifically"""
    return await optimize_claude_request({"todos": todos}, "todowrite")


def get_optimization_insights() -> Dict[str, Any]:
    """Get current optimization insights and recommendations"""
    suite = get_optimization_suite()
    return suite.get_optimization_status()


# Example usage and testing
async def example_usage():
    """Example of how to use the Claude API optimization suite"""

    # Initialize with custom configuration
    config = OptimizationConfig(
        mode=OptimizationMode.BALANCED,
        enable_todowrite_optimization=True,
        enable_pattern_analysis=True,
        todowrite_consolidation_window=45,
    )

    # Start optimization
    success = await initialize_claude_api_optimization(config)
    if not success:
        print("Failed to initialize optimization suite")
        return

    # Get optimization suite
    suite = get_optimization_suite()

    # Example: Optimize TodoWrite operation
    todowrite_result = await optimize_todowrite(
        [
            {
                "content": "Implement authentication system",
                "status": "pending",
                "activeForm": "Implementing authentication system",
            },
            {
                "content": "Create login endpoint",
                "status": "pending",
                "activeForm": "Creating login endpoint",
            },
            {
                "content": "Add auth middleware",
                "status": "pending",
                "activeForm": "Adding auth middleware",
            },
        ]
    )
    print("TodoWrite optimization result:", json.dumps(todowrite_result, indent=2))

    # Example: Optimize general request
    general_result = await optimize_claude_request(
        {"action": "read_file", "path": "/test/file.py"}, "read_operation"
    )
    print("General request optimization result:", json.dumps(general_result, indent=2))

    # Get optimization status
    status = suite.get_optimization_status()
    print("Optimization status:", json.dumps(status, indent=2, default=str))

    # Force optimization analysis
    analysis = await suite.force_optimization_analysis()
    print("Forced analysis result:", json.dumps(analysis, indent=2, default=str))

    # Export comprehensive report
    report_path = "/tmp/claude_optimization_report.json"
    exported = await suite.export_optimization_report(report_path)
    print(f"Report exported: {exported} -> {report_path}")

    # Shutdown
    await shutdown_claude_api_optimization()
    print("Optimization suite shutdown complete")


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
