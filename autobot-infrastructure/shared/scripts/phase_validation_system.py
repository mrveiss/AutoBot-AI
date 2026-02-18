#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated Phase Validation System for AutoBot
Implements comprehensive validation of development phases with automated criteria
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import psutil
import requests

# Import centralized Redis client
sys.path.append(str(Path(__file__).parent.parent))
from constants import ServiceURLs
from utils.redis_client import get_redis_client

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class PhaseValidationCriteria:
    """Defines validation criteria for each development phase"""

    PHASE_CRITERIA = {
        "Phase 1: Core Infrastructure": {
            "description": "Establish foundational system architecture",
            "acceptance_criteria": [
                "Backend API server runs on port 8001",
                "Configuration management system operational",
                "Basic project structure established",
                "Dependency management configured",
            ],
            "functional_requirements": [
                "FastAPI backend responds to health checks",
                "Configuration loaded from YAML files",
                "Logging system captures application events",
                "Error handling framework in place",
            ],
            "files": [
                "main.py",
                "src/config.py",
                "backend/app_factory.py",
                "requirements.txt",
            ],
            "directories": ["src/", "backend/", "data/"],
            "endpoints": ["/api/system/health", "/api/system/status"],
            "services": ["backend"],
            "weight": 100,
        },
        "Phase 2: Knowledge Base and Memory": {
            "description": "Implement persistent memory and knowledge management",
            "acceptance_criteria": [
                "ChromaDB vector storage operational",
                "SQLite database for memory persistence",
                "Redis integration for caching",
                "Knowledge entry CRUD operations",
            ],
            "functional_requirements": [
                "Store and retrieve knowledge entries",
                "Vector similarity search functionality",
                "Memory context preservation",
                "Redis background task processing",
            ],
            "files": [
                "src/knowledge_base.py",
                "src/enhanced_memory_manager.py",
                "data/knowledge_base.db",
            ],
            "endpoints": [
                "/api/system/health",  # Use system health
                "/api/redis/status",  # Check Redis status instead
            ],
            "services": ["redis"],
            "weight": 90,
        },
        "Phase 3: LLM Integration": {
            "description": "Integrate LLM capabilities with local Ollama service",
            "acceptance_criteria": [
                "Ollama service running and accessible",
                "LLM interface module operational",
                "Prompt management system implemented",
                "LLM health monitoring active",
            ],
            "functional_requirements": [
                "Process natural language queries",
                "Generate contextual responses",
                "Manage conversation prompts",
                "Monitor LLM service health",
                "Handle LLM timeout and error scenarios",
            ],
            "files": ["src/llm_interface.py", "src/prompt_manager.py"],
            "endpoints": ["/api/llm/status", "/api/llm/status/comprehensive"],
            "services": ["ollama"],
            "weight": 85,
        },
        "Phase 4: Security and Authentication": {
            "description": "Implement comprehensive security framework",
            "acceptance_criteria": [
                "Security layer modules implemented",
                "Automated security scanning configured",
                "SAST analysis pipeline active",
                "Container security measures in place",
                "Security status monitoring operational",
            ],
            "functional_requirements": [
                "Authenticate user access",
                "Validate input data security",
                "Scan dependencies for vulnerabilities",
                "Perform static code analysis",
                "Monitor security events",
                "Enforce access controls",
            ],
            "files": [
                "src/security_layer.py",
                "src/enhanced_security_layer.py",
                ".github/workflows/security.yml",
                ".bandit",
            ],
            "endpoints": ["/api/security/status"],
            "security_features": [
                "dependency_scanning",
                "sast_analysis",
                "container_security",
            ],
            "weight": 95,
        },
        "Phase 5: Agent Orchestration": {
            "description": "Implement intelligent agent orchestration system",
            "acceptance_criteria": [
                "Agent orchestration framework operational",
                "Task planning and execution system active",
                "Multi-agent coordination functional",
                "Workflow management implemented",
                "Agent status monitoring operational",
            ],
            "functional_requirements": [
                "Coordinate multiple AI agents",
                "Plan and execute complex tasks",
                "Manage agent workflows",
                "Handle agent communication",
                "Monitor agent performance",
                "Resolve agent conflicts",
            ],
            "files": [
                "src/orchestrator.py",
                "src/lightweight_orchestrator.py",
                "backend/api/orchestration.py",
            ],
            "endpoints": ["/api/orchestration/status"],
            "orchestration_features": [
                "task_planning",
                "agent_coordination",
                "workflow_management",
            ],
            "weight": 70,
        },
        "Phase 6: Enhanced UI/UX": {
            "description": "Develop comprehensive user interface with Vue.js frontend",
            "acceptance_criteria": [
                "Vue.js frontend application functional",
                "Chat interface fully operational",
                "Settings and configuration panels active",
                "Real-time status updates working",
                "Responsive design implemented",
            ],
            "functional_requirements": [
                "Provide intuitive chat interface",
                "Display system status and metrics",
                "Enable configuration management",
                "Support real-time updates",
                "Implement responsive design",
                "Handle user interactions",
            ],
            "files": [
                "autobot-vue/src/App.vue",
                "autobot-vue/package.json",
                "autobot-vue/src/components/",
            ],
            "endpoints": [ServiceURLs.FRONTEND_LOCAL],
            "ui_features": ["chat_interface", "terminal_interface", "settings_panel"],
            "weight": 75,
        },
        "Phase 7: Testing and Validation": {
            "description": "Implement comprehensive testing framework",
            "acceptance_criteria": [
                "Automated test suite operational",
                "Unit tests for all core modules",
                "Integration tests for API endpoints",
                "Performance testing implemented",
                "Test reporting and metrics active",
            ],
            "functional_requirements": [
                "Execute automated test suites",
                "Validate module functionality",
                "Test API endpoint responses",
                "Measure system performance",
                "Generate test reports",
                "Ensure code quality standards",
            ],
            "files": [
                "tests/",
                "scripts/automated_testing_procedure.py",
                "scripts/comprehensive_code_profiler.py",
            ],
            "endpoints": ["/api/system/health"],
            "testing_features": [
                "unit_testing",
                "integration_testing",
                "performance_testing",
                "code_quality_checks",
            ],
            "weight": 80,
        },
        "Phase 8: Advanced Features": {
            "description": "Implement advanced system capabilities",
            "acceptance_criteria": [
                "Performance optimization modules active",
                "Advanced caching system operational",
                "Memory optimization implemented",
                "Monitoring and alerting functional",
                "Performance metrics tracking active",
            ],
            "functional_requirements": [
                "Optimize system performance",
                "Manage advanced caching strategies",
                "Monitor memory usage",
                "Track performance metrics",
                "Generate performance alerts",
                "Provide performance dashboards",
            ],
            "files": [
                "src/utils/database_pool.py",
                "src/utils/advanced_cache_manager.py",
                "src/utils/memory_optimization.py",
                "scripts/monitoring_system.py",
                "scripts/performance_dashboard.py",
            ],
            "endpoints": ["/api/metrics/system/health"],
            "performance_metrics": {
                "api_response_time": 100,  # ms
                "memory_usage": 85,  # percentage
                "cpu_usage": 80,  # percentage
            },
            "monitoring_features": [
                "system_metrics",
                "health_checks",
                "performance_dashboard",
            ],
            "weight": 88,
        },
        "Phase 9: Multi-Modal AI": {
            "description": "Implement advanced multi-modal AI capabilities",
            "acceptance_criteria": [
                "Multi-modal AI agents operational",
                "Hardware acceleration configured",
                "Code search functionality active",
                "NPU worker integration complete",
                "Advanced research capabilities functional",
            ],
            "functional_requirements": [
                "Process multiple input modalities",
                "Perform semantic code analysis",
                "Execute advanced research tasks",
                "Utilize hardware acceleration",
                "Coordinate specialized AI agents",
                "Handle complex AI workflows",
            ],
            "files": [
                "src/agents/",
                "src/hardware_acceleration.py",
                "src/worker_node.py",
                "src/llm_self_awareness.py",
                "src/phase_progression_manager.py",
            ],
            "endpoints": [
                "/api/intelligent-agent/health",
                "/api/code_search/status",
                "/api/phase_management/status",
            ],
            "ai_features": [
                "multimodal_ai",
                "code_search",
                "advanced_research",
                "self_awareness",
                "phase_progression",
            ],
            "weight": 65,
        },
        "Phase 10: Production Readiness": {
            "files": ["docker-compose.yml", "Dockerfile", ".dockerignore"],
            "production_features": [
                "containerization",
                "scalability",
                "deployment_automation",
            ],
            "weight": 60,
        },
    }


class PhaseValidator:
    """Comprehensive phase validation system"""

    def __init__(self, project_root: Path = None):
        """Initialize phase validator with project root and backend/frontend URLs."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.validation_results = {}
        self.overall_score = 0
        self.backend_url = ServiceURLs.BACKEND_LOCAL
        self.frontend_url = ServiceURLs.FRONTEND_LOCAL

    async def validate_all_phases(self) -> Dict[str, Any]:
        """Validate all development phases"""
        logger.info("🔍 Starting comprehensive phase validation...")

        validation_results = {
            "timestamp": datetime.now().isoformat(),
            "phases": {},
            "overall_assessment": {},
            "recommendations": [],
        }

        total_weighted_score = 0
        total_weight = 0

        for phase_name, criteria in PhaseValidationCriteria.PHASE_CRITERIA.items():
            logger.info("📋 Validating %s...", phase_name)

            phase_result = await self._validate_phase(phase_name, criteria)
            validation_results["phases"][phase_name] = phase_result

            # Calculate weighted score
            phase_weight = criteria.get("weight", 50)
            weighted_score = phase_result["completion_percentage"] * phase_weight / 100
            total_weighted_score += weighted_score
            total_weight += phase_weight

            logger.info(
                f"✅ {phase_name}: {phase_result['completion_percentage']:.1f}% complete"
            )

        # Calculate overall system maturity
        overall_completion = (
            (total_weighted_score / total_weight) * 100 if total_weight > 0 else 0
        )

        validation_results["overall_assessment"] = {
            "system_maturity_score": round(overall_completion, 2),
            "development_stage": self._determine_development_stage(overall_completion),
            "ready_for_production": overall_completion >= 85,
            "critical_phases_complete": self._check_critical_phases(
                validation_results["phases"]
            ),
            "total_phases_evaluated": len(PhaseValidationCriteria.PHASE_CRITERIA),
            "phases_fully_complete": len(
                [
                    p
                    for p in validation_results["phases"].values()
                    if p["completion_percentage"] >= 95
                ]
            ),
        }

        # Generate recommendations
        validation_results["recommendations"] = self._generate_recommendations(
            validation_results["phases"]
        )

        self.validation_results = validation_results
        return validation_results

    def _determine_phase_status(self, completion_percentage: float) -> str:
        """Determine phase status from completion percentage (Issue #665: extracted helper)."""
        if completion_percentage >= 95:
            return "complete"
        elif completion_percentage >= 75:
            return "mostly_complete"
        elif completion_percentage >= 50:
            return "in_progress"
        else:
            return "incomplete"

    async def _validate_phase_features(
        self, criteria: Dict[str, Any], results: Dict[str, Any]
    ) -> tuple:
        """Validate all feature types in criteria (Issue #665: extracted helper)."""
        feature_types = [
            "security_features",
            "performance_metrics",
            "monitoring_features",
            "ui_features",
            "orchestration_features",
            "ai_features",
            "production_features",
            "testing_features",
        ]

        total_checks = 0
        passed_checks = 0

        for feature_type in feature_types:
            if feature_type in criteria:
                feature_results = await self._validate_features(
                    feature_type, criteria[feature_type]
                )
                results["validations"]["features"]["passed"] += feature_results[
                    "passed"
                ]
                results["validations"]["features"]["total"] += feature_results["total"]
                results["validations"]["features"]["details"].extend(
                    feature_results["details"]
                )
                total_checks += feature_results["total"]
                passed_checks += feature_results["passed"]

        return total_checks, passed_checks

    def _empty_phase_result(self, phase_name: str) -> Dict[str, Any]:
        """Create empty phase validation result structure.

        Helper for _validate_phase (#825).
        """
        empty_validation = {"passed": 0, "total": 0, "details": []}
        return {
            "phase_name": phase_name,
            "completion_percentage": 0,
            "status": "incomplete",
            "validations": {
                k: dict(empty_validation)
                for k in [
                    "files",
                    "directories",
                    "endpoints",
                    "services",
                    "features",
                ]
            },
            "issues": [],
            "recommendations": [],
        }

    async def _validate_phase(
        self, phase_name: str, criteria: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate a specific development phase."""
        results = self._empty_phase_result(phase_name)
        total_checks = 0
        passed_checks = 0

        validation_map = {
            "files": self._validate_files,
            "directories": self._validate_directories,
        }
        for key, validator in validation_map.items():
            if key in criteria:
                vr = validator(criteria[key])
                results["validations"][key] = vr
                total_checks += vr["total"]
                passed_checks += vr["passed"]

        async_validation_map = {
            "endpoints": self._validate_endpoints,
            "services": self._validate_services,
        }
        for key, validator in async_validation_map.items():
            if key in criteria:
                vr = await validator(criteria[key])
                results["validations"][key] = vr
                total_checks += vr["total"]
                passed_checks += vr["passed"]

        ft, fp = await self._validate_phase_features(criteria, results)
        total_checks += ft
        passed_checks += fp

        if total_checks > 0:
            results["completion_percentage"] = round(
                (passed_checks / total_checks) * 100, 2
            )
        results["status"] = self._determine_phase_status(
            results["completion_percentage"]
        )
        return results

    def _validate_files(self, files: List[str]) -> Dict[str, Any]:
        """Validate required files exist"""
        results = {"passed": 0, "total": len(files), "details": []}

        for file_path in files:
            full_path = self.project_root / file_path
            exists = full_path.exists()

            results["details"].append(
                {
                    "path": file_path,
                    "exists": exists,
                    "size": full_path.stat().st_size if exists else 0,
                }
            )

            if exists:
                results["passed"] += 1

        return results

    def _validate_directories(self, directories: List[str]) -> Dict[str, Any]:
        """Validate required directories exist"""
        results = {"passed": 0, "total": len(directories), "details": []}

        for dir_path in directories:
            full_path = self.project_root / dir_path
            exists = full_path.exists() and full_path.is_dir()

            results["details"].append(
                {
                    "path": dir_path,
                    "exists": exists,
                    "files_count": len(list(full_path.iterdir())) if exists else 0,
                }
            )

            if exists:
                results["passed"] += 1

        return results

    async def _validate_endpoints(self, endpoints: List[str]) -> Dict[str, Any]:
        """Validate API endpoints are accessible"""
        results = {"passed": 0, "total": len(endpoints), "details": []}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            for endpoint in endpoints:
                # Determine full URL
                if endpoint.startswith("http"):
                    url = endpoint
                else:
                    url = f"{self.backend_url}{endpoint}"

                try:
                    async with session.get(url) as response:
                        accessible = response.status < 500
                        results["details"].append(
                            {
                                "endpoint": endpoint,
                                "url": url,
                                "accessible": accessible,
                                "status_code": response.status,
                                "response_time_ms": 0,  # Could add timing if needed
                            }
                        )

                        if accessible:
                            results["passed"] += 1

                except Exception as e:
                    results["details"].append(
                        {
                            "endpoint": endpoint,
                            "url": url,
                            "accessible": False,
                            "error": str(e),
                        }
                    )

        return results

    async def _validate_services(self, services: List[str]) -> Dict[str, Any]:
        """Validate required services are running"""
        results = {"passed": 0, "total": len(services), "details": []}

        for service in services:
            running = self._check_service_status(service)

            results["details"].append(
                {
                    "service": service,
                    "running": running,
                    "status": "active" if running else "inactive",
                }
            )

            if running:
                results["passed"] += 1

        return results

    def _check_backend_service(self) -> bool:
        """Check if uvicorn/backend is running (Issue #315: extracted helper)."""
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            if "uvicorn" in cmdline or "main:app" in cmdline:
                return True
        return False

    def _check_redis_service(self) -> bool:
        """Check if Redis is accessible (Issue #315: extracted helper)."""
        try:

            async def check_redis():
                """Check Redis connectivity using centralized client."""
                redis_client = await get_redis_client("main")
                if redis_client:
                    await redis_client.ping()
                    return True
                return False

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(check_redis())
            loop.close()
            return result
        except Exception:
            return False

    def _check_ollama_service(self) -> bool:
        """Check if Ollama is accessible (Issue #315: extracted helper)."""
        try:
            response = requests.get("ServiceURLs.OLLAMA_LOCAL/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def _check_frontend_service(self) -> bool:
        """Check if frontend dev server is running (Issue #315: extracted helper)."""
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            if "vite" in cmdline or "npm run dev" in cmdline:
                return True
        return False

    def _check_service_status(self, service: str) -> bool:
        """Check if a specific service is running (Issue #315: refactored)."""
        service_checkers = {
            "backend": self._check_backend_service,
            "redis": self._check_redis_service,
            "ollama": self._check_ollama_service,
            "frontend": self._check_frontend_service,
        }

        try:
            checker = service_checkers.get(service)
            if checker:
                return checker()
            return False
        except Exception as e:
            logger.debug("Error checking service %s: %s", service, e)
            return False

    async def _validate_features(self, feature_type: str, features) -> Dict[str, Any]:
        """Validate specific feature implementations"""
        if isinstance(features, dict):
            # Performance metrics validation
            if feature_type == "performance_metrics":
                return await self._validate_performance_metrics(features)
            else:
                # Convert dict to list for other feature types
                features = list(features.keys())

        # Default feature validation for lists
        results = {"passed": 0, "total": len(features), "details": []}

        for feature in features:
            # Basic feature validation - could be enhanced per feature type
            validated = await self._validate_single_feature(feature_type, feature)

            results["details"].append(
                {"feature": feature, "implemented": validated, "type": feature_type}
            )

            if validated:
                results["passed"] += 1

        return results

    async def _validate_performance_metrics(
        self, metrics: Dict[str, int]
    ) -> Dict[str, Any]:
        """Validate performance metrics meet criteria"""
        results = {"passed": 0, "total": len(metrics), "details": []}

        try:
            # Get current system metrics
            cpu_usage = psutil.cpu_percent(interval=1)
            memory_usage = psutil.virtual_memory().percent

            # Test API response time (Issue #359: use async HTTP)
            start_time = time.time()
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        f"{self.backend_url}/api/system/health"
                    ) as response:
                        await response.text()  # Consume response
                api_response_time = (time.time() - start_time) * 1000  # ms
            except Exception:
                api_response_time = 5000  # Timeout

            current_metrics = {
                "api_response_time": api_response_time,
                "memory_usage": memory_usage,
                "cpu_usage": cpu_usage,
            }

            for metric_name, threshold in metrics.items():
                current_value = current_metrics.get(metric_name, threshold + 1)
                meets_criteria = current_value <= threshold

                results["details"].append(
                    {
                        "metric": metric_name,
                        "current_value": round(current_value, 2),
                        "threshold": threshold,
                        "meets_criteria": meets_criteria,
                    }
                )

                if meets_criteria:
                    results["passed"] += 1

        except Exception as e:
            logger.error("Error validating performance metrics: %s", e)

        return results

    def _get_feature_validators(self) -> Dict[str, Any]:
        """Build mapping of feature names to validation callables.

        Helper for _validate_single_feature (#825).
        """
        root = self.project_root
        return {
            "dependency_scanning": lambda: (
                root / ".github/workflows/security.yml"
            ).exists(),
            "sast_analysis": lambda: (root / ".bandit").exists(),
            "container_security": lambda: any((root / "scripts").glob("*security*")),
            "system_metrics": lambda: (root / "scripts/monitoring_system.py").exists(),
            "health_checks": lambda: self._check_endpoint_sync("/api/system/health"),
            "performance_dashboard": lambda: (
                root / "scripts/performance_dashboard.py"
            ).exists(),
            "chat_interface": lambda: (root / "autobot-vue/src/components").exists(),
            "terminal_interface": lambda: any(
                (root / "autobot-vue/src/components").glob("*Terminal*")
            ),
            "settings_panel": lambda: any(
                (root / "autobot-vue/src/components").glob("*Settings*")
            ),
            "multimodal_ai": lambda: (root / "src/agents").exists(),
            "code_search": lambda: any((root / "src/agents").glob("*code_search*")),
            "advanced_research": lambda: any((root / "src/agents").glob("*research*")),
            "self_awareness": lambda: (root / "src/llm_self_awareness.py").exists(),
            "phase_progression": lambda: (
                root / "src/phase_progression_manager.py"
            ).exists(),
            "unit_testing": lambda: (root / "tests").exists(),
            "integration_testing": lambda: (
                root / "scripts/automated_testing_procedure.py"
            ).exists(),
            "performance_testing": lambda: (
                root / "scripts/comprehensive_code_profiler.py"
            ).exists(),
            "code_quality_checks": lambda: any((root / "scripts").glob("*profile*")),
            "task_planning": lambda: any((root / "src").glob("*orchestrat*")),
            "agent_coordination": lambda: (root / "src/orchestrator.py").exists(),
            "workflow_management": lambda: (
                root / "backend/api/orchestration.py"
            ).exists(),
        }

    async def _validate_single_feature(self, feature_type: str, feature: str) -> bool:
        """Validate a single feature implementation."""
        validators = self._get_feature_validators()
        validator = validators.get(feature)
        if validator:
            try:
                return validator()
            except Exception:
                return False
        return True

    def _check_endpoint_sync(self, endpoint: str) -> bool:
        """Synchronous endpoint check for feature validation"""
        try:
            response = requests.get(f"{self.backend_url}{endpoint}", timeout=3)
            return response.status_code < 500
        except Exception:
            return False

    def _determine_development_stage(self, completion_percentage: float) -> str:
        """Determine overall development stage"""
        if completion_percentage >= 95:
            return "production_ready"
        elif completion_percentage >= 85:
            return "release_candidate"
        elif completion_percentage >= 70:
            return "beta"
        elif completion_percentage >= 50:
            return "alpha"
        elif completion_percentage >= 25:
            return "development"
        else:
            return "prototype"

    def _check_critical_phases(self, phases: Dict[str, Any]) -> bool:
        """Check if critical phases are complete"""
        critical_phases = [
            "Phase 1: Core Infrastructure",
            "Phase 2: Knowledge Base and Memory",
            "Phase 3: LLM Integration",
            "Phase 4: Security and Authentication",
        ]

        for phase_name in critical_phases:
            if phase_name in phases:
                if phases[phase_name]["completion_percentage"] < 90:
                    return False
        return True

    def _generate_recommendations(self, phases: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on validation results"""
        recommendations = []

        # Check each phase for issues
        for phase_name, phase_data in phases.items():
            completion = phase_data["completion_percentage"]

            if completion < 50:
                recommendations.append(
                    f"🔴 CRITICAL: {phase_name} needs significant work "
                    f"({completion:.1f}% complete)"
                )
            elif completion < 75:
                recommendations.append(
                    f"🟡 MEDIUM: {phase_name} requires attention "
                    f"({completion:.1f}% complete)"
                )
            elif completion < 95:
                recommendations.append(
                    f"🟢 LOW: {phase_name} nearly complete ({completion:.1f}% complete)"
                )

        # Performance recommendations
        overall_completion = sum(
            p["completion_percentage"] for p in phases.values()
        ) / len(phases)

        if overall_completion < 70:
            recommendations.append(
                "🎯 Focus on completing critical infrastructure phases first"
            )
        elif overall_completion < 85:
            recommendations.append(
                "🚀 System approaching production readiness - "
                "focus on final optimizations"
            )
        else:
            recommendations.append(
                "✅ System is production-ready - consider advanced features and scaling"
            )

        return recommendations

    def save_validation_report(self, output_path: Optional[Path] = None) -> Path:
        """Save validation report to file"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = (
                self.project_root / "reports" / f"phase_validation_{timestamp}.json"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.validation_results, f, indent=2)

        logger.info("📊 Validation report saved: %s", output_path)
        return output_path


def _output_json_results(results: Dict[str, Any], output_file: str = None):
    """Format and output validation results as JSON.

    Helper for main (#825).
    """
    output = {
        "timestamp": datetime.now().isoformat(),
        "overall_maturity": results.get("overall_maturity", 0),
        "phases": [],
        "recommendations": [],
    }

    for phase_name, phase_data in results.get("phases", {}).items():
        output["phases"].append(
            {
                "name": phase_name,
                "status": phase_data.get("status", "unknown"),
                "completion_percentage": phase_data.get("completion_percentage", 0),
                "validation_details": phase_data.get("validation_details", {}),
            }
        )

    output["recommendations"] = [
        {"title": rec, "action": "Review and implement"}
        for rec in results.get("recommendations", [])
    ]

    if output_file:
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        logger.info("Results saved to %s", output_file)
    else:
        logger.info(json.dumps(output, indent=2))


def _output_summary_results(results: Dict[str, Any]):
    """Format and output validation results as summary text.

    Helper for main (#825).
    """
    logger.info("AutoBot Phase Validation Results")
    logger.info("==================================")
    maturity = results.get("overall_maturity", 0)
    logger.info("Overall System Maturity: %.1f%%", maturity)
    logger.info("")

    for phase_name, phase_data in results.get("phases", {}).items():
        status = phase_data.get("status", "unknown")
        completion = phase_data.get("completion_percentage", 0)
        logger.info("[%s] %s: %.1f%% complete", status, phase_name, completion)

    logger.info("")
    logger.info("Recommendations:")
    for rec in results.get("recommendations", []):
        logger.info("  - %s", rec)


def main() -> None:
    """Main entry point for CLI phase validation system."""
    parser = argparse.ArgumentParser(description="AutoBot Phase Validation System")
    parser.add_argument(
        "--output-format",
        choices=["json", "summary"],
        default="summary",
        help="Output format for results",
    )
    parser.add_argument("--output-file", type=str, help="Output file path for results")
    parser.add_argument(
        "--phase-filter",
        type=str,
        help="Filter validation to specific phase",
    )
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Run in CI mode with simplified output",
    )
    args = parser.parse_args()

    validator = PhaseValidator()

    try:
        results = asyncio.run(validator.validate_all_phases())

        if args.output_format == "json":
            _output_json_results(results, args.output_file)
        else:
            _output_summary_results(results)

        maturity = results.get("overall_maturity", 0)
        if maturity < 50:
            sys.exit(2)
        elif maturity < 75:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        logger.error("Validation failed: %s", e)
        sys.exit(3)


if __name__ == "__main__":
    main()
