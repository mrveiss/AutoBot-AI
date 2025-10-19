"""
Comprehensive System Validation
Validates all optimization components and their integration for production readiness.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import psutil

from src.config_helper import cfg
from src.constants.network_constants import NetworkConstants


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
        self.logger = logging.getLogger(__name__)
        self.results: List[ValidationResult] = []

        # Validation configuration
        self.timeout_seconds = cfg.get("validation.timeout_seconds", 30)
        self.critical_thresholds = {
            "response_time_ms": cfg.get("validation.thresholds.response_time_ms", 5000),
            "cache_hit_rate": cfg.get("validation.thresholds.cache_hit_rate", 50.0),
            "memory_usage_percent": cfg.get(
                "validation.thresholds.memory_usage_percent", 90.0
            ),
            "cpu_usage_percent": cfg.get(
                "validation.thresholds.cpu_usage_percent", 95.0
            ),
            "error_rate_percent": cfg.get(
                "validation.thresholds.error_rate_percent", 5.0
            ),
        }

        # Service endpoints
        self.base_urls = {
            "backend": f"http://{cfg.get_host('backend')}:{cfg.get_port('backend')}",
            "frontend": f"http://{cfg.get_host('frontend')}:{cfg.get_port('frontend')}",
            "ollama": f"http://{cfg.get_host('ollama')}:{cfg.get_port('ollama')}",
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

    async def validate_knowledge_base_caching(self) -> List[ValidationResult]:
        """Validate knowledge base caching system"""
        component = "Knowledge Base Cache"
        results = []

        try:
            from src.knowledge_base import KnowledgeBase
            from src.utils.knowledge_cache import get_knowledge_cache

            # Test 1: Cache system initialization
            start_time = time.time()
            cache = get_knowledge_cache()
            init_time = (time.time() - start_time) * 1000

            if cache:
                self._add_result(
                    component,
                    "Cache Initialization",
                    ValidationSeverity.SUCCESS,
                    True,
                    "Cache system initialized successfully",
                    {"init_time_ms": init_time},
                    init_time,
                )
            else:
                self._add_result(
                    component,
                    "Cache Initialization",
                    ValidationSeverity.CRITICAL,
                    False,
                    "Failed to initialize cache system",
                )
                return results

            # Test 2: Cache functionality
            start_time = time.time()
            test_results = [{"test": "data", "score": 0.95}]
            cache_success = await cache.cache_results(
                "validation_test", 5, test_results
            )
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

            # Test 3: Cache statistics
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

            # Test 4: Knowledge base integration
            try:
                kb = KnowledgeBase()
                await kb.ainit()

                if kb.index:
                    start_time = time.time()
                    search_results = await kb.search("validation test query", top_k=3)
                    search_time = (time.time() - start_time) * 1000

                    if search_results:
                        severity = (
                            ValidationSeverity.SUCCESS
                            if search_time
                            < self.critical_thresholds["response_time_ms"]
                            else ValidationSeverity.WARNING
                        )
                        self._add_result(
                            component,
                            "KB Integration",
                            severity,
                            True,
                            f"Knowledge base search working: {len(search_results)} results",
                            {
                                "search_time_ms": search_time,
                                "result_count": len(search_results),
                            },
                            search_time,
                        )
                    else:
                        self._add_result(
                            component,
                            "KB Integration",
                            ValidationSeverity.WARNING,
                            True,
                            "Knowledge base search returned no results",
                        )
                else:
                    self._add_result(
                        component,
                        "KB Integration",
                        ValidationSeverity.WARNING,
                        False,
                        "Knowledge base index not available",
                    )
            except Exception as e:
                self._add_result(
                    component,
                    "KB Integration",
                    ValidationSeverity.WARNING,
                    False,
                    f"Knowledge base integration error: {str(e)}",
                )

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

        return [r for r in self.results if r.component == component]

    async def validate_hybrid_search(self) -> List[ValidationResult]:
        """Validate hybrid search functionality"""
        component = "Hybrid Search"

        try:
            from src.knowledge_base import KnowledgeBase
            from src.utils.hybrid_search import get_hybrid_search_engine

            # Test 1: Hybrid search engine initialization
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
                return [r for r in self.results if r.component == component]

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

            # Test 2: Keyword extraction
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
                        f"Poor keyword extraction: {len(keywords)} keywords",
                        {"query": query[:50] + "...", "keywords": keywords},
                    )

            # Test 3: Hybrid search execution
            start_time = time.time()
            search_results = await hybrid_engine.search(
                "Python programming tutorial", top_k=5
            )
            search_time = (time.time() - start_time) * 1000

            if search_results:
                # Check for hybrid scoring
                has_hybrid_scores = any(
                    "hybrid_score" in result for result in search_results
                )
                has_keyword_scores = any(
                    "keyword_score" in result for result in search_results
                )

                if has_hybrid_scores and has_keyword_scores:
                    severity = (
                        ValidationSeverity.SUCCESS
                        if search_time < self.critical_thresholds["response_time_ms"]
                        else ValidationSeverity.WARNING
                    )
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
                        {
                            "search_time_ms": search_time,
                            "result_count": len(search_results),
                        },
                    )
            else:
                self._add_result(
                    component,
                    "Hybrid Search",
                    ValidationSeverity.WARNING,
                    False,
                    "Hybrid search returned no results",
                )

            # Test 4: Search explanation
            try:
                explanation = await hybrid_engine.explain_search("test query", top_k=3)
                if "extracted_keywords" in explanation:
                    self._add_result(
                        component,
                        "Search Explanation",
                        ValidationSeverity.SUCCESS,
                        True,
                        "Search explanation functionality working",
                        {
                            "keywords_count": len(
                                explanation.get("extracted_keywords", [])
                            )
                        },
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

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Hybrid search validation failed: {str(e)}",
            )

        return [r for r in self.results if r.component == component]

    async def validate_monitoring_system(self) -> List[ValidationResult]:
        """Validate monitoring and metrics system"""
        component = "Monitoring System"

        try:
            from src.utils.system_metrics import get_metrics_collector

            # Test 1: Metrics collector initialization
            start_time = time.time()
            collector = get_metrics_collector()
            init_time = (time.time() - start_time) * 1000

            self._add_result(
                component,
                "Collector Initialization",
                ValidationSeverity.SUCCESS,
                True,
                "Metrics collector initialized",
                {"init_time_ms": init_time},
                init_time,
            )

            # Test 2: System metrics collection
            start_time = time.time()
            system_metrics = await collector.collect_system_metrics()
            collection_time = (time.time() - start_time) * 1000

            expected_metrics = ["cpu_percent", "memory_percent", "disk_usage"]
            found_metrics = [
                name for name in expected_metrics if name in system_metrics
            ]

            if len(found_metrics) == len(expected_metrics):
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
                    f"All system metrics collected: {len(found_metrics)}/{len(expected_metrics)}",
                    {
                        "collection_time_ms": collection_time,
                        "metrics": list(system_metrics.keys()),
                    },
                    collection_time,
                )
            else:
                self._add_result(
                    component,
                    "System Metrics",
                    ValidationSeverity.WARNING,
                    False,
                    f"Missing system metrics: {len(found_metrics)}/{len(expected_metrics)}",
                    {
                        "found_metrics": found_metrics,
                        "expected_metrics": expected_metrics,
                    },
                )

            # Test 3: Service health collection
            start_time = time.time()
            health_metrics = await collector.collect_service_health()
            health_time = (time.time() - start_time) * 1000

            service_count = len([k for k in health_metrics.keys() if "health" in k])
            if service_count >= 2:  # At least backend and redis health
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

            # Test 4: Metrics storage
            start_time = time.time()
            all_metrics = await collector.collect_all_metrics()
            storage_success = await collector.store_metrics(all_metrics)
            storage_time = (time.time() - start_time) * 1000

            if storage_success:
                self._add_result(
                    component,
                    "Metrics Storage",
                    ValidationSeverity.SUCCESS,
                    True,
                    f"Metrics storage working: {len(all_metrics)} metrics stored",
                    {
                        "storage_time_ms": storage_time,
                        "metrics_count": len(all_metrics),
                    },
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

            # Test 5: Metrics summary
            try:
                summary = await collector.get_metric_summary()
                if "overall_health" in summary:
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
                else:
                    self._add_result(
                        component,
                        "Health Summary",
                        ValidationSeverity.INFO,
                        True,
                        "Health summary available without overall score",
                    )
            except Exception as e:
                self._add_result(
                    component,
                    "Health Summary",
                    ValidationSeverity.WARNING,
                    False,
                    f"Health summary error: {str(e)}",
                )

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Monitoring system validation failed: {str(e)}",
            )

        return [r for r in self.results if r.component == component]

    async def validate_model_optimization(self) -> List[ValidationResult]:
        """Validate model optimization system"""
        component = "Model Optimization"

        try:
            from src.utils.model_optimizer import (
                TaskComplexity,
                TaskRequest,
                get_model_optimizer,
            )

            # Test 1: Model optimizer initialization
            start_time = time.time()
            optimizer = get_model_optimizer()
            init_time = (time.time() - start_time) * 1000

            self._add_result(
                component,
                "Optimizer Initialization",
                ValidationSeverity.SUCCESS,
                True,
                "Model optimizer initialized",
                {"init_time_ms": init_time},
                init_time,
            )

            # Test 2: Model discovery
            start_time = time.time()
            models = await optimizer.refresh_available_models()
            discovery_time = (time.time() - start_time) * 1000

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
            elif models and len(models) == 1:
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
            else:
                self._add_result(
                    component,
                    "Model Discovery",
                    ValidationSeverity.CRITICAL,
                    False,
                    "No models discovered - is Ollama running?",
                )
                return [r for r in self.results if r.component == component]

            # Test 3: Task complexity analysis
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
                ValidationSeverity.SUCCESS
                if accuracy >= 66
                else ValidationSeverity.WARNING
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

            # Test 4: Model selection
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
                    {
                        "selection_time_ms": selection_time,
                        "selected_model": selected_model,
                    },
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

            # Test 5: Performance tracking
            if selected_model:
                try:
                    await optimizer.track_model_performance(
                        model_name=selected_model,
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

            # Test 6: Optimization suggestions
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

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"Model optimization validation failed: {str(e)}",
            )

        return [r for r in self.results if r.component == component]

    async def validate_api_endpoints(self) -> List[ValidationResult]:
        """Validate all optimization API endpoints"""
        component = "API Endpoints"

        # Critical API endpoints to test
        endpoints = [
            # Knowledge base cache endpoints
            (
                "GET",
                f"{self.base_urls['backend']}/api/knowledge_base/cache/stats",
                "Cache Stats",
            ),
            (
                "GET",
                f"{self.base_urls['backend']}/api/knowledge_base/cache/health",
                "Cache Health",
            ),
            # Hybrid search endpoints
            (
                "GET",
                f"{self.base_urls['backend']}/api/knowledge_base/search/config",
                "Search Config",
            ),
            # Monitoring endpoints
            (
                "GET",
                f"{self.base_urls['backend']}/api/monitoring/health",
                "Monitoring Health",
            ),
            (
                "GET",
                f"{self.base_urls['backend']}/api/monitoring/dashboard/overview",
                "Dashboard Overview",
            ),
            # Model optimization endpoints
            (
                "GET",
                f"{self.base_urls['backend']}/api/llm_optimization/health",
                "Optimization Health",
            ),
            (
                "GET",
                f"{self.base_urls['backend']}/api/llm_optimization/models/available",
                "Available Models",
            ),
        ]

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                for method, url, name in endpoints:
                    start_time = time.time()
                    try:
                        if method == "GET":
                            async with session.get(url) as response:
                                response_time = (time.time() - start_time) * 1000

                                if response.status == 200:
                                    data = await response.json()
                                    severity = (
                                        ValidationSeverity.SUCCESS
                                        if response_time
                                        < self.critical_thresholds["response_time_ms"]
                                        else ValidationSeverity.WARNING
                                    )
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
                                else:
                                    self._add_result(
                                        component,
                                        name,
                                        ValidationSeverity.WARNING,
                                        False,
                                        f"API endpoint error: HTTP {response.status}",
                                        {
                                            "response_time_ms": response_time,
                                            "status_code": response.status,
                                        },
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

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"API endpoint validation failed: {str(e)}",
            )

        return [r for r in self.results if r.component == component]

    async def validate_system_resources(self) -> List[ValidationResult]:
        """Validate system resource availability and performance"""
        component = "System Resources"

        try:
            # Test 1: CPU usage
            cpu_percent = psutil.cpu_percent(interval=1.0)
            if cpu_percent < self.critical_thresholds["cpu_usage_percent"]:
                severity = (
                    ValidationSeverity.SUCCESS
                    if cpu_percent < 70
                    else ValidationSeverity.INFO
                )
                self._add_result(
                    component,
                    "CPU Usage",
                    severity,
                    True,
                    f"CPU usage acceptable: {cpu_percent:.1f}%",
                    {
                        "cpu_percent": cpu_percent,
                        "threshold": self.critical_thresholds["cpu_usage_percent"],
                    },
                )
            else:
                self._add_result(
                    component,
                    "CPU Usage",
                    ValidationSeverity.WARNING,
                    False,
                    f"High CPU usage: {cpu_percent:.1f}%",
                    {
                        "cpu_percent": cpu_percent,
                        "threshold": self.critical_thresholds["cpu_usage_percent"],
                    },
                )

            # Test 2: Memory usage
            memory = psutil.virtual_memory()
            if memory.percent < self.critical_thresholds["memory_usage_percent"]:
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
                        "threshold": self.critical_thresholds["memory_usage_percent"],
                    },
                )
            else:
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

            # Test 3: Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent < 85:
                severity = (
                    ValidationSeverity.SUCCESS
                    if disk_percent < 70
                    else ValidationSeverity.INFO
                )
                self._add_result(
                    component,
                    "Disk Usage",
                    severity,
                    True,
                    f"Disk usage acceptable: {disk_percent:.1f}%",
                    {"disk_percent": disk_percent, "free_gb": disk.free / (1024**3)},
                )
            else:
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

            # Test 4: Network connectivity
            import socket

            try:
                socket.create_connection(("8.8.8.8", 53), timeout=3)
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

            # Test 5: Service ports availability
            critical_ports = [
                (cfg.get_host("backend"), cfg.get_port("backend"), "Backend"),
                (cfg.get_host("redis"), cfg.get_port("redis"), "Redis"),
                (cfg.get_host("ollama"), cfg.get_port("ollama"), "Ollama"),
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

        except Exception as e:
            self._add_result(
                component,
                "System Error",
                ValidationSeverity.CRITICAL,
                False,
                f"System resource validation failed: {str(e)}",
            )

        return [r for r in self.results if r.component == component]

    async def run_comprehensive_validation(self) -> SystemValidationReport:
        """Run all validation tests and generate comprehensive report"""
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

        # Generate comprehensive report
        total_duration = time.time() - start_time

        # Calculate statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.status)
        failed_tests = total_tests - passed_tests
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

        # Calculate overall health score
        if total_tests > 0:
            base_score = (passed_tests / total_tests) * 100
            # Penalize critical issues more heavily
            critical_penalty = critical_issues * 20
            warning_penalty = warnings * 5
            overall_health_score = max(
                0, base_score - critical_penalty - warning_penalty
            )
        else:
            overall_health_score = 0

        # Determine if system is ready
        system_ready = critical_issues == 0 and overall_health_score >= 70

        # Generate recommendations
        recommendations = self._generate_recommendations()

        # Calculate performance metrics
        avg_response_time = sum(
            r.duration_ms for r in self.results if r.duration_ms > 0
        ) / max(len([r for r in self.results if r.duration_ms > 0]), 1)

        performance_metrics = {
            "total_validation_time_seconds": round(total_duration, 2),
            "average_response_time_ms": round(avg_response_time, 2),
            "fastest_test_ms": min(
                (r.duration_ms for r in self.results if r.duration_ms > 0), default=0
            ),
            "slowest_test_ms": max(
                (r.duration_ms for r in self.results if r.duration_ms > 0), default=0
            ),
        }

        report = SystemValidationReport(
            timestamp=time.time(),
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            critical_issues=critical_issues,
            warnings=warnings,
            overall_health_score=round(overall_health_score, 1),
            system_ready=system_ready,
            validation_results=self.results,
            recommendations=recommendations,
            performance_metrics=performance_metrics,
        )

        self.logger.info(
            f"✅ Validation completed: {passed_tests}/{total_tests} tests passed, "
            f"Health Score: {overall_health_score:.1f}%, Ready: {system_ready}"
        )

        return report

    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []

        # Critical issues
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

        # Performance issues
        slow_tests = [
            r
            for r in self.results
            if r.duration_ms > self.critical_thresholds["response_time_ms"]
        ]
        if slow_tests:
            recommendations.append(
                f"PERFORMANCE: {len(slow_tests)} operations are slower than {self.critical_thresholds['response_time_ms']}ms"
            )

        # Component-specific recommendations
        failed_by_component = {}
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

        # Success acknowledgments
        success_count = sum(1 for r in self.results if r.status)
        if success_count > 0:
            recommendations.append(
                f"POSITIVE: {success_count} tests are passing successfully"
            )

        # Overall system health
        if not recommendations:
            recommendations.append("EXCELLENT: All systems are operating optimally")

        return recommendations


# Global validator instance
_system_validator = None


def get_system_validator() -> SystemValidator:
    """Get the global system validator instance"""
    global _system_validator
    if _system_validator is None:
        _system_validator = SystemValidator()
    return _system_validator
