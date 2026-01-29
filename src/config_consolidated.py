"""
Unified Configuration Management System - CONSOLIDATED VERSION

This module consolidates all configuration management capabilities:
- Async config operations with Redis caching (from async_config_manager)
- Simple dot-notation access (from config_helper)
- Legacy variable exports (from main config)
- Default config management (from utils.config_manager)
- File watching and auto-reload
- Distributed config caching

FEATURES CONSOLIDATED:
✅ Async file I/O operations
✅ Redis-based distributed caching  
✅ Dot-notation configuration access
✅ Legacy variable backward compatibility
✅ YAML configuration loading
✅ Environment variable overrides
✅ File watching and auto-reload
✅ Pydantic validation
✅ Default configuration fallbacks
✅ Service URL generation
✅ Host/port resolution

USAGE:
    from src.config_consolidated import config, cfg
    
    # Async usage
    await config.async_get("backend.timeout")
    
    # Sync usage  
    timeout = cfg.get("backend.timeout")
    
    # Legacy variables (backward compatibility)
    from src.config_consolidated import BACKEND_HOST_IP, OLLAMA_PORT
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiofiles
import yaml
from pydantic import BaseSettings, Field, validator
from tenacity import retry, stop_after_attempt, wait_exponential

# Optional imports for advanced features
try:
    from src.utils.async_redis_manager import redis_get, redis_set
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    
try:
    from src.utils.service_registry import get_service_url
    SERVICE_REGISTRY_AVAILABLE = True
except ImportError:
    SERVICE_REGISTRY_AVAILABLE = False

# Import SSOT config for infrastructure values
try:
    from src.config.ssot_config import get_config as get_ssot_config
    _SSOT_AVAILABLE = True
except ImportError:
    _SSOT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ConsolidatedConfigSettings(BaseSettings):
    """Base configuration settings with all consolidated features"""
    
    # File paths
    config_dir: Path = Field(default=Path("config"), env="CONFIG_DIR")
    config_file: str = Field(default="config.yaml", env="CONFIG_FILE")
    complete_config_file: str = Field(default="complete.yaml", env="COMPLETE_CONFIG_FILE")
    settings_file: str = Field(default="settings.json", env="SETTINGS_FILE")
    
    # Cache settings
    cache_ttl: int = Field(default=300, env="CONFIG_CACHE_TTL")  # 5 minutes
    auto_reload: bool = Field(default=True, env="CONFIG_AUTO_RELOAD")
    
    # Redis settings for distributed config
    use_redis_cache: bool = Field(default=True, env="USE_REDIS_CONFIG_CACHE")
    redis_key_prefix: str = Field(default="config:", env="CONFIG_REDIS_PREFIX")
    
    # Legacy support
    enable_legacy_variables: bool = Field(default=True, env="ENABLE_LEGACY_CONFIG_VARS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


class ConsolidatedConfigManager:
    """
    Unified configuration manager with all features:
    - Async operations with Redis caching
    - Dot-notation access
    - Legacy variable exports
    - File watching and validation
    """
    
    def __init__(self, config_settings: Optional[ConsolidatedConfigSettings] = None):
        self.settings = config_settings or ConsolidatedConfigSettings()
        self._config_cache = {}
        self._complete_config_cache = {}
        self._last_reload = None
        self._file_watchers = {}
        
        # Load all configurations
        self._load_default_config()
        self._load_yaml_config()
        self._load_complete_config()
        
        if self.settings.enable_legacy_variables:
            self._export_legacy_variables()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load comprehensive default configuration"""
        return {
            "backend": {
                "api_endpoint": "http://localhost:8001",
                "server_host": "localhost", 
                "server_port": 8001,
                "timeout": 60,
                "max_retries": 3,
                "streaming": False,
                "cors_origins": ["http://localhost:5173", "http://localhost:3000"]
            },
            "frontend": {
                "server_host": "localhost",
                "server_port": 5173
            },
            "infrastructure": self._get_infrastructure_config(),
            "llm": {
                "provider_type": "local",
                "local": {
                    "provider": "ollama",
                    "providers": {
                        "ollama": {
                            "host": "http://localhost:11434",
                            "endpoint": "http://localhost:11434/api/generate",
                            "selected_model": "llama3.2:1b-instruct-q4_K_M",
                            "classification_model": "gemma2:2b",
                            "models": []
                        }
                    }
                }
            },
            "chat": {
                "max_messages": 100,
                "auto_scroll": True,
                "message_retention_days": 30
            },
            "knowledge_base": {
                "enabled": True,
                "update_frequency_days": 7
            },
            "logging": {
                "level": "INFO",
                "backend_log_file": "logs/backend.log",
                "frontend_log_file": "logs/frontend.log"
            },
            "developer": {
                "debug_logging": True,
                "enabled": True,
                "enhanced_errors": True
            }
        }

    def _get_infrastructure_config(self) -> Dict[str, Any]:
        """
        Get infrastructure config from SSOT or fallback defaults.

        Issue #694: Config consolidation - single source of truth.
        """
        if _SSOT_AVAILABLE:
            try:
                ssot = get_ssot_config()
                return {
                    "hosts": {
                        "backend": ssot.vm.main,
                        "frontend": ssot.vm.frontend,
                        "redis": ssot.vm.redis,
                        "ollama": ssot.vm.ollama,
                        "ai_stack": ssot.vm.aistack,
                        "npu_worker": ssot.vm.npu,
                        "browser_service": ssot.vm.browser,
                    },
                    "ports": {
                        "backend": ssot.port.backend,
                        "frontend": ssot.port.frontend,
                        "redis": ssot.port.redis,
                        "ollama": ssot.port.ollama,
                        "ai_stack": ssot.port.aistack,
                        "npu_worker": ssot.port.npu,
                        "browser_service": ssot.port.browser,
                        "vnc": ssot.port.vnc,
                    },
                    "protocols": {
                        "default": "http",
                        "secure": "https",
                    },
                }
            except Exception as e:
                logger.warning(f"SSOT config unavailable: {e}, using defaults")

        # Fallback defaults
        return {
            "hosts": {
                "backend": "172.16.168.20",
                "frontend": "172.16.168.21",
                "redis": "172.16.168.23",
                "ollama": "127.0.0.1",
                "ai_stack": "172.16.168.24",
                "npu_worker": "172.16.168.22",
                "browser_service": "172.16.168.25",
            },
            "ports": {
                "backend": 8001,
                "frontend": 5173,
                "redis": 6379,
                "ollama": 11434,
                "ai_stack": 8080,
                "npu_worker": 8081,
                "browser_service": 3000,
                "vnc": 6080,
            },
            "protocols": {
                "default": "http",
                "secure": "https",
            },
        }

    def _load_yaml_config(self):
        """Load YAML configuration with fallback to defaults"""
        self._config_cache = self._load_default_config()
        
        try:
            config_path = Path(self.settings.config_file)
            if config_path.exists():
                with open(config_path, "r") as f:
                    file_config = yaml.safe_load(f) or {}
                self._merge_configs(self._config_cache, file_config)
                logger.info(f"YAML configuration loaded from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load YAML config: {e}")
    
    def _load_complete_config(self):
        """Load complete configuration from complete.yaml"""
        try:
            complete_path = Path(self.settings.config_dir) / self.settings.complete_config_file
            if complete_path.exists():
                with open(complete_path, 'r') as f:
                    self._complete_config_cache = yaml.safe_load(f) or {}
                logger.info("Complete configuration loaded successfully")
        except Exception as e:
            logger.warning(f"Complete config not available: {e}")
            self._complete_config_cache = {}
    
    def _merge_configs(self, base_config: Dict, new_config: Dict):
        """Recursively merge configuration dictionaries"""
        for key, value in new_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                self._merge_configs(base_config[key], value)
            else:
                base_config[key] = value
    
    def _export_legacy_variables(self):
        """Export legacy variables for backward compatibility"""
        try:
            # Service Host IP Addresses
            self.OLLAMA_HOST_IP = self.get_host('ollama')
            self.LM_STUDIO_HOST_IP = self.get_host('ollama')
            self.BACKEND_HOST_IP = self.get_host('backend')
            self.FRONTEND_HOST_IP = self.get_host('frontend')
            self.PLAYWRIGHT_HOST_IP = self.get_host('browser_service')
            self.NPU_WORKER_HOST_IP = self.get_host('npu_worker')
            self.AI_STACK_HOST_IP = self.get_host('ai_stack')
            self.REDIS_HOST_IP = self.get_host('redis')
            
            # Service Ports
            self.BACKEND_PORT = self.get_port('backend')
            self.FRONTEND_PORT = self.get_port('frontend')
            self.OLLAMA_PORT = self.get_port('ollama')
            self.REDIS_PORT = self.get_port('redis')
            self.PLAYWRIGHT_API_PORT = self.get_port('browser_service')
            
            # Protocol
            self.HTTP_PROTOCOL = self.get('infrastructure.protocols.default', 'http')
            
            logger.debug("Legacy configuration variables exported")
        except Exception as e:
            logger.error(f"Failed to export legacy variables: {e}")
    
    # ==============================================
    # DOT-NOTATION ACCESS METHODS (from config_helper)
    # ==============================================
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        Tries complete config first, then falls back to main config.
        """
        # First try complete config
        if self._complete_config_cache:
            value = self._get_nested_value(self._complete_config_cache, path, None)
            if value is not None:
                return value
        
        # Fallback to main config
        return self._get_nested_value(self._config_cache, path, default)
    
    def _get_nested_value(self, config: Dict, path: str, default: Any) -> Any:
        """Get nested value using dot notation"""
        keys = path.split('.')
        current = config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    # ==============================================
    # SERVICE RESOLUTION METHODS (consolidated)
    # ==============================================
    
    def get_host(self, service_name: str) -> str:
        """Get host for a service"""
        return self.get(f'infrastructure.hosts.{service_name}', 'localhost')
    
    def get_port(self, service_name: str) -> int:
        """Get port for a service"""
        default_ports = {
            'backend': 8001, 'frontend': 5173, 'redis': 6379,
            'ollama': 11434, 'ai_stack': 8080, 'npu_worker': 8081,
            'browser_service': 3000, 'vnc': 6080
        }
        return self.get(f'infrastructure.ports.{service_name}', default_ports.get(service_name, 8000))
    
    def get_service_url(self, service_name: str, protocol: str = None) -> str:
        """Generate complete service URL"""
        if not protocol:
            protocol = self.get('infrastructure.protocols.default', 'http')
        
        host = self.get_host(service_name)
        port = self.get_port(service_name)
        
        # CRITICAL FIX: Always use localhost for Ollama service
        if service_name.lower() == 'ollama' and '172.16.168.20' in host:
            host = 'localhost'
            # Also ensure we use the correct port for localhost
            port = 11434
        
        return f"{protocol}://{host}:{port}"
    
    # ==============================================
    # ASYNC METHODS (from async_config_manager)
    # ==============================================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def async_get(self, path: str, default: Any = None, use_cache: bool = True) -> Any:
        """Async configuration retrieval with Redis caching"""
        if not use_cache or not REDIS_AVAILABLE:
            return self.get(path, default)
        
        try:
            # Try Redis cache first
            cache_key = f"{self.settings.redis_key_prefix}{path}"
            cached_value = await redis_get(cache_key)
            
            if cached_value is not None:
                return json.loads(cached_value) if isinstance(cached_value, str) else cached_value
            
            # Get from config and cache result
            value = self.get(path, default)
            if value is not None:
                await redis_set(cache_key, json.dumps(value), expire=self.settings.cache_ttl)
            
            return value
            
        except Exception as e:
            logger.warning(f"Async config cache failed for {path}: {e}")
            return self.get(path, default)
    
    async def async_reload_config(self):
        """Async configuration reload"""
        try:
            async with aiofiles.open(self.settings.config_file, 'r') as f:
                content = await f.read()
                file_config = yaml.safe_load(content) or {}
            
            # Update cache
            self._config_cache = self._load_default_config()
            self._merge_configs(self._config_cache, file_config)
            self._last_reload = datetime.now(timezone.utc)
            
            if self.settings.enable_legacy_variables:
                self._export_legacy_variables()
            
            logger.info("Configuration reloaded asynchronously")
            
        except Exception as e:
            logger.error(f"Async config reload failed: {e}")
    
    async def watch_config_file(self):
        """Watch configuration file for changes"""
        if not self.settings.auto_reload:
            return
            
        # Simplified file watching - check modification time
        config_path = Path(self.settings.config_file)
        last_mtime = None
        
        try:
            if config_path.exists():
                last_mtime = config_path.stat().st_mtime
        except Exception:
            return
        
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                if config_path.exists():
                    current_mtime = config_path.stat().st_mtime
                    if last_mtime and current_mtime > last_mtime:
                        await self.async_reload_config()
                        last_mtime = current_mtime
                        
            except Exception as e:
                logger.warning(f"Config file watching error: {e}")
                await asyncio.sleep(30)  # Wait longer on error


# ==============================================
# GLOBAL INSTANCES AND LEGACY EXPORTS
# ==============================================

# Create global instance
config = ConsolidatedConfigManager()

# Simple dot-notation interface (config_helper compatibility)
class ConfigHelper:
    """Simple interface for dot-notation access"""
    def __init__(self, config_manager):
        self._config = config_manager
    
    def get(self, path: str, default: Any = None) -> Any:
        return self._config.get(path, default)
    
    def get_host(self, service_name: str) -> str:
        return self._config.get_host(service_name)
    
    def get_port(self, service_name: str) -> int:
        return self._config.get_port(service_name)
    
    def get_service_url(self, service_name: str, protocol: str = None) -> str:
        return self._config.get_service_url(service_name, protocol)

cfg = ConfigHelper(config)

# Legacy variable exports for backward compatibility
OLLAMA_HOST_IP = config.OLLAMA_HOST_IP
LM_STUDIO_HOST_IP = config.LM_STUDIO_HOST_IP  
BACKEND_HOST_IP = config.BACKEND_HOST_IP
FRONTEND_HOST_IP = config.FRONTEND_HOST_IP
PLAYWRIGHT_HOST_IP = config.PLAYWRIGHT_HOST_IP
NPU_WORKER_HOST_IP = config.NPU_WORKER_HOST_IP
AI_STACK_HOST_IP = config.AI_STACK_HOST_IP
REDIS_HOST_IP = config.REDIS_HOST_IP

BACKEND_PORT = config.BACKEND_PORT
FRONTEND_PORT = config.FRONTEND_PORT
OLLAMA_PORT = config.OLLAMA_PORT
REDIS_PORT = config.REDIS_PORT
PLAYWRIGHT_API_PORT = config.PLAYWRIGHT_API_PORT

HTTP_PROTOCOL = config.HTTP_PROTOCOL

# Utility functions for service resolution
def get_service_url(service_name: str, protocol: str = None) -> str:
    """Get complete service URL - legacy function"""
    return config.get_service_url(service_name, protocol)

def get_standardized_service_address(service_name: str, port: int, protocol: str = "http") -> str:
    """Legacy function for standardized service addressing"""
    host = config.get_host(service_name) 
    return f"{protocol}://{host}:{port}"

# Service URL configurations  
service_host_mapping = {
    "redis": REDIS_HOST_IP,
    "ollama": OLLAMA_HOST_IP,
    "backend": BACKEND_HOST_IP,
    "frontend": FRONTEND_HOST_IP,
    "ai_stack": AI_STACK_HOST_IP,
    "npu_worker": NPU_WORKER_HOST_IP,
    "browser_service": PLAYWRIGHT_HOST_IP
}

logger.info("Consolidated configuration system initialized with all features")