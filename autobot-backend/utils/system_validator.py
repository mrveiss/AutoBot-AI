# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive System Validation
Validates all optimization components and their integration for production readiness.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

import aiohttp
import psutil
from config import UnifiedConfigManager

from autobot_shared.http_client import get_http_client

# Create singleton config instance
config = UnifiedConfigManager()
from backend.constants.network_constants import NetworkConstants

# Issue #380: Module-level tuple for expected system metrics
_EXPECTED_SYSTEM_METRICS = ("cpu_percent", "memory_percent", "disk_usage")


class ValidationSeverity(Enum):
    """Validation result severity levels"""

    CRITICAL = "critical"  # System cannot operate safely
    WARNING = "warning"  # Degraded performance or reliability
    INFO = "info"  # Informational, no action needed
    SUCCESS = "success"  # All systems operating optimally


@dataclass
class ValidationResult:
    """Individual validation test result"""

    component: str
    test_name: str
    severity: ValidationSeverity
    status: bool
    message: str
    details: Dict[str, Any] = None
    timestamp: float = 0.0
    duration_ms: float = 0.0


@dataclass
class SystemValidationReport:
    """Complete system validation report"""

    timestamp: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    critical_issues: int
    warnings: int
    overall_health_score: float
    system_ready: bool
    validation_results: List[ValidationResult]
    recommendations: List[str]
    performance_metrics: Dict[str, Any]


class SystemValidator:
    """Comprehensive system validation for production readiness"""

    def __init__(self):
        """Initialize system validator with validation thresholds."""
        self.logger = logging.getLogger(__name__)
        self.results: List[ValidationResult] = []

        # Validation configuration
        self.timeout_seconds = config.get("validation.timeout_seconds", 30)
        self.critical_thresholds = {
            "response_time_ms": config.get(
                "validation.thresholds.response_time_ms", 5000
            ),
            "cache_hit_rate": config.get("validation.thresholds.cache_hit_rate", 50.0),
            "memory_usage_percent": config.get(
                "validation.thresholds.memory_usage_percent", 90.0
            ),
            "cpu_usage_percent": config.get(
                "validation.thresholds.cpu_usage_percent", 95.0
            ),
            "error_rate_percent": config.get(
                "validation.thresholds.error_rate_percent", 5.0
            ),
        }

        # Service endpoints
        self.base_urls = {
            "backend": (
                f"http://{config.get_host('backend')}:{config.get_port('backend')}"
            ),
            "frontend": (
                f"http://{config.get_host('frontend')}:{config.get_port('frontend')}"
            ),
            "ollama": f"http://{config.get_host('ollama')}:{config.get_port('ollama')}",
            "redis": None,  # Special handling for Redis
        }

    def _add_result(
        self,
        component: str,
        test_name: str,
        severity: ValidationSeverity,
        status: bool,
        message: str,
        details: Dict[str, Any] = None,
        duration_ms: float = 0.0,
    ):
        """Add a validation result"""
        result = ValidationResult(
            component=component,
            test_name=test_name,
            severity=severity,
            status=status,
            message=message,
            details=details or {},
            timestamp=time.time(),
            duration_ms=duration_ms,
        )
        self.results.append(result)
        return result

    def _get_severity_for_response_time(
        self, response_time_ms: float, base_success: bool = True
    ) -> ValidationSeverity:
        """Get severity based on response time (Issue #333 - extracted helper)."""
        if not base_success:
            return ValidationSeverity.WARNING

        if response_time_ms < self.critical_thresholds["response_time_ms"]:
            return ValidationSeverity.SUCCESS
        return ValidationSeverity.WARNING

    def _get_component_results(self, component: str) -> List[ValidationResult]:
        """Get results for a specific component (Issue #333 - extracted helper)."""
        return [r for r in self.results if r.component == component]

    async def _validate_cache_stats(self, component: str, cache) -> None:
        """Validate cache statistics (Issue #333 - extracted helper)."""
        try:
            stats = await cache.get_cache_stats()
            if "cache_entries" in stats:
                self._add_result(
                    component,
                    "Cache Statistics",
                    ValidationSeverity.SUCCESS,
                    True,
                    f"Cache stats available: {stats.get('cache_entries', 0)} entries",
                    stats,
                )
            else:
                self._add_result(
                    component,
                    "Cache Statistics",
                    ValidationSeverity.WARNING,
                    False,
                    "Cache statistics not available",
                    stats,
                )
        except Exception as e:
            self._add_result(
                component,
                "Cache Statistics",
                ValidationSeverity.WARNING,
                False,
                f"Cache statistics error: {str(e)}",
            )

    async def _validate_kb_integration(self, component: str) -> None:
        """Validate knowledge base integration (Issue #333 - extracted helper)."""
        from knowledge_base import KnowledgeBase

        try:
            kb = KnowledgeBase()
            await kb.ainit()

            if not kb.index:
                self._add_result(
                    component,
                    "KB Integration",
                    ValidationSeverity.WARNING,
                    False,
                    "Knowledge base index not available",
                )
                return

            start_time = time.time()
            search_results = await kb.search("validation test query", top_k=3)
            search_time = (time.time() - start_time) * 1000

            if not search_results:
                self._add_result(
                    component,
                    "KB Integration",
                    ValidationSeverity.WARNING,
                    True,
                    "Knowledge base search returned no results",
                )
                return

            severity = self._get_severity_for_response_time(search_time)
            self._add_result(
                component,
                "KB Integration",
                severity,
                True,
                f"Knowledge base search working: {len(search_results)} results",
                {"search_time_ms": search_time, "result_count": len(search_results)},
                search_time,
            )

        except Exception as e:
            self._add_result(
                component,
                "KB Integration",
                ValidationSeverity.WARNING,
                False,
                f"Knowledge base integration error: {str(e)}",
            )

    def _validate_cache_initialization(
        self, component: str, cache, init_time: float
    ) -> bool:
        """
        Validate cache system initialization (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            cache: Cache instance or None
            init_time: Initialization time in milliseconds

        Returns:
            True if cache initialized successfully, False otherwise
        """
        if not cache:
            self._add_result(
                component,
                "Cache Initialization",
                ValidationSeverity.CRITICAL,
                False,
                "Failed to initialize cache system",
            )
            return False

        self._add_result(
            component,
            "Cache Initialization",
            ValidationSeverity.SUCCESS,
            True,
            "Cache system initialized successfully",
            {"init_time_ms": init_time},
            init_time,
        )
        return True

    async def _validate_cache_operations(self, component: str, cache) -> None:
        """
        Validate cache store/retrieve operations (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            cache: Cache instance to test
        """
        start_time = time.time()
        test_results = [{"test": "data", "score": 0.95}]
        cache_success = await cache.cache_results("validation_test", 5, test_results)
        retrieved_results = await cache.get_cached_results("validation_test", 5)
        cache_time = (time.time() - start_time) * 1000

        if cache_success and retrieved_results:
            self._add_result(
                component,
                "Cache Operations",
                ValidationSeverity.SUCCESS,
                True,
                "Cache store/retrieve operations working",
                {"cache_time_ms": cache_time},
                cache_time,
            )
        else:
            self._add_result(
                component,
                "Cache Operations",
                ValidationSeverity.CRITICAL,
                False,
                "Cache operations failed",
            )

    async def validate_knowledge_base_caching(self) -> List[ValidationResult]:
        """Validate knowledge base caching system"""
        component = "Knowledge Base Cache"

        try:
            from utils.advanced_cache_manager import get_knowledge_cache

            # Test 1: Cache system initialization (Issue #620: uses helper)
            start_time = time.time()
            cache = get_knowledge_cache()
            init_time = (time.time() - start_time) * 1000

            if not self._validate_cache_initialization(component, cache, init_time):
                return self._get_component_results(component)

            # Test 2: Cache functionality (Issue #620: uses helper)
            await self._validate_cache_operations(component, cache)

            # Test 3: Cache statistics (uses helper)
            await self._validate_cache_stats(component, cache)

            # Test 4: Knowledge base integration (uses helper)
            await self._validate_kb_integration(component)

            # Cleanup test data
            await cache.clear_cache("*validation_test*")

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Knowledge base cache validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    def _validate_hybrid_search_results(
        self, component: str, search_results: List, search_time: float
    ) -> None:
        """Validate hybrid search results (Issue #333 - extracted helper)."""
        if not search_results:
            self._add_result(
                component,
                "Hybrid Search",
                ValidationSeverity.WARNING,
                False,
                "Hybrid search returned no results",
            )
            return

        has_hybrid_scores = any("hybrid_score" in result for result in search_results)
        has_keyword_scores = any("keyword_score" in result for result in search_results)

        if has_hybrid_scores and has_keyword_scores:
            severity = self._get_severity_for_response_time(search_time)
            self._add_result(
                component,
                "Hybrid Search",
                severity,
                True,
                f"Hybrid search working: {len(search_results)} results with scoring",
                {
                    "search_time_ms": search_time,
                    "result_count": len(search_results),
                    "has_hybrid_scores": has_hybrid_scores,
                    "has_keyword_scores": has_keyword_scores,
                },
                search_time,
            )
        else:
            self._add_result(
                component,
                "Hybrid Search",
                ValidationSeverity.WARNING,
                True,
                "Hybrid search working but missing enhanced scoring",
                {"search_time_ms": search_time, "result_count": len(search_results)},
            )

    async def _validate_search_explanation(self, component: str, hybrid_engine) -> None:
        """Validate search explanation (Issue #333 - extracted helper)."""
        try:
            explanation = await hybrid_engine.explain_search("test query", top_k=3)
            if "extracted_keywords" in explanation:
                self._add_result(
                    component,
                    "Search Explanation",
                    ValidationSeverity.SUCCESS,
                    True,
                    "Search explanation functionality working",
                    {"keywords_count": len(explanation.get("extracted_keywords", []))},
                )
            else:
                self._add_result(
                    component,
                    "Search Explanation",
                    ValidationSeverity.WARNING,
                    False,
                    "Search explanation missing keywords",
                )
        except Exception as e:
            self._add_result(
                component,
                "Search Explanation",
                ValidationSeverity.WARNING,
                False,
                f"Search explanation error: {str(e)}",
            )

    def _validate_system_metrics_result(
        self, component: str, system_metrics: Dict, collection_time: float
    ) -> None:
        """Validate system metrics collection result (Issue #380: use module constant)."""
        found_metrics = [
            name for name in _EXPECTED_SYSTEM_METRICS if name in system_metrics
        ]

        if len(found_metrics) != len(_EXPECTED_SYSTEM_METRICS):
            self._add_result(
                component,
                "System Metrics",
                ValidationSeverity.WARNING,
                False,
                f"Missing system metrics: {len(found_metrics)}/{len(_EXPECTED_SYSTEM_METRICS)}",
                {
                    "found_metrics": found_metrics,
                    "expected_metrics": list(_EXPECTED_SYSTEM_METRICS),
                },
            )
            return

        severity = (
            ValidationSeverity.SUCCESS
            if collection_time < 1000
            else ValidationSeverity.WARNING
        )
        self._add_result(
            component,
            "System Metrics",
            severity,
            True,
            f"All system metrics collected: {len(found_metrics)}/{len(_EXPECTED_SYSTEM_METRICS)}",
            {
                "collection_time_ms": collection_time,
                "metrics": list(system_metrics.keys()),
            },
            collection_time,
        )

    def _validate_service_health_result(
        self, component: str, health_metrics: Dict, health_time: float
    ) -> None:
        """Validate service health collection result (Issue #333 - extracted helper)."""
        service_count = len([k for k in health_metrics.keys() if "health" in k])

        if service_count >= 2:
            self._add_result(
                component,
                "Service Health",
                ValidationSeverity.SUCCESS,
                True,
                f"Service health metrics collected: {service_count} services",
                {"collection_time_ms": health_time, "services": service_count},
                health_time,
            )
        else:
            self._add_result(
                component,
                "Service Health",
                ValidationSeverity.WARNING,
                False,
                f"Limited service health coverage: {service_count} services",
            )

    def _validate_metrics_storage_result(
        self,
        component: str,
        storage_success: bool,
        all_metrics: Dict,
        storage_time: float,
    ) -> None:
        """Validate metrics storage result (Issue #333 - extracted helper)."""
        if storage_success:
            self._add_result(
                component,
                "Metrics Storage",
                ValidationSeverity.SUCCESS,
                True,
                f"Metrics storage working: {len(all_metrics)} metrics stored",
                {"storage_time_ms": storage_time, "metrics_count": len(all_metrics)},
                storage_time,
            )
        else:
            self._add_result(
                component,
                "Metrics Storage",
                ValidationSeverity.WARNING,
                False,
                "Metrics storage failed",
            )

    async def _validate_health_summary(self, component: str, collector) -> None:
        """Validate health summary (Issue #333 - extracted helper)."""
        try:
            summary = await collector.get_metric_summary()
            if "overall_health" not in summary:
                self._add_result(
                    component,
                    "Health Summary",
                    ValidationSeverity.INFO,
                    True,
                    "Health summary available without overall score",
                )
                return

            health_score = summary["overall_health"].get("value", 0)
            severity = (
                ValidationSeverity.SUCCESS
                if health_score > 80
                else ValidationSeverity.WARNING
            )
            self._add_result(
                component,
                "Health Summary",
                severity,
                True,
                f"System health summary available: {health_score}% health",
                {
                    "health_score": health_score,
                    "status": summary["overall_health"].get("status"),
                },
            )
        except Exception as e:
            self._add_result(
                component,
                "Health Summary",
                ValidationSeverity.WARNING,
                False,
                f"Health summary error: {str(e)}",
            )

    def _validate_model_discovery_result(
        self, component: str, models: List, discovery_time: float
    ) -> bool:
        """Validate model discovery result (Issue #333 - extracted helper).

        Returns:
            True if models are available and validation should continue
        """
        if models and len(models) >= 2:
            self._add_result(
                component,
                "Model Discovery",
                ValidationSeverity.SUCCESS,
                True,
                f"Models discovered: {len(models)} available",
                {
                    "discovery_time_ms": discovery_time,
                    "model_count": len(models),
                    "models": [m.name for m in models[:5]],
                },
                discovery_time,
            )
            return True

        if models and len(models) == 1:
            self._add_result(
                component,
                "Model Discovery",
                ValidationSeverity.WARNING,
                True,
                f"Limited models available: {len(models)}",
                {
                    "discovery_time_ms": discovery_time,
                    "models": [m.name for m in models],
                },
            )
            return True

        self._add_result(
            component,
            "Model Discovery",
            ValidationSeverity.CRITICAL,
            False,
            "No models discovered - is Ollama running?",
        )
        return False

    def _validate_complexity_analysis(
        self, component: str, optimizer, TaskComplexity, TaskRequest
    ) -> None:
        """Validate task complexity analysis (Issue #333 - extracted helper)."""
        test_cases = [
            ("What is 2+2?", TaskComplexity.SIMPLE),
            ("Explain machine learning algorithms", TaskComplexity.MODERATE),
            ("Design a microservices architecture", TaskComplexity.COMPLEX),
        ]

        correct_classifications = 0
        for query, expected_complexity in test_cases:
            task_request = TaskRequest(query=query, task_type="chat")
            actual_complexity = optimizer.analyze_task_complexity(task_request)
            if actual_complexity == expected_complexity:
                correct_classifications += 1

        accuracy = (correct_classifications / len(test_cases)) * 100
        severity = (
            ValidationSeverity.SUCCESS if accuracy >= 66 else ValidationSeverity.WARNING
        )
        self._add_result(
            component,
            "Complexity Analysis",
            severity,
            accuracy >= 50,
            f"Task complexity classification: {accuracy:.1f}% accuracy",
            {
                "accuracy": accuracy,
                "correct": correct_classifications,
                "total": len(test_cases),
            },
        )

    async def _validate_model_selection(
        self, component: str, optimizer, TaskRequest
    ) -> str | None:
        """Validate model selection (Issue #333 - extracted helper).

        Returns:
            Selected model name or None if selection failed
        """
        start_time = time.time()
        task_request = TaskRequest(
            query="Write a Python function to sort a list",
            task_type="code",
            max_response_time=30.0,
        )
        selected_model = await optimizer.select_optimal_model(task_request)
        selection_time = (time.time() - start_time) * 1000

        if selected_model:
            self._add_result(
                component,
                "Model Selection",
                ValidationSeverity.SUCCESS,
                True,
                f"Model selection working: {selected_model}",
                {"selection_time_ms": selection_time, "selected_model": selected_model},
                selection_time,
            )
        else:
            self._add_result(
                component,
                "Model Selection",
                ValidationSeverity.WARNING,
                False,
                "Model selection returned no result",
            )
        return selected_model

    async def _validate_performance_tracking(
        self, component: str, optimizer, model_name: str
    ) -> None:
        """Validate performance tracking (Issue #333 - extracted helper)."""
        try:
            await optimizer.track_model_performance(
                model_name=model_name,
                response_time=2.5,
                response_tokens=150,
                success=True,
            )
            self._add_result(
                component,
                "Performance Tracking",
                ValidationSeverity.SUCCESS,
                True,
                "Model performance tracking working",
            )
        except Exception as e:
            self._add_result(
                component,
                "Performance Tracking",
                ValidationSeverity.WARNING,
                False,
                f"Performance tracking error: {str(e)}",
            )

    async def _validate_optimization_suggestions(
        self, component: str, optimizer
    ) -> None:
        """Validate optimization suggestions (Issue #333 - extracted helper)."""
        try:
            suggestions = await optimizer.get_optimization_suggestions()
            self._add_result(
                component,
                "Optimization Suggestions",
                ValidationSeverity.SUCCESS,
                True,
                f"Optimization suggestions generated: {len(suggestions)}",
                {"suggestion_count": len(suggestions)},
            )
        except Exception as e:
            self._add_result(
                component,
                "Optimization Suggestions",
                ValidationSeverity.WARNING,
                False,
                f"Optimization suggestions error: {str(e)}",
            )

    def _record_endpoint_error_response(
        self, component: str, name: str, status: int, response_time: float
    ) -> None:
        """
        Record an API endpoint error response (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            name: Endpoint name
            status: HTTP status code
            response_time: Response time in milliseconds
        """
        self._add_result(
            component,
            name,
            ValidationSeverity.WARNING,
            False,
            f"API endpoint error: HTTP {status}",
            {"response_time_ms": response_time, "status_code": status},
        )

    async def _record_endpoint_success(
        self, component: str, name: str, response, response_time: float
    ) -> None:
        """
        Record a successful API endpoint response (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            name: Endpoint name
            response: aiohttp response object
            response_time: Response time in milliseconds
        """
        data = await response.json()
        severity = self._get_severity_for_response_time(response_time)
        self._add_result(
            component,
            name,
            severity,
            True,
            f"API endpoint responding: {response.status}",
            {
                "response_time_ms": response_time,
                "status_code": response.status,
                "response_size": len(str(data)),
            },
            response_time,
        )

    async def _validate_single_endpoint(
        self, component: str, http_client, method: str, url: str, name: str
    ) -> None:
        """Validate a single API endpoint (Issue #333, #620 - uses extracted helpers)."""
        start_time = time.time()
        try:
            if method != "GET":
                return  # Only GET supported in this validator

            async with await http_client.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response_time = (time.time() - start_time) * 1000

                if response.status != 200:
                    self._record_endpoint_error_response(
                        component, name, response.status, response_time
                    )
                    return

                await self._record_endpoint_success(
                    component, name, response, response_time
                )

        except asyncio.TimeoutError:
            self._add_result(
                component,
                name,
                ValidationSeverity.CRITICAL,
                False,
                "API endpoint timeout",
                {"timeout_seconds": 10},
            )
        except Exception as e:
            self._add_result(
                component,
                name,
                ValidationSeverity.CRITICAL,
                False,
                f"API endpoint error: {str(e)}",
            )

    def _validate_cpu_usage(self, component: str) -> None:
        """Validate CPU usage (Issue #333 - extracted helper)."""
        cpu_percent = psutil.cpu_percent(interval=1.0)
        threshold = self.critical_thresholds["cpu_usage_percent"]

        if cpu_percent >= threshold:
            self._add_result(
                component,
                "CPU Usage",
                ValidationSeverity.WARNING,
                False,
                f"High CPU usage: {cpu_percent:.1f}%",
                {"cpu_percent": cpu_percent, "threshold": threshold},
            )
            return

        severity = (
            ValidationSeverity.SUCCESS if cpu_percent < 70 else ValidationSeverity.INFO
        )
        self._add_result(
            component,
            "CPU Usage",
            severity,
            True,
            f"CPU usage acceptable: {cpu_percent:.1f}%",
            {"cpu_percent": cpu_percent, "threshold": threshold},
        )

    def _validate_memory_usage(self, component: str) -> None:
        """Validate memory usage (Issue #333 - extracted helper)."""
        memory = psutil.virtual_memory()
        threshold = self.critical_thresholds["memory_usage_percent"]

        if memory.percent >= threshold:
            self._add_result(
                component,
                "Memory Usage",
                ValidationSeverity.WARNING,
                False,
                f"High memory usage: {memory.percent:.1f}%",
                {
                    "memory_percent": memory.percent,
                    "available_gb": memory.available / (1024**3),
                },
            )
            return

        severity = (
            ValidationSeverity.SUCCESS
            if memory.percent < 80
            else ValidationSeverity.INFO
        )
        self._add_result(
            component,
            "Memory Usage",
            severity,
            True,
            f"Memory usage acceptable: {memory.percent:.1f}%",
            {
                "memory_percent": memory.percent,
                "available_gb": memory.available / (1024**3),
                "threshold": threshold,
            },
        )

    def _validate_disk_usage(self, component: str) -> None:
        """Validate disk usage (Issue #333 - extracted helper)."""
        disk = psutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100

        if disk_percent >= 85:
            severity = (
                ValidationSeverity.CRITICAL
                if disk_percent > 95
                else ValidationSeverity.WARNING
            )
            self._add_result(
                component,
                "Disk Usage",
                severity,
                False,
                f"High disk usage: {disk_percent:.1f}%",
                {"disk_percent": disk_percent, "free_gb": disk.free / (1024**3)},
            )
            return

        severity = (
            ValidationSeverity.SUCCESS if disk_percent < 70 else ValidationSeverity.INFO
        )
        self._add_result(
            component,
            "Disk Usage",
            severity,
            True,
            f"Disk usage acceptable: {disk_percent:.1f}%",
            {"disk_percent": disk_percent, "free_gb": disk.free / (1024**3)},
        )

    def _validate_network_connectivity(self, component: str) -> None:
        """Validate network connectivity (Issue #333 - extracted helper)."""
        import socket

        try:
            socket.create_connection((NetworkConstants.PUBLIC_DNS_IP, 53), timeout=3)
            self._add_result(
                component,
                "Network Connectivity",
                ValidationSeverity.SUCCESS,
                True,
                "Network connectivity available",
            )
        except Exception:
            self._add_result(
                component,
                "Network Connectivity",
                ValidationSeverity.WARNING,
                False,
                "Limited network connectivity",
            )

    def _validate_service_ports(self, component: str) -> None:
        """Validate service ports availability (Issue #333 - extracted helper)."""
        import socket

        critical_ports = [
            (config.get_host("backend"), config.get_port("backend"), "Backend"),
            (config.get_host("redis"), config.get_port("redis"), "Redis"),
            (config.get_host("ollama"), config.get_port("ollama"), "Ollama"),
        ]

        for host, port, service_name in critical_ports:
            try:
                with socket.create_connection((host, port), timeout=3):
                    self._add_result(
                        component,
                        f"{service_name} Port",
                        ValidationSeverity.SUCCESS,
                        True,
                        f"{service_name} service port accessible: {host}:{port}",
                    )
            except Exception:
                self._add_result(
                    component,
                    f"{service_name} Port",
                    ValidationSeverity.CRITICAL,
                    False,
                    f"{service_name} service port inaccessible: {host}:{port}",
                )

    async def _init_hybrid_search_engine(self, component: str):
        """
        Initialize KB and hybrid search engine (Issue #620: extracted helper).

        Args:
            component: Component name for result logging

        Returns:
            Tuple of (hybrid_engine, init_time_ms) or (None, 0) if failed
        """
        from knowledge_base import KnowledgeBase
        from utils.hybrid_search import get_hybrid_search_engine

        start_time = time.time()
        kb = KnowledgeBase()
        await kb.ainit()

        if not kb.index:
            self._add_result(
                component,
                "Prerequisites",
                ValidationSeverity.WARNING,
                False,
                "Knowledge base not available for hybrid search testing",
            )
            return None, 0

        hybrid_engine = get_hybrid_search_engine(kb)
        init_time = (time.time() - start_time) * 1000

        self._add_result(
            component,
            "Engine Initialization",
            ValidationSeverity.SUCCESS,
            True,
            "Hybrid search engine initialized",
            {"init_time_ms": init_time},
            init_time,
        )
        return hybrid_engine, init_time

    def _validate_keyword_extraction(self, component: str, hybrid_engine) -> None:
        """
        Validate keyword extraction for test queries (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            hybrid_engine: Hybrid search engine instance
        """
        test_queries = [
            "How to implement machine learning algorithms in Python?",
            "Database design best practices for web applications",
            "Docker container orchestration with Kubernetes",
        ]

        for query in test_queries:
            keywords = hybrid_engine.extract_keywords(query)
            if keywords and len(keywords) >= 2:
                self._add_result(
                    component,
                    "Keyword Extraction",
                    ValidationSeverity.SUCCESS,
                    True,
                    f"Keywords extracted: {len(keywords)} from query",
                    {"query": query[:50] + "...", "keywords": keywords},
                )
            else:
                self._add_result(
                    component,
                    "Keyword Extraction",
                    ValidationSeverity.WARNING,
                    False,
                    f"Poor keyword extraction: {len(keywords) if keywords else 0} keywords",
                    {"query": query[:50] + "...", "keywords": keywords},
                )

    async def validate_hybrid_search(self) -> List[ValidationResult]:
        """Validate hybrid search functionality"""
        component = "Hybrid Search"

        try:
            # Test 1: Hybrid search engine initialization (Issue #620: uses helper)
            hybrid_engine, _ = await self._init_hybrid_search_engine(component)
            if not hybrid_engine:
                return self._get_component_results(component)

            # Test 2: Keyword extraction (Issue #620: uses helper)
            self._validate_keyword_extraction(component, hybrid_engine)

            # Test 3: Hybrid search execution (uses helper)
            start_time = time.time()
            search_results = await hybrid_engine.search(
                "Python programming tutorial", top_k=5
            )
            search_time = (time.time() - start_time) * 1000
            self._validate_hybrid_search_results(component, search_results, search_time)

            # Test 4: Search explanation (uses helper)
            await self._validate_search_explanation(component, hybrid_engine)

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Hybrid search validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    def _validate_collector_init(
        self, component: str, collector, init_time: float
    ) -> None:
        """
        Record metrics collector initialization result.

        Args:
            component: Component name for result logging
            collector: Metrics collector instance
            init_time: Initialization time in milliseconds

        Issue #620.
        """
        self._add_result(
            component,
            "Collector Initialization",
            ValidationSeverity.SUCCESS,
            True,
            "Metrics collector initialized",
            {"init_time_ms": init_time},
            init_time,
        )

    async def _run_monitoring_validation_tests(self, component: str, collector) -> None:
        """
        Run all monitoring system validation tests.

        Executes tests for system metrics, service health, storage, and summary. Issue #620.
        """
        # Test 2: System metrics collection
        start_time = time.time()
        system_metrics = await collector.collect_system_metrics()
        collection_time = (time.time() - start_time) * 1000
        self._validate_system_metrics_result(component, system_metrics, collection_time)

        # Test 3: Service health collection
        start_time = time.time()
        health_metrics = await collector.collect_service_health()
        health_time = (time.time() - start_time) * 1000
        self._validate_service_health_result(component, health_metrics, health_time)

        # Test 4: Metrics storage
        start_time = time.time()
        all_metrics = await collector.collect_all_metrics()
        storage_success = await collector.store_metrics(all_metrics)
        storage_time = (time.time() - start_time) * 1000
        self._validate_metrics_storage_result(
            component, storage_success, all_metrics, storage_time
        )

        # Test 5: Metrics summary
        await self._validate_health_summary(component, collector)

    async def validate_monitoring_system(self) -> List[ValidationResult]:
        """Validate monitoring and metrics system."""
        component = "Monitoring System"

        try:
            from utils.system_metrics import get_metrics_collector

            # Test 1: Metrics collector initialization
            start_time = time.time()
            collector = get_metrics_collector()
            init_time = (time.time() - start_time) * 1000
            self._validate_collector_init(component, collector, init_time)

            # Run remaining validation tests
            await self._run_monitoring_validation_tests(component, collector)

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Monitoring system validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    def _validate_optimizer_init(
        self, component: str, optimizer, init_time: float
    ) -> None:
        """
        Record optimizer initialization result (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            optimizer: Model optimizer instance
            init_time: Initialization time in milliseconds
        """
        self._add_result(
            component,
            "Optimizer Initialization",
            ValidationSeverity.SUCCESS,
            True,
            "Model optimizer initialized",
            {"init_time_ms": init_time},
            init_time,
        )

    async def _validate_model_discovery(self, component: str, optimizer) -> bool:
        """
        Validate model discovery and return availability (Issue #620: extracted helper).

        Args:
            component: Component name for result logging
            optimizer: Model optimizer instance

        Returns:
            True if models are available, False otherwise
        """
        start_time = time.time()
        models = await optimizer.refresh_available_models()
        discovery_time = (time.time() - start_time) * 1000

        return self._validate_model_discovery_result(component, models, discovery_time)

    async def validate_model_optimization(self) -> List[ValidationResult]:
        """Validate model optimization system"""
        component = "Model Optimization"

        try:
            from utils.model_optimizer import (
                TaskComplexity,
                TaskRequest,
                get_model_optimizer,
            )

            # Test 1: Model optimizer initialization (Issue #620: uses helper)
            start_time = time.time()
            optimizer = get_model_optimizer()
            init_time = (time.time() - start_time) * 1000
            self._validate_optimizer_init(component, optimizer, init_time)

            # Test 2: Model discovery (Issue #620: uses helper)
            if not await self._validate_model_discovery(component, optimizer):
                return self._get_component_results(component)

            # Test 3: Task complexity analysis (uses helper)
            self._validate_complexity_analysis(
                component, optimizer, TaskComplexity, TaskRequest
            )

            # Test 4: Model selection (uses helper)
            selected_model = await self._validate_model_selection(
                component, optimizer, TaskRequest
            )

            # Test 5: Performance tracking (uses helper)
            if selected_model:
                await self._validate_performance_tracking(
                    component, optimizer, selected_model
                )

            # Test 6: Optimization suggestions (uses helper)
            await self._validate_optimization_suggestions(component, optimizer)

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Model optimization validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    def _get_critical_api_endpoints(self) -> List[tuple]:
        """
        Get the list of critical API endpoints to validate.

        Returns:
            List of tuples containing (method, url, name) for each endpoint

        Issue #620.
        """
        backend_url = self.base_urls["backend"]
        return [
            ("GET", f"{backend_url}/api/knowledge_base/cache/stats", "Cache Stats"),
            ("GET", f"{backend_url}/api/knowledge_base/cache/health", "Cache Health"),
            ("GET", f"{backend_url}/api/knowledge_base/search/config", "Search Config"),
            ("GET", f"{backend_url}/api/monitoring/health", "Monitoring Health"),
            (
                "GET",
                f"{backend_url}/api/monitoring/dashboard/overview",
                "Dashboard Overview",
            ),
            (
                "GET",
                f"{backend_url}/api/llm_optimization/health",
                "Optimization Health",
            ),
            (
                "GET",
                f"{backend_url}/api/llm_optimization/models/available",
                "Available Models",
            ),
        ]

    async def validate_api_endpoints(self) -> List[ValidationResult]:
        """
        Validate all optimization API endpoints.

        (Issue #620: refactored to use extracted helper)
        """
        component = "API Endpoints"
        endpoints = self._get_critical_api_endpoints()

        try:
            http_client = get_http_client()
            for method, url, name in endpoints:
                await self._validate_single_endpoint(
                    component, http_client, method, url, name
                )

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"API endpoint validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    async def validate_system_resources(self) -> List[ValidationResult]:
        """Validate system resource availability and performance"""
        component = "System Resources"

        try:
            # Test 1: CPU usage (uses helper)
            self._validate_cpu_usage(component)

            # Test 2: Memory usage (uses helper)
            self._validate_memory_usage(component)

            # Test 3: Disk usage (uses helper)
            self._validate_disk_usage(component)

            # Test 4: Network connectivity (uses helper)
            self._validate_network_connectivity(component)

            # Test 5: Service ports availability (uses helper)
            self._validate_service_ports(component)

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"System resource validation failed: {str(e)}",
            )

        return self._get_component_results(component)

    def _calculate_validation_statistics(self) -> Dict[str, int]:
        """
        Calculate validation statistics from results (Issue #665: extracted helper).

        Returns:
            Dict with total_tests, passed_tests, failed_tests, critical_issues, warnings
        """
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.status)
        critical_issues = sum(
            1
            for r in self.results
            if r.severity == ValidationSeverity.CRITICAL and not r.status
        )
        warnings = sum(
            1
            for r in self.results
            if r.severity == ValidationSeverity.WARNING and not r.status
        )
        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "critical_issues": critical_issues,
            "warnings": warnings,
        }

    def _calculate_health_score(self, stats: Dict[str, int]) -> float:
        """
        Calculate overall health score with penalties (Issue #665: extracted helper).

        Args:
            stats: Validation statistics dict

        Returns:
            Health score from 0 to 100
        """
        if stats["total_tests"] == 0:
            return 0.0
        base_score = (stats["passed_tests"] / stats["total_tests"]) * 100
        critical_penalty = stats["critical_issues"] * 20
        warning_penalty = stats["warnings"] * 5
        return max(0, base_score - critical_penalty - warning_penalty)

    def _calculate_performance_metrics(self, total_duration: float) -> Dict[str, float]:
        """
        Calculate performance metrics from results (Issue #665: extracted helper).

        Args:
            total_duration: Total validation time in seconds

        Returns:
            Dict with timing metrics
        """
        valid_durations = [r.duration_ms for r in self.results if r.duration_ms > 0]
        avg_response_time = (
            sum(valid_durations) / len(valid_durations) if valid_durations else 0
        )
        return {
            "total_validation_time_seconds": round(total_duration, 2),
            "average_response_time_ms": round(avg_response_time, 2),
            "fastest_test_ms": min(valid_durations, default=0),
            "slowest_test_ms": max(valid_durations, default=0),
        }

    async def run_comprehensive_validation(self) -> SystemValidationReport:
        """
        Run all validation tests and generate comprehensive report.

        Issue #665: Refactored to use extracted helper methods for
        statistics, health score, and performance metric calculation.
        """
        self.logger.info("🔍 Starting comprehensive system validation...")
        start_time = time.time()

        # Clear previous results
        self.results = []

        # Run all validation components
        validation_tasks = [
            self.validate_knowledge_base_caching(),
            self.validate_hybrid_search(),
            self.validate_monitoring_system(),
            self.validate_model_optimization(),
            self.validate_api_endpoints(),
            self.validate_system_resources(),
        ]

        # Execute validations concurrently
        await asyncio.gather(*validation_tasks, return_exceptions=True)

        # Calculate statistics using helpers (Issue #665)
        total_duration = time.time() - start_time
        stats = self._calculate_validation_statistics()
        overall_health_score = self._calculate_health_score(stats)
        system_ready = stats["critical_issues"] == 0 and overall_health_score >= 70
        performance_metrics = self._calculate_performance_metrics(total_duration)

        report = SystemValidationReport(
            timestamp=time.time(),
            total_tests=stats["total_tests"],
            passed_tests=stats["passed_tests"],
            failed_tests=stats["failed_tests"],
            critical_issues=stats["critical_issues"],
            warnings=stats["warnings"],
            overall_health_score=round(overall_health_score, 1),
            system_ready=system_ready,
            validation_results=self.results,
            recommendations=self._generate_recommendations(),
            performance_metrics=performance_metrics,
        )

        self.logger.info(
            f"✅ Validation completed: {stats['passed_tests']}/{stats['total_tests']} tests passed, "
            f"Health Score: {overall_health_score:.1f}%, Ready: {system_ready}"
        )

        return report

    def _build_critical_recommendations(self, recommendations: List[str]) -> None:
        """
        Add recommendations for critical issues to the list.

        Finds critical validation failures and adds deployment warnings. Issue #620.
        """
        critical_results = [
            r
            for r in self.results
            if r.severity == ValidationSeverity.CRITICAL and not r.status
        ]
        if critical_results:
            recommendations.append(
                f"CRITICAL: Address {len(critical_results)} critical issues before production deployment"
            )
            for result in critical_results[:3]:  # Show first 3
                recommendations.append(f"  - {result.component}: {result.message}")

    def _build_performance_recommendations(self, recommendations: List[str]) -> None:
        """
        Add recommendations for performance issues to the list.

        Identifies operations exceeding response time threshold. Issue #620.
        """
        slow_tests = [
            r
            for r in self.results
            if r.duration_ms > self.critical_thresholds["response_time_ms"]
        ]
        if slow_tests:
            threshold = self.critical_thresholds["response_time_ms"]
            recommendations.append(
                f"PERFORMANCE: {len(slow_tests)} operations are slower than {threshold}ms"
            )

    def _build_component_recommendations(self, recommendations: List[str]) -> None:
        """
        Add recommendations for component-specific failures to the list.

        Identifies component with most failures and suggests prioritization. Issue #620.
        """
        failed_by_component: Dict[str, int] = {}
        for result in self.results:
            if not result.status:
                component = result.component
                failed_by_component[component] = (
                    failed_by_component.get(component, 0) + 1
                )

        if failed_by_component:
            worst_component = max(failed_by_component.items(), key=lambda x: x[1])
            recommendations.append(
                f"FOCUS: '{worst_component[0]}' has {worst_component[1]} failing tests - prioritize fixes here"
            )

    def _build_success_recommendations(self, recommendations: List[str]) -> None:
        """
        Add success acknowledgments to the recommendations list.

        Counts passing tests and adds positive feedback. Issue #620.
        """
        success_count = sum(1 for r in self.results if r.status)
        if success_count > 0:
            recommendations.append(
                f"POSITIVE: {success_count} tests are passing successfully"
            )

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on validation results."""
        recommendations: List[str] = []

        self._build_critical_recommendations(recommendations)
        self._build_performance_recommendations(recommendations)
        self._build_component_recommendations(recommendations)
        self._build_success_recommendations(recommendations)

        # Overall system health - only if no other recommendations
        if not recommendations:
            recommendations.append("EXCELLENT: All systems are operating optimally")

        return recommendations


# Global validator instance (thread-safe)
import threading

_system_validator = None
_system_validator_lock = threading.Lock()


def get_system_validator() -> SystemValidator:
    """Get the global system validator instance (thread-safe)"""
    global _system_validator
    if _system_validator is None:
        with _system_validator_lock:
            # Double-check after acquiring lock
            if _system_validator is None:
                _system_validator = SystemValidator()
    return _system_validator
