# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Startup Dependency Validator

This module validates all critical dependencies and imports at startup to catch
issues early rather than masking them with lazy loading patterns.

Key Features:
- Comprehensive dependency validation
- Early failure detection
- Detailed error reporting
- Graceful fallback mechanisms
- Configuration validation
- Service connectivity testing

Usage:
    from startup_validator import validate_startup_dependencies

    # In app startup
    validation_result = await validate_startup_dependencies()
    if not validation_result.success:
        logger.error("Startup validation failed: %s", validation_result.errors)
"""

import asyncio
import importlib
import logging
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.constants.path_constants import PATH
from config import ConfigManager

from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)

# Create singleton config instance
config = ConfigManager()


@dataclass
class ValidationResult:
    """Result of dependency validation"""

    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str, details: Any = None):
        """Add error to validation result and mark as failed."""
        self.errors.append(error)
        self.success = False
        if details:
            self.details[error] = details

    def add_warning(self, warning: str, details: Any = None):
        """Add warning to validation result without failing."""
        self.warnings.append(warning)
        if details:
            self.details[warning] = details


class StartupValidator:
    """Comprehensive startup dependency validator"""

    def __init__(self):
        """Initialize validator with default validation result and dependency lists."""
        self.result = ValidationResult(success=True)

        # Critical imports that must be available
        self.critical_imports = [
            "fastapi",
            "pydantic",
            "redis",
            "aioredis",
            "jwt",
            "bcrypt",
            "yaml",
            "asyncio",
            "logging",
        ]

        # AutoBot modules that should be importable
        self.autobot_modules = [
            "src.unified_config",
            "src.auth_middleware",
            "src.security_layer",
            "src.knowledge_base_factory",
            "src.knowledge_base",
        ]

        # Optional modules (warnings only if missing)
        # Note: Obsolete chat_workflow_consolidated removed in Issue #567 archive cleanup
        self.optional_modules = [
            "src.agents.kb_librarian_agent",
            "src.agents.librarian_assistant",
            "src.agents.llm_failsafe_agent",
            "src.conversation",
            "src.async_chat_workflow",
            "src.llm_interface",
            "src.circuit_breaker",
        ]

        # Services to validate connectivity
        self.services = {
            "redis": self._validate_redis_connectivity,
            "ollama": self._validate_ollama_connectivity,
            "config": self._validate_configuration,
        }

    async def validate_all(self) -> ValidationResult:
        """Run comprehensive validation"""
        logger.info("Starting comprehensive startup validation...")

        # Step 1: Validate critical Python imports
        self._validate_critical_imports()

        # Step 2: Validate AutoBot modules
        self._validate_autobot_modules()

        # Step 3: Validate optional modules (warnings only)
        self._validate_optional_modules()

        # Step 4: Validate configuration
        await self._validate_configuration()

        # Step 5: Validate service connectivity
        await self._validate_service_connectivity()

        # Step 6: Validate system requirements
        self._validate_system_requirements()

        # Report results
        if self.result.success:
            logger.info(
                f"✅ Startup validation completed successfully. {len(self.result.warnings)} warnings."
            )
        else:
            logger.error(
                "❌ Startup validation failed with %d errors and %d warnings.",
                len(self.result.errors),
                len(self.result.warnings),
            )

        for warning in self.result.warnings:
            logger.warning("⚠️  %s", warning)

        for error in self.result.errors:
            logger.error("❌ %s", error)

        return self.result

    def _validate_critical_imports(self):
        """Validate critical Python dependencies"""
        logger.info("Validating critical Python imports...")

        for module_name in self.critical_imports:
            try:
                importlib.import_module(module_name)
                logger.debug("✅ Critical import: %s", module_name)
            except ImportError as e:
                self.result.add_error(
                    f"Critical import failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()},
                )

    def _validate_autobot_modules(self):
        """Validate AutoBot-specific modules"""
        logger.info("Validating AutoBot modules...")

        for module_name in self.autobot_modules:
            try:
                importlib.import_module(module_name)
                logger.debug("✅ AutoBot module: %s", module_name)
            except ImportError as e:
                self.result.add_error(
                    f"AutoBot module import failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()},
                )
            except Exception as e:
                # Module imported but failed to initialize
                self.result.add_error(
                    f"AutoBot module initialization failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()},
                )

    def _validate_optional_modules(self):
        """Validate optional modules (warnings only)"""
        logger.info("Validating optional modules...")

        for module_name in self.optional_modules:
            try:
                importlib.import_module(module_name)
                logger.debug("✅ Optional module: %s", module_name)
            except ImportError as e:
                self.result.add_warning(
                    f"Optional module not available: {module_name}", {"error": str(e)}
                )
            except Exception as e:
                self.result.add_warning(
                    f"Optional module initialization failed: {module_name}",
                    {"error": str(e)},
                )

    async def _validate_configuration(self):
        """Validate configuration system"""
        logger.info("Validating configuration...")

        try:
            # Test basic config access
            backend_host = config.get_host("backend")
            redis_host = config.get_host("redis")

            if not backend_host:
                self.result.add_error("Backend host not configured")

            if not redis_host:
                self.result.add_error("Redis host not configured")

            # Validate config structure
            config_validation = config.validate()
            if not config_validation["valid"]:
                for issue in config_validation["issues"]:
                    self.result.add_error(f"Configuration issue: {issue}")

            logger.debug("✅ Configuration validation passed")

        except Exception as e:
            self.result.add_error(
                "Configuration system failed",
                {"error": str(e), "traceback": traceback.format_exc()},
            )

    async def _validate_service_connectivity(self):
        """Validate connectivity to external services"""
        logger.info("Validating service connectivity...")

        # Issue #370: Validate all services in parallel
        async def validate_single_service(service_name: str, validator_func):
            """Validate a single service and return result."""
            try:
                await validator_func()
                logger.debug("✅ Service connectivity: %s", service_name)
                return service_name, None
            except Exception as e:
                return service_name, str(e)

        results = await asyncio.gather(
            *[
                validate_single_service(name, func)
                for name, func in self.services.items()
            ],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                # Gather itself failed for some reason
                self.result.add_warning(
                    f"Service validation error: {result}", {"error": str(result)}
                )
            elif result[1] is not None:
                # Service connectivity issues are warnings, not errors
                # The system should still start but with reduced functionality
                service_name, error = result
                self.result.add_warning(
                    f"Service connectivity failed: {service_name}", {"error": error}
                )

    async def _validate_redis_connectivity(self):
        """Test Redis connectivity using canonical Redis utility"""
        try:
            redis_config = config.get_redis_config()
            if not redis_config["enabled"]:
                self.result.add_warning("Redis is disabled in configuration")
                return

            # Use canonical Redis utility instead of direct instantiation
            # This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from autobot_shared.redis_client import get_redis_client

            client = get_redis_client(database="main")
            if client is None:
                raise Exception("Redis client initialization returned None")

            # Test connection
            await asyncio.to_thread(client.ping)
            # Note: Connection pooling means we don't close individual clients
            # The redis_database_manager handles connection lifecycle

        except Exception as e:
            raise Exception(f"Redis connection test failed: {e}")

    async def _validate_ollama_connectivity(self):
        """Test Ollama service connectivity"""
        try:
            import aiohttp

            ollama_url = config.get_service_url("ollama")
            health_url = f"{ollama_url}/api/tags"

            # Use singleton HTTP client for connection pooling
            http_client = get_http_client()
            async with await http_client.get(
                health_url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ollama returned status {response.status}")

        except Exception as e:
            raise Exception(f"Ollama connectivity test failed: {e}")

    def _validate_system_requirements(self):
        """Validate system-level requirements"""
        logger.info("Validating system requirements...")

        # Check Python version
        if sys.version_info < (3, 8):
            self.result.add_error(f"Python 3.8+ required, found {sys.version}")

        # Check disk space for logs and data
        try:
            import shutil

            # Use centralized PathConstants (Issue #380)
            _, _, free_space = shutil.disk_usage(PATH.PROJECT_ROOT)
            free_gb = free_space / (1024**3)

            if free_gb < 1:
                self.result.add_error(
                    f"Insufficient disk space: {free_gb:.1f}GB available, minimum 1GB required"
                )
            elif free_gb < 5:
                self.result.add_warning(f"Low disk space: {free_gb:.1f}GB available")

        except Exception as e:
            self.result.add_warning(f"Could not check disk space: {e}")

        logger.debug("✅ System requirements validation completed")


# Convenience functions
async def validate_startup_dependencies() -> ValidationResult:
    """Main validation function"""
    validator = StartupValidator()
    return await validator.validate_all()


def validate_import_quickly(module_name: str) -> Tuple[bool, Optional[str]]:
    """Quick import validation for a single module"""
    try:
        importlib.import_module(module_name)
        return True, None
    except Exception as e:
        return False, str(e)


async def validate_service_health(service_name: str) -> Tuple[bool, Optional[str]]:
    """Quick service health check"""
    validator = StartupValidator()

    if service_name in validator.services:
        try:
            await validator.services[service_name]()
            return True, None
        except Exception as e:
            return False, str(e)
    else:
        return False, f"Unknown service: {service_name}"


# Export key functions
__all__ = [
    "ValidationResult",
    "StartupValidator",
    "validate_startup_dependencies",
    "validate_import_quickly",
    "validate_service_health",
]
