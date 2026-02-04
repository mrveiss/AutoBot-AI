#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enterprise Feature Manager - Phase 4 Implementation
Enables and manages enterprise-grade features for AutoBot system.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeatureCategory(Enum):
    """Categories of enterprise features"""

    RESEARCH_ORCHESTRATION = "research_orchestration"
    LOAD_BALANCING = "load_balancing"
    RESOURCE_OPTIMIZATION = "resource_optimization"
    HEALTH_MONITORING = "health_monitoring"
    FAILOVER_RECOVERY = "failover_recovery"
    CONFIGURATION_MANAGEMENT = "configuration_management"
    PERFORMANCE_TUNING = "performance_tuning"
    SECURITY_ENHANCEMENT = "security_enhancement"


class FeatureStatus(Enum):
    """Status of enterprise features"""

    DISABLED = "disabled"
    ENABLING = "enabling"
    ENABLED = "enabled"
    ERROR = "error"
    DEGRADED = "degraded"


@dataclass
class EnterpriseFeature:
    """Enterprise feature definition"""

    name: str
    category: FeatureCategory
    description: str
    dependencies: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    status: FeatureStatus = FeatureStatus.DISABLED
    enabled_at: Optional[datetime] = None
    health_check_endpoint: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


class EnterpriseFeatureManager:
    """Manages enterprise-grade features and capabilities"""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize enterprise feature manager with VM topology and resource pools."""
        import os

        base_dir = os.getenv(
            "AUTOBOT_BASE_DIR",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        self.config_path = (
            config_path or Path(base_dir) / "config" / "enterprise_features.json"
        )
        self.features: Dict[str, EnterpriseFeature] = {}
        self.vm_topology = self._initialize_vm_topology()
        self.resource_pools = self._initialize_resource_pools()
        self.health_checkers = {}

        # Initialize enterprise features
        self._initialize_enterprise_features()

        logger.info("Enterprise Feature Manager initialized")

    def _get_vm_env_config(self) -> Dict[str, Optional[str]]:
        """Get VM environment configuration variables."""
        import os

        return {
            "backend_host": os.getenv("AUTOBOT_BACKEND_HOST"),
            "backend_port": os.getenv("AUTOBOT_BACKEND_PORT"),
            "vnc_port": os.getenv("AUTOBOT_VNC_PORT"),
            "frontend_host": os.getenv("AUTOBOT_FRONTEND_HOST"),
            "frontend_port": os.getenv("AUTOBOT_FRONTEND_PORT"),
            "npu_worker_host": os.getenv("AUTOBOT_NPU_WORKER_HOST"),
            "npu_worker_port": os.getenv("AUTOBOT_NPU_WORKER_PORT"),
            "redis_host": os.getenv("AUTOBOT_REDIS_HOST"),
            "redis_port": os.getenv("AUTOBOT_REDIS_PORT"),
            "ai_stack_host": os.getenv("AUTOBOT_AI_STACK_HOST"),
            "ai_stack_port": os.getenv("AUTOBOT_AI_STACK_PORT"),
            "browser_host": os.getenv("AUTOBOT_BROWSER_SERVICE_HOST"),
            "browser_port": os.getenv("AUTOBOT_BROWSER_SERVICE_PORT"),
        }

    def _validate_vm_env_config(self, cfg: Dict[str, Optional[str]]) -> None:
        """Validate that all required VM environment variables are set."""
        if not all(cfg.values()):
            raise ValueError(
                "VM topology configuration missing: All AUTOBOT_*_HOST and "
                "AUTOBOT_*_PORT environment variables must be set"
            )

    def _get_core_vm_configs(
        self, cfg: Dict[str, Optional[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get main machine and frontend VM configurations.

        Issue #620.
        """
        return {
            "main_machine": {
                "ip": cfg["backend_host"],
                "services": ["backend_api", "desktop_vnc", "terminal_vnc"],
                "ports": [int(cfg["backend_port"]), int(cfg["vnc_port"])],
                "capabilities": ["coordination", "management", "user_interface"],
                "resources": {"cpu_cores": 22, "memory_gb": 32, "gpu": "RTX_4070"},
            },
            "frontend_vm": {
                "ip": cfg["frontend_host"],
                "services": ["web_interface"],
                "ports": [int(cfg["frontend_port"])],
                "capabilities": ["web_ui", "user_interaction"],
                "resources": {"cpu_cores": 4, "memory_gb": 8},
            },
        }

    def _get_processing_vm_configs(
        self, cfg: Dict[str, Optional[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get NPU worker and AI stack VM configurations.

        Issue #620.
        """
        return {
            "npu_worker_vm": {
                "ip": cfg["npu_worker_host"],
                "services": ["ai_acceleration", "npu_worker"],
                "ports": [int(cfg["npu_worker_port"])],
                "capabilities": [
                    "ai_acceleration",
                    "npu_processing",
                    "hardware_optimization",
                ],
                "resources": {"cpu_cores": 4, "memory_gb": 8, "npu": "Intel_NPU"},
            },
            "ai_stack_vm": {
                "ip": cfg["ai_stack_host"],
                "services": ["ai_processing", "llm_inference"],
                "ports": [int(cfg["ai_stack_port"])],
                "capabilities": [
                    "ai_processing",
                    "llm_inference",
                    "knowledge_processing",
                ],
                "resources": {
                    "cpu_cores": 8,
                    "memory_gb": 16,
                    "gpu_acceleration": True,
                },
            },
        }

    def _get_service_vm_configs(
        self, cfg: Dict[str, Optional[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get Redis and browser VM configurations.

        Issue #620.
        """
        return {
            "redis_vm": {
                "ip": cfg["redis_host"],
                "services": ["redis_server", "data_storage"],
                "ports": [int(cfg["redis_port"])],
                "capabilities": ["data_persistence", "caching", "session_storage"],
                "resources": {"cpu_cores": 2, "memory_gb": 16, "storage_gb": 100},
            },
            "browser_vm": {
                "ip": cfg["browser_host"],
                "services": ["web_automation", "playwright_server"],
                "ports": [int(cfg["browser_port"])],
                "capabilities": ["web_automation", "browser_control", "scraping"],
                "resources": {"cpu_cores": 4, "memory_gb": 8, "display": True},
            },
        }

    def _build_vm_topology(
        self, cfg: Dict[str, Optional[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build VM topology dictionary from environment configuration.

        Issue #620: Refactored with helper methods for each VM group.
        """
        topology = {}
        topology.update(self._get_core_vm_configs(cfg))
        topology.update(self._get_processing_vm_configs(cfg))
        topology.update(self._get_service_vm_configs(cfg))
        return topology

    def _initialize_vm_topology(self) -> Dict[str, Dict[str, Any]]:
        """Initialize 6-VM distributed topology."""
        cfg = self._get_vm_env_config()
        self._validate_vm_env_config(cfg)
        return self._build_vm_topology(cfg)

    def _initialize_resource_pools(self) -> Dict[str, Dict[str, Any]]:
        """Initialize resource pools for intelligent routing"""
        return {
            "cpu_intensive": {
                "primary": ["main_machine", "ai_stack_vm"],
                "secondary": ["npu_worker_vm", "browser_vm"],
                "routing_logic": "round_robin_weighted",
                "weight_factors": {
                    "cpu_cores": 0.6,
                    "memory_gb": 0.3,
                    "current_load": 0.1,
                },
            },
            "gpu_acceleration": {
                "primary": ["main_machine"],
                "secondary": ["ai_stack_vm"],
                "routing_logic": "capability_based",
                "requirements": {"gpu": True},
            },
            "npu_acceleration": {
                "primary": ["npu_worker_vm"],
                "secondary": [],
                "routing_logic": "dedicated",
                "requirements": {"npu": True},
            },
            "memory_intensive": {
                "primary": ["redis_vm", "main_machine"],
                "secondary": ["ai_stack_vm"],
                "routing_logic": "memory_availability",
                "threshold_gb": 4,
            },
            "web_processing": {
                "primary": ["browser_vm"],
                "secondary": ["frontend_vm"],
                "routing_logic": "service_locality",
                "preferred_services": ["web_automation", "web_interface"],
            },
        }

    def _get_research_features(self) -> Dict[str, EnterpriseFeature]:
        """Get research orchestration feature definitions."""
        return {
            "web_research_orchestration": EnterpriseFeature(
                name="Web Research Orchestration",
                category=FeatureCategory.RESEARCH_ORCHESTRATION,
                description="Enable advanced web research capabilities with librarian agents",
                configuration={
                    "enable_librarian_agents": True,
                    "enable_mcp_integration": True,
                    "research_timeout_seconds": 30,
                    "max_concurrent_research": 3,
                    "research_sources": ["web", "manuals", "knowledge_base"],
                    "quality_threshold": 0.7,
                },
                health_check_endpoint="/api/research/health",
            ),
            "advanced_knowledge_search": EnterpriseFeature(
                name="Advanced Knowledge Search",
                category=FeatureCategory.RESEARCH_ORCHESTRATION,
                description="Enhanced knowledge base search with semantic understanding",
                dependencies=["web_research_orchestration"],
                configuration={
                    "enable_semantic_search": True,
                    "enable_cross_reference": True,
                    "search_timeout_seconds": 10,
                    "relevance_threshold": 0.1,
                    "max_results": 10,
                },
            ),
        }

    def _get_load_balancing_features(self) -> Dict[str, EnterpriseFeature]:
        """Get load balancing and routing feature definitions."""
        return {
            "cross_vm_load_balancing": EnterpriseFeature(
                name="Cross-VM Load Balancing",
                category=FeatureCategory.LOAD_BALANCING,
                description="Intelligent load distribution across 6-VM infrastructure",
                configuration={
                    "enable_adaptive_routing": True,
                    "load_balance_algorithm": "weighted_round_robin",
                    "health_check_interval": 30,
                    "failover_threshold": 0.8,
                    "resource_monitoring": True,
                    "auto_scaling": True,
                },
                health_check_endpoint="/api/load_balancer/health",
            ),
            "intelligent_task_routing": EnterpriseFeature(
                name="Intelligent Task Routing",
                category=FeatureCategory.RESOURCE_OPTIMIZATION,
                description="Route tasks to optimal hardware (NPU/GPU/CPU) based on requirements",
                dependencies=["cross_vm_load_balancing"],
                configuration={
                    "enable_hardware_detection": True,
                    "enable_performance_prediction": True,
                    "routing_strategies": {
                        "ai_tasks": "npu_preferred",
                        "gpu_tasks": "gpu_required",
                        "cpu_tasks": "cpu_optimized",
                        "memory_tasks": "memory_optimized",
                    },
                    "performance_history_days": 7,
                    "auto_optimization": True,
                },
            ),
            "dynamic_resource_allocation": EnterpriseFeature(
                name="Dynamic Resource Allocation",
                category=FeatureCategory.RESOURCE_OPTIMIZATION,
                description="Automatic resource scaling based on demand",
                configuration={
                    "enable_auto_scaling": True,
                    "scale_up_threshold": 0.8,
                    "scale_down_threshold": 0.3,
                    "scaling_cooldown_minutes": 5,
                    "resource_limits": {
                        "max_cpu_percent": 90,
                        "max_memory_percent": 85,
                        "max_concurrent_tasks": 50,
                    },
                },
            ),
        }

    def _get_monitoring_features(self) -> Dict[str, EnterpriseFeature]:
        """Get health monitoring and failover feature definitions."""
        return {
            "comprehensive_health_monitoring": EnterpriseFeature(
                name="Comprehensive Health Monitoring",
                category=FeatureCategory.HEALTH_MONITORING,
                description="End-to-end health checks across all systems",
                configuration={
                    "health_check_interval": 30,
                    "critical_service_timeout": 5,
                    "degraded_performance_threshold": 0.7,
                    "alert_channels": ["logs", "metrics", "notifications"],
                    "enable_predictive_health": True,
                    "health_history_days": 30,
                },
                health_check_endpoint="/api/health/comprehensive",
            ),
            "graceful_degradation": EnterpriseFeature(
                name="Graceful Degradation",
                category=FeatureCategory.FAILOVER_RECOVERY,
                description="Graceful service degradation and automatic recovery",
                dependencies=["comprehensive_health_monitoring"],
                configuration={
                    "enable_circuit_breakers": True,
                    "enable_fallback_services": True,
                    "degradation_levels": ["full", "limited", "basic", "emergency"],
                    "recovery_strategies": ["restart", "failover", "scale_out"],
                    "max_degradation_time_minutes": 30,
                },
            ),
            "automated_backup_recovery": EnterpriseFeature(
                name="Automated Backup & Recovery",
                category=FeatureCategory.FAILOVER_RECOVERY,
                description="Automated backup and disaster recovery procedures",
                configuration={
                    "backup_interval_hours": 6,
                    "backup_retention_days": 30,
                    "enable_incremental_backup": True,
                    "backup_targets": [
                        "configurations",
                        "knowledge_base",
                        "chat_history",
                    ],
                    "recovery_testing_enabled": True,
                },
            ),
        }

    def _get_config_and_deployment_features(self) -> Dict[str, EnterpriseFeature]:
        """Get configuration management and deployment feature definitions."""
        return {
            "enterprise_configuration_management": EnterpriseFeature(
                name="Enterprise Configuration Management",
                category=FeatureCategory.CONFIGURATION_MANAGEMENT,
                description="Centralized configuration management with validation",
                configuration={
                    "enable_config_validation": True,
                    "enable_config_versioning": True,
                    "enable_config_rollback": True,
                    "config_sync_interval_minutes": 15,
                    "enable_environment_isolation": True,
                    "config_audit_logging": True,
                },
            ),
            "zero_downtime_deployment": EnterpriseFeature(
                name="Zero-Downtime Deployment",
                category=FeatureCategory.PERFORMANCE_TUNING,
                description="Blue-green deployment with zero downtime",
                dependencies=[
                    "cross_vm_load_balancing",
                    "comprehensive_health_monitoring",
                ],
                configuration={
                    "deployment_strategy": "blue_green",
                    "health_check_timeout": 60,
                    "rollback_on_failure": True,
                    "canary_deployment_percent": 10,
                    "enable_a_b_testing": True,
                },
            ),
        }

    def _initialize_enterprise_features(self):
        """Initialize all enterprise features."""
        self.features.update(self._get_research_features())
        self.features.update(self._get_load_balancing_features())
        self.features.update(self._get_monitoring_features())
        self.features.update(self._get_config_and_deployment_features())
        logger.info("Initialized %s enterprise features", len(self.features))

    def _check_feature_dependencies(self, feature: EnterpriseFeature) -> List[str]:
        """
        Check and return list of missing dependencies for a feature.

        Issue #620.
        """
        missing_deps = []
        for dep in feature.dependencies:
            if (
                dep not in self.features
                or self.features[dep].status != FeatureStatus.ENABLED
            ):
                missing_deps.append(dep)
        return missing_deps

    def _build_success_response(
        self, feature_name: str, feature: EnterpriseFeature, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build success response dictionary for enabled feature.

        Issue #620.
        """
        return {
            "status": "success",
            "message": f"Feature {feature_name} enabled successfully",
            "feature": feature_name,
            "capabilities_unlocked": result.get("capabilities", []),
            "configuration": feature.configuration,
        }

    def _build_error_response(
        self, feature_name: str, error_message: str
    ) -> Dict[str, Any]:
        """
        Build error response dictionary for feature enablement failure.

        Issue #620.
        """
        return {
            "status": "error",
            "message": error_message,
            "feature": feature_name,
        }

    async def enable_feature(self, feature_name: str) -> Dict[str, Any]:
        """Enable a specific enterprise feature. Issue #620: Refactored with helpers."""
        if feature_name not in self.features:
            raise ValueError(f"Unknown feature: {feature_name}")

        feature = self.features[feature_name]
        missing_deps = self._check_feature_dependencies(feature)

        if missing_deps:
            return self._build_error_response(
                feature_name, f"Missing dependencies: {missing_deps}"
            )

        try:
            feature.status = FeatureStatus.ENABLING
            logger.info("Enabling enterprise feature: %s", feature_name)

            result = await self._enable_feature_implementation(feature_name, feature)

            if result["success"]:
                feature.status = FeatureStatus.ENABLED
                feature.enabled_at = datetime.now()

                if feature.health_check_endpoint:
                    await self._start_health_monitoring(feature_name, feature)

                logger.info("Enterprise feature enabled: %s", feature_name)
                return self._build_success_response(feature_name, feature, result)
            else:
                feature.status = FeatureStatus.ERROR
                logger.error("Failed to enable feature: %s", feature_name)
                error_msg = f"Failed to enable {feature_name}: {result.get('error', 'Unknown error')}"
                return self._build_error_response(feature_name, error_msg)

        except Exception as e:
            feature.status = FeatureStatus.ERROR
            logger.error("Exception enabling feature %s: %s", feature_name, e)
            return self._build_error_response(
                feature_name, f"Exception enabling {feature_name}: {str(e)}"
            )

    def _get_feature_enablers(self) -> Dict[str, Any]:
        """Get feature name to enabler method mapping (Issue #315 - dispatch table)."""
        return {
            "web_research_orchestration": self._enable_web_research_orchestration,
            "cross_vm_load_balancing": self._enable_cross_vm_load_balancing,
            "intelligent_task_routing": self._enable_intelligent_task_routing,
            "comprehensive_health_monitoring": self._enable_comprehensive_health_monitoring,
            "graceful_degradation": self._enable_graceful_degradation,
        }

    async def _enable_feature_implementation(
        self, feature_name: str, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Implement specific feature enablement logic (Issue #315 - refactored depth 5 to 2)."""
        enablers = self._get_feature_enablers()

        if feature_name in enablers:
            return await enablers[feature_name](feature)

        # Generic feature enablement
        return {"success": True, "capabilities": [f"{feature_name}_enabled"]}

    async def _enable_web_research_orchestration(
        self, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Enable web research orchestration capabilities"""
        try:
            # Update chat workflow configuration to enable research
            config_updates = {
                "web_research_integration": True,
                "librarian_agents_enabled": True,
                "mcp_integration_enabled": True,
                "research_timeout": feature.configuration["research_timeout_seconds"],
                "max_concurrent_research": feature.configuration[
                    "max_concurrent_research"
                ],
            }

            # Apply configuration to chat workflow
            await self._update_chat_workflow_config(config_updates)

            # Initialize research service endpoints
            await self._initialize_research_endpoints()

            return {
                "success": True,
                "capabilities": [
                    "advanced_web_research",
                    "librarian_agent_coordination",
                    "mcp_manual_integration",
                    "research_quality_control",
                ],
                "config_updates": config_updates,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _enable_cross_vm_load_balancing(
        self, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Enable cross-VM load balancing"""
        try:
            # Initialize load balancer
            load_balancer_config = {
                "vm_topology": self.vm_topology,
                "resource_pools": self.resource_pools,
                "algorithm": feature.configuration["load_balance_algorithm"],
                "health_check_interval": feature.configuration["health_check_interval"],
            }

            # Create load balancer service
            await self._create_load_balancer_service(load_balancer_config)

            return {
                "success": True,
                "capabilities": [
                    "cross_vm_load_distribution",
                    "adaptive_resource_routing",
                    "health_based_failover",
                    "performance_optimization",
                ],
                "load_balancer_config": load_balancer_config,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _enable_intelligent_task_routing(
        self, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Enable intelligent task routing between NPU/GPU/CPU"""
        try:
            # Initialize hardware detection
            hardware_capabilities = await self._detect_hardware_capabilities()

            # Create routing engine
            routing_config = {
                "hardware_capabilities": hardware_capabilities,
                "routing_strategies": feature.configuration["routing_strategies"],
                "performance_history_enabled": True,
            }

            await self._create_task_routing_engine(routing_config)

            return {
                "success": True,
                "capabilities": [
                    "hardware_aware_routing",
                    "performance_based_optimization",
                    "npu_gpu_cpu_coordination",
                    "adaptive_task_placement",
                ],
                "hardware_detected": hardware_capabilities,
                "routing_config": routing_config,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _enable_comprehensive_health_monitoring(
        self, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Enable comprehensive health monitoring"""
        try:
            # Initialize health monitoring system
            monitoring_config = {
                "vm_endpoints": {
                    vm: data["ip"] for vm, data in self.vm_topology.items()
                },
                "service_endpoints": self._get_all_service_endpoints(),
                "check_interval": feature.configuration["health_check_interval"],
                "alert_thresholds": {
                    "response_time_ms": 5000,
                    "error_rate_percent": 10,
                    "resource_usage_percent": 90,
                },
            }

            await self._create_health_monitoring_system(monitoring_config)

            return {
                "success": True,
                "capabilities": [
                    "end_to_end_health_monitoring",
                    "predictive_failure_detection",
                    "automated_alerting",
                    "performance_trend_analysis",
                ],
                "monitoring_config": monitoring_config,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _enable_graceful_degradation(
        self, feature: EnterpriseFeature
    ) -> Dict[str, Any]:
        """Enable graceful degradation and failover"""
        try:
            # Initialize circuit breakers
            circuit_breaker_config = {
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "half_open_max_calls": 3,
            }

            # Initialize fallback services
            fallback_config = {
                "degradation_levels": feature.configuration["degradation_levels"],
                "fallback_endpoints": self._get_fallback_endpoints(),
                "recovery_strategies": feature.configuration["recovery_strategies"],
            }

            await self._create_degradation_system(
                circuit_breaker_config, fallback_config
            )

            return {
                "success": True,
                "capabilities": [
                    "circuit_breaker_protection",
                    "automatic_failover",
                    "graceful_service_degradation",
                    "self_healing_recovery",
                ],
                "circuit_breaker_config": circuit_breaker_config,
                "fallback_config": fallback_config,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def enable_all_enterprise_features(self) -> Dict[str, Any]:
        """Enable all enterprise features in dependency order"""
        logger.info("🚀 Enabling all enterprise features...")

        results = {
            "enabled_features": [],
            "failed_features": [],
            "capabilities_unlocked": [],
            "total_features": len(self.features),
        }

        # Sort features by dependencies
        sorted_features = self._sort_features_by_dependencies()

        for feature_name in sorted_features:
            try:
                result = await self.enable_feature(feature_name)
                if result["status"] == "success":
                    results["enabled_features"].append(feature_name)
                    results["capabilities_unlocked"].extend(
                        result.get("capabilities_unlocked", [])
                    )
                else:
                    results["failed_features"].append(
                        {"feature": feature_name, "error": result["message"]}
                    )
            except Exception as e:
                results["failed_features"].append(
                    {"feature": feature_name, "error": str(e)}
                )

        logger.info(
            f"✅ Enterprise features enabled: {len(results['enabled_features'])}/{results['total_features']}"
        )
        return results

    def _sort_features_by_dependencies(self) -> List[str]:
        """Sort features by dependency order"""
        sorted_features = []
        remaining_features = set(self.features.keys())

        while remaining_features:
            # Find features with no unmet dependencies
            ready_features = []
            for feature_name in remaining_features:
                feature = self.features[feature_name]
                if all(dep in sorted_features for dep in feature.dependencies):
                    ready_features.append(feature_name)

            if not ready_features:
                # Circular dependency or missing dependency
                sorted_features.extend(remaining_features)
                break

            # Add ready features
            sorted_features.extend(ready_features)
            remaining_features -= set(ready_features)

        return sorted_features

    async def get_enterprise_status(self) -> Dict[str, Any]:
        """Get comprehensive enterprise feature status"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "feature_summary": {
                "total_features": len(self.features),
                "enabled_features": len(
                    [
                        f
                        for f in self.features.values()
                        if f.status == FeatureStatus.ENABLED
                    ]
                ),
                "degraded_features": len(
                    [
                        f
                        for f in self.features.values()
                        if f.status == FeatureStatus.DEGRADED
                    ]
                ),
                "failed_features": len(
                    [
                        f
                        for f in self.features.values()
                        if f.status == FeatureStatus.ERROR
                    ]
                ),
            },
            "features": {},
            "capabilities": {
                "research_orchestration": self._check_research_capabilities(),
                "load_balancing": self._check_load_balancing_capabilities(),
                "resource_optimization": self._check_resource_capabilities(),
                "health_monitoring": self._check_health_capabilities(),
                "failover_recovery": self._check_failover_capabilities(),
            },
            "infrastructure": {
                "vm_topology": self.vm_topology,
                "resource_pools": self.resource_pools,
            },
        }

        # Add detailed feature status
        for name, feature in self.features.items():
            status["features"][name] = {
                "status": feature.status.value,
                "category": feature.category.value,
                "enabled_at": (
                    feature.enabled_at.isoformat() if feature.enabled_at else None
                ),
                "description": feature.description,
                "health_check": (
                    await self._check_feature_health(name)
                    if feature.status == FeatureStatus.ENABLED
                    else None
                ),
            }

        return status

    # Placeholder methods for implementation
    async def _update_chat_workflow_config(self, config_updates: Dict[str, Any]):
        """Update chat workflow configuration"""
        logger.info("Updating chat workflow config: %s", config_updates)

    async def _initialize_research_endpoints(self):
        """Initialize research service endpoints"""
        logger.info("Initializing research endpoints")

    async def _create_load_balancer_service(self, config: Dict[str, Any]):
        """Create load balancer service"""
        logger.info("Creating load balancer service: %s", config)

    async def _detect_hardware_capabilities(self) -> Dict[str, Any]:
        """Detect available hardware capabilities"""
        return {
            "gpu": {"type": "RTX_4070", "available": True},
            "npu": {"type": "Intel_NPU", "available": True},
            "cpu": {"cores": 22, "architecture": "x86_64"},
        }

    async def _create_task_routing_engine(self, config: Dict[str, Any]):
        """Create task routing engine"""
        logger.info("Creating task routing engine: %s", config)

    async def _create_health_monitoring_system(self, config: Dict[str, Any]):
        """Create health monitoring system"""
        logger.info("Creating health monitoring system: %s", config)

    async def _create_degradation_system(
        self, circuit_config: Dict[str, Any], fallback_config: Dict[str, Any]
    ):
        """Create graceful degradation system"""
        logger.info(
            f"Creating degradation system: circuit={circuit_config}, fallback={fallback_config}"
        )

    async def _start_health_monitoring(
        self, feature_name: str, feature: EnterpriseFeature
    ):
        """Start health monitoring for a feature"""
        logger.info("Starting health monitoring for %s", feature_name)

    async def _check_feature_health(self, feature_name: str) -> Dict[str, Any]:
        """Check health of a specific feature"""
        return {"status": "healthy", "last_check": datetime.now().isoformat()}

    def _get_all_service_endpoints(self) -> Dict[str, str]:
        """Get all service endpoints"""
        endpoints = {}
        for vm_name, vm_data in self.vm_topology.items():
            for service in vm_data["services"]:
                endpoints[service] = f"http://{vm_data['ip']}:{vm_data['ports'][0]}"
        return endpoints

    def _get_fallback_endpoints(self) -> Dict[str, str]:
        """Get fallback service endpoints"""
        import os

        backend_host = os.getenv("AUTOBOT_BACKEND_HOST")
        backend_port = os.getenv("AUTOBOT_BACKEND_PORT")
        frontend_host = os.getenv("AUTOBOT_FRONTEND_HOST")
        frontend_port = os.getenv("AUTOBOT_FRONTEND_PORT")
        ai_stack_host = os.getenv("AUTOBOT_AI_STACK_HOST")
        ai_stack_port = os.getenv("AUTOBOT_AI_STACK_PORT")

        if not all(
            [
                backend_host,
                backend_port,
                frontend_host,
                frontend_port,
                ai_stack_host,
                ai_stack_port,
            ]
        ):
            raise ValueError(
                "Fallback endpoint configuration missing: All AUTOBOT_*_HOST and "
                "AUTOBOT_*_PORT environment variables must be set"
            )

        return {
            "backend_api": f"http://{backend_host}:{backend_port}/health",
            "web_interface": f"http://{frontend_host}:{frontend_port}/health",
            "ai_processing": f"http://{ai_stack_host}:{ai_stack_port}/health",
        }

    def _check_research_capabilities(self) -> bool:
        """Check if research capabilities are enabled"""
        return (
            self.features.get(
                "web_research_orchestration",
                EnterpriseFeature("", FeatureCategory.RESEARCH_ORCHESTRATION, ""),
            ).status
            == FeatureStatus.ENABLED
        )

    def _check_load_balancing_capabilities(self) -> bool:
        """Check if load balancing is enabled"""
        return (
            self.features.get(
                "cross_vm_load_balancing",
                EnterpriseFeature("", FeatureCategory.LOAD_BALANCING, ""),
            ).status
            == FeatureStatus.ENABLED
        )

    def _check_resource_capabilities(self) -> bool:
        """Check if resource optimization is enabled"""
        return (
            self.features.get(
                "intelligent_task_routing",
                EnterpriseFeature("", FeatureCategory.RESOURCE_OPTIMIZATION, ""),
            ).status
            == FeatureStatus.ENABLED
        )

    def _check_health_capabilities(self) -> bool:
        """Check if health monitoring is enabled"""
        return (
            self.features.get(
                "comprehensive_health_monitoring",
                EnterpriseFeature("", FeatureCategory.HEALTH_MONITORING, ""),
            ).status
            == FeatureStatus.ENABLED
        )

    def _check_failover_capabilities(self) -> bool:
        """Check if failover capabilities are enabled"""
        return (
            self.features.get(
                "graceful_degradation",
                EnterpriseFeature("", FeatureCategory.FAILOVER_RECOVERY, ""),
            ).status
            == FeatureStatus.ENABLED
        )


# Singleton instance (thread-safe)
import threading

_enterprise_manager: Optional[EnterpriseFeatureManager] = None
_enterprise_manager_lock = threading.Lock()


def get_enterprise_manager() -> EnterpriseFeatureManager:
    """Get singleton enterprise feature manager (thread-safe)"""
    global _enterprise_manager
    if _enterprise_manager is None:
        with _enterprise_manager_lock:
            # Double-check after acquiring lock
            if _enterprise_manager is None:
                _enterprise_manager = EnterpriseFeatureManager()
    return _enterprise_manager
