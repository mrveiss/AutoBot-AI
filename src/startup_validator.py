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
    from src.startup_validator import validate_startup_dependencies

    # In app startup
    validation_result = await validate_startup_dependencies()
    if not validation_result.success:
        logger.error(f"Startup validation failed: {validation_result.errors}")
"""

import asyncio
import importlib
import logging
import sys
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path

from src.unified_config import config
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of dependency validation"""
    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str, details: Any = None):
        self.errors.append(error)
        self.success = False
        if details:
            self.details[error] = details

    def add_warning(self, warning: str, details: Any = None):
        self.warnings.append(warning)
        if details:
            self.details[warning] = details


class StartupValidator:
    """Comprehensive startup dependency validator"""

    def __init__(self):
        self.result = ValidationResult(success=True)

        # Critical imports that must be available
        self.critical_imports = [
            'fastapi',
            'pydantic',
            'redis',
            'aioredis',
            'jwt',
            'bcrypt',
            'yaml',
            'asyncio',
            'logging'
        ]

        # AutoBot modules that should be importable
        self.autobot_modules = [
            'src.unified_config',
            'src.auth_middleware',
            'src.security_layer',
            'src.knowledge_base_factory',
            'src.knowledge_base_v2'
        ]

        # Optional modules (warnings only if missing)
        self.optional_modules = [
            'src.agents.kb_librarian_agent',
            'src.agents.librarian_assistant_agent',
            'src.agents.llm_failsafe_agent',
            'src.conversation',
            'src.chat_workflow_consolidated',
            'src.llm_interface',
            'src.circuit_breaker'
        ]

        # Services to validate connectivity
        self.services = {
            'redis': self._validate_redis_connectivity,
            'ollama': self._validate_ollama_connectivity,
            'config': self._validate_configuration
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
            logger.info(f"✅ Startup validation completed successfully. {len(self.result.warnings)} warnings.")
        else:
            logger.error(f"❌ Startup validation failed with {len(self.result.errors)} errors and {len(self.result.warnings)} warnings.")

        for warning in self.result.warnings:
            logger.warning(f"⚠️  {warning}")

        for error in self.result.errors:
            logger.error(f"❌ {error}")

        return self.result

    def _validate_critical_imports(self):
        """Validate critical Python dependencies"""
        logger.info("Validating critical Python imports...")

        for module_name in self.critical_imports:
            try:
                importlib.import_module(module_name)
                logger.debug(f"✅ Critical import: {module_name}")
            except ImportError as e:
                self.result.add_error(
                    f"Critical import failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()}
                )

    def _validate_autobot_modules(self):
        """Validate AutoBot-specific modules"""
        logger.info("Validating AutoBot modules...")

        for module_name in self.autobot_modules:
            try:
                importlib.import_module(module_name)
                logger.debug(f"✅ AutoBot module: {module_name}")
            except ImportError as e:
                self.result.add_error(
                    f"AutoBot module import failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()}
                )
            except Exception as e:
                # Module imported but failed to initialize
                self.result.add_error(
                    f"AutoBot module initialization failed: {module_name}",
                    {"error": str(e), "traceback": traceback.format_exc()}
                )

    def _validate_optional_modules(self):
        """Validate optional modules (warnings only)"""
        logger.info("Validating optional modules...")

        for module_name in self.optional_modules:
            try:
                importlib.import_module(module_name)
                logger.debug(f"✅ Optional module: {module_name}")
            except ImportError as e:
                self.result.add_warning(
                    f"Optional module not available: {module_name}",
                    {"error": str(e)}
                )
            except Exception as e:
                self.result.add_warning(
                    f"Optional module initialization failed: {module_name}",
                    {"error": str(e)}
                )

    async def _validate_configuration(self):
        """Validate configuration system"""
        logger.info("Validating configuration...")

        try:
            # Test basic config access
            backend_host = config.get_host('backend')
            redis_host = config.get_host('redis')

            if not backend_host:
                self.result.add_error("Backend host not configured")

            if not redis_host:
                self.result.add_error("Redis host not configured")

            # Validate config structure
            config_validation = config.validate()
            if not config_validation['valid']:
                for issue in config_validation['issues']:
                    self.result.add_error(f"Configuration issue: {issue}")

            logger.debug("✅ Configuration validation passed")

        except Exception as e:
            self.result.add_error(
                "Configuration system failed",
                {"error": str(e), "traceback": traceback.format_exc()}
            )

    async def _validate_service_connectivity(self):
        """Validate connectivity to external services"""
        logger.info("Validating service connectivity...")

        for service_name, validator_func in self.services.items():
            try:
                await validator_func()
                logger.debug(f"✅ Service connectivity: {service_name}")
            except Exception as e:
                # Service connectivity issues are warnings, not errors
                # The system should still start but with reduced functionality
                self.result.add_warning(
                    f"Service connectivity failed: {service_name}",
                    {"error": str(e)}
                )

    async def _validate_redis_connectivity(self):
        """Test Redis connectivity"""
        try:
            redis_config = config.get_redis_config()
            if not redis_config['enabled']:
                self.result.add_warning("Redis is disabled in configuration")
                return

            import redis
            client = redis.Redis(
                host=redis_config['host'],
                port=redis_config['port'],
                db=redis_config['db'],
                socket_timeout=5,
                socket_connect_timeout=5
            )

            # Test connection
            await asyncio.to_thread(client.ping)
            await asyncio.to_thread(client.close)

        except Exception as e:
            raise Exception(f"Redis connection test failed: {e}")

    async def _validate_ollama_connectivity(self):
        """Test Ollama service connectivity"""
        try:
            import aiohttp

            ollama_url = config.get_service_url('ollama')
            health_url = f"{ollama_url}/api/tags"

            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(health_url) as response:
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
            project_root = Path(__file__).parent.parent
            _, _, free_space = shutil.disk_usage(project_root)
            free_gb = free_space / (1024**3)

            if free_gb < 1:
                self.result.add_error(f"Insufficient disk space: {free_gb:.1f}GB available, minimum 1GB required")
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
    'ValidationResult',
    'StartupValidator',
    'validate_startup_dependencies',
    'validate_import_quickly',
    'validate_service_health'
]