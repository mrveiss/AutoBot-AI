"""
Unified Configuration System - Single Source of Truth

This module provides the definitive, single configuration system for AutoBot.
All other configuration modules are deprecated and will be phased out.

Key Features:
- Single configuration file: config/complete.yaml
- Environment variable support with AUTOBOT_ prefix
- Variable substitution with ${path.to.value} syntax
- Proper precedence: Environment > Config File > Defaults
- Thread-safe singleton pattern
- Validation and error handling
- No circular dependencies

Usage:
    from src.unified_config import config
    
    backend_host = config.get_host('backend')
    timeout = config.get_timeout('llm', 'default')
    redis_url = config.get_service_url('redis')
"""

import os
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, List
import yaml
import re
from src.constants import NetworkConstants, ServiceURLs

logger = logging.getLogger(__name__)


class UnifiedConfig:
    """Thread-safe, singleton configuration manager"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._config = {}
        self._config_file = None
        self._initialized = False
        
        # Find configuration file
        self._locate_config_file()
        
        # Load configuration
        self._load_configuration()
        
        self._initialized = True
        logger.info("Unified configuration system initialized successfully")
    
    def _locate_config_file(self) -> None:
        """Locate the configuration file"""
        # Find project root (parent of src directory)
        project_root = Path(__file__).parent.parent
        
        # Look for config/complete.yaml first (preferred)
        complete_config = project_root / 'config' / 'complete.yaml'
        if complete_config.exists():
            self._config_file = complete_config
            logger.info(f"Using complete configuration: {complete_config}")
            return
            
        # Fall back to config/config.yaml
        fallback_config = project_root / 'config' / 'config.yaml'
        if fallback_config.exists():
            self._config_file = fallback_config
            logger.warning(f"Using fallback configuration: {fallback_config}")
            return
            
        raise FileNotFoundError(
            f"No configuration file found. Expected {complete_config} or {fallback_config}"
        )
    
    def _load_configuration(self) -> None:
        """Load configuration with error handling"""
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            
            # Apply variable substitution
            self._substitute_variables()
            
            # Apply environment overrides
            self._apply_environment_overrides()
            
            logger.info(f"Configuration loaded from {self._config_file}")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Load minimal defaults to prevent system failure
            self._load_emergency_defaults()
    
    def _substitute_variables(self) -> None:
        """Substitute ${path.to.value} references in configuration"""
        def substitute_recursive(obj, depth=0):
            if depth > 10:  # Prevent infinite recursion
                logger.warning("Variable substitution depth limit reached")
                return obj
                
            if isinstance(obj, dict):
                return {k: substitute_recursive(v, depth + 1) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_recursive(item, depth + 1) for item in obj]
            elif isinstance(obj, str) and '${' in obj:
                return self._substitute_string_variables(obj, depth)
            else:
                return obj
        
        self._config = substitute_recursive(self._config)
    
    def _substitute_string_variables(self, value: str, depth: int) -> str:
        """Substitute variables in a string value"""
        pattern = r'\$\{([^}]+)\}'
        
        def replace_var(match):
            var_path = match.group(1)
            replacement = self._get_nested_value(var_path)
            if replacement is not None:
                return str(replacement)
            else:
                logger.warning(f"Variable substitution failed for: {var_path}")
                return match.group(0)  # Return original if substitution fails
        
        return re.sub(pattern, replace_var, value)
    
    def _get_nested_value(self, path: str, default: Any = None) -> Any:
        """Get nested configuration value using dot notation"""
        keys = path.split('.')
        current = self._config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides with AUTOBOT_ prefix"""
        env_mappings = {
            # Infrastructure
            'AUTOBOT_BACKEND_HOST': 'infrastructure.hosts.backend',
            'AUTOBOT_FRONTEND_HOST': 'infrastructure.hosts.frontend',
            'AUTOBOT_REDIS_HOST': 'infrastructure.hosts.redis',
            'AUTOBOT_OLLAMA_HOST': 'infrastructure.hosts.ollama',
            'AUTOBOT_BACKEND_PORT': 'infrastructure.ports.backend',
            'AUTOBOT_FRONTEND_PORT': 'infrastructure.ports.frontend',
            'AUTOBOT_REDIS_PORT': 'infrastructure.ports.redis',
            'AUTOBOT_OLLAMA_PORT': 'infrastructure.ports.ollama',
            
            # Timeouts
            'AUTOBOT_LLM_TIMEOUT': 'timeouts.llm.default',
            'AUTOBOT_HTTP_TIMEOUT': 'timeouts.http.standard',
            'AUTOBOT_REDIS_TIMEOUT': 'timeouts.redis.stats_collection',
            
            # Redis
            'AUTOBOT_REDIS_DB': 'redis.databases.main',
            'AUTOBOT_REDIS_PASSWORD': 'redis.password',
            
            # Features
            'AUTOBOT_DEBUG': 'development.debug',
            'AUTOBOT_MONITORING': 'monitoring.enabled',
            
            # Security
            'AUTOBOT_SESSION_TIMEOUT': 'security.session.timeout_minutes',
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert string values to appropriate types
                converted_value = self._convert_env_value(env_value)
                self._set_nested_value(config_path, converted_value)
                logger.info(f"Applied environment override: {env_var} = {converted_value}")
    
    def _convert_env_value(self, value: str) -> Any:
        """Convert environment variable string to appropriate type"""
        # Boolean conversion
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer conversion
        if value.isdigit():
            return int(value)
        
        # Float conversion
        try:
            if '.' in value:
                return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    def _set_nested_value(self, path: str, value: Any) -> None:
        """Set nested configuration value using dot notation"""
        keys = path.split('.')
        current = self._config
        
        # Navigate to parent of target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the value
        current[keys[-1]] = value
    
    def _load_emergency_defaults(self) -> None:
        """Load minimal emergency defaults to prevent system failure"""
        logger.warning("Loading emergency configuration defaults")
        
        self._config = {
            'infrastructure': {
                'hosts': {
                    'backend': '172.16.168.20',
                    'frontend': '172.16.168.21',
                    'redis': '172.16.168.23',
                    'ollama': '172.16.168.20',
                    'ai_stack': '172.16.168.24',
                    'npu_worker': '172.16.168.22',
                    'browser_service': '172.16.168.25'
                },
                'ports': {
                    'backend': 8001,
                    'frontend': 5173,
                    'redis': 6379,
                    'ollama': 11434,
                    'ai_stack': 8080,
                    'npu_worker': 8081,
                    'browser_service': 3000
                }
            },
            'timeouts': {
                'llm': {'default': 120},
                'http': {'standard': 30},
                'redis': {'stats_collection': 15}
            },
            'redis': {
                'enabled': True,
                'databases': {'main': 0},
                'connection': {
                    'socket_timeout': 2,
                    'socket_connect_timeout': 2,
                    'retry_on_timeout': False
                }
            }
        }
    
    # Public API methods
    
    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        return self._get_nested_value(path, default)

    def set_nested(self, path: str, value: Any) -> None:
        """Set configuration value using dot notation"""
        with self._lock:
            self._set_nested_value(path, value)

    def get_host(self, service: str, default: str = '127.0.0.1') -> str:
        """Get host IP for a service"""
        return self.get(f'infrastructure.hosts.{service}', default)
    
    def get_port(self, service: str, default: int = 8000) -> int:
        """Get port for a service"""
        return self.get(f'infrastructure.ports.{service}', default)
    
    def get_timeout(self, category: str, timeout_type: str = 'default', default: float = 60.0) -> float:
        """Get timeout value for category and type"""
        return float(self.get(f'timeouts.{category}.{timeout_type}', default))
    
    def get_service_url(self, service: str, endpoint: str = None) -> str:
        """Get complete service URL with optional endpoint"""
        # Try to get from services section first
        base_url = self.get(f'services.{service}.base_url')
        
        if not base_url:
            # Build URL from infrastructure settings
            host = self.get_host(service)
            port = self.get_port(service)
            protocol = 'http'  # Default protocol
            
            # Special cases for protocols
            if service == 'redis':
                protocol = 'redis'
            
            base_url = f"{protocol}://{host}:{port}"
        
        if endpoint:
            return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        return base_url
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration"""
        redis_config = self.get('redis', {})
        
        # Ensure required fields with proper defaults
        config = {
            'enabled': redis_config.get('enabled', True),
            'host': self.get_host('redis', '172.16.168.23'),
            'port': self.get_port('redis', 6379),
            'password': redis_config.get('password'),
            'db': redis_config.get('databases', {}).get('main', 0),
            'decode_responses': True,
            'socket_timeout': redis_config.get('connection', {}).get('socket_timeout', 2.0),
            'socket_connect_timeout': redis_config.get('connection', {}).get('socket_connect_timeout', 2.0),
            'retry_on_timeout': redis_config.get('connection', {}).get('retry_on_timeout', False)
        }
        
        return config
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get(f'features.{feature}', False)
    
    def get_path(self, category: str, name: str = None) -> str:
        """Get file or directory path"""
        if name:
            return self.get(f'paths.{category}.{name}', f'{category}/{name}')
        return self.get(f'paths.{category}.directory', category)

    def get_timeout_for_env(self, category: str, timeout_type: str,
                            environment: str = None, default: float = 60.0) -> float:
        """
        Get environment-aware timeout value.

        Args:
            category: Category path (e.g., 'redis.operations')
            timeout_type: Specific timeout type (e.g., 'get')
            environment: Environment name ('development', 'production')
            default: Fallback value if not found

        Returns:
            Timeout value in seconds
        """
        if environment is None:
            environment = os.getenv('AUTOBOT_ENVIRONMENT', 'production')

        # Try environment-specific override first
        env_path = f'environments.{environment}.timeouts.{category}.{timeout_type}'
        env_timeout = self.get(env_path)
        if env_timeout is not None:
            return float(env_timeout)

        # Fall back to base configuration
        base_path = f'timeouts.{category}.{timeout_type}'
        base_timeout = self.get(base_path, default)
        return float(base_timeout)

    def get_timeout_group(self, category: str, environment: str = None) -> Dict[str, float]:
        """
        Get all timeouts for a category as a dictionary.

        Args:
            category: Category path (e.g., 'redis.operations')
            environment: Environment name (optional)

        Returns:
            Dictionary of timeout names to values
        """
        base_path = f'timeouts.{category}'
        base_config = self.get(base_path, {})

        if not isinstance(base_config, dict):
            return {}

        # Apply environment overrides if specified
        if environment:
            env_path = f'environments.{environment}.timeouts.{category}'
            env_overrides = self.get(env_path, {})
            if isinstance(env_overrides, dict):
                base_config = {**base_config, **env_overrides}

        # Convert all values to float
        result = {}
        for k, v in base_config.items():
            if isinstance(v, (int, float)):
                result[k] = float(v)

        return result

    def validate_timeouts(self) -> Dict[str, Any]:
        """
        Validate all timeout configurations.

        Returns:
            Validation report with issues and warnings
        """
        issues = []
        warnings = []

        # Check required timeout categories
        required_categories = ['redis', 'llamaindex', 'documents', 'http', 'llm']
        for category in required_categories:
            timeout_config = self.get(f'timeouts.{category}')
            if timeout_config is None:
                issues.append(f"Missing timeout configuration for '{category}'")

        # Validate timeout ranges
        all_timeouts = self.get('timeouts', {})

        def check_timeout_values(config, path=''):
            for key, value in config.items():
                current_path = f'{path}.{key}' if path else key
                if isinstance(value, dict):
                    check_timeout_values(value, current_path)
                elif isinstance(value, (int, float)):
                    if value <= 0:
                        issues.append(f"Invalid timeout '{current_path}': {value} (must be > 0)")
                    elif value > 600:
                        warnings.append(f"Very long timeout '{current_path}': {value}s (> 10 minutes)")

        check_timeout_values(all_timeouts)

        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }

    def reload(self) -> None:
        """Reload configuration from file"""
        with self._lock:
            self._load_configuration()
            logger.info("Configuration reloaded successfully")
    
    def validate(self) -> Dict[str, Any]:
        """Validate configuration and return status"""
        issues = []
        
        # Check required services have hosts and ports
        required_services = ['backend', 'frontend', 'redis', 'ollama']
        for service in required_services:
            if not self.get_host(service):
                issues.append(f"Missing host for {service}")
            if not self.get_port(service):
                issues.append(f"Missing port for {service}")
        
        # Check Redis configuration
        redis_config = self.get_redis_config()
        if redis_config['enabled'] and not redis_config['host']:
            issues.append("Redis enabled but no host configured")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'config_file': str(self._config_file),
            'services': {
                service: {
                    'host': self.get_host(service),
                    'port': self.get_port(service),
                    'url': self.get_service_url(service)
                }
                for service in required_services
            }
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get('security', {
            'session': {'timeout_minutes': 30},
            'encryption': {'enabled': False}
        })
    
    def get_cors_origins(self) -> List[str]:
        """Get CORS origins for the backend"""
        configured_origins = self.get('security.cors_origins', [])
        
        # Add dynamic origins based on frontend configuration
        frontend_host = self.get_host('frontend')
        frontend_port = self.get_port('frontend')
        
        dynamic_origins = [
            f"http://{frontend_host}:{frontend_port}",
            ServiceURLs.FRONTEND_LOCAL,
            "http://127.0.0.1:5173"
        ]
        
        # Combine and deduplicate
        all_origins = list(set(configured_origins + dynamic_origins))
        return all_origins


# Create singleton instance
config = UnifiedConfig()

# Convenience functions for backward compatibility
def get_host(service: str, default: str = '127.0.0.1') -> str:
    return config.get_host(service, default)

def get_port(service: str, default: int = 8000) -> int:
    return config.get_port(service, default)

def get_service_url(service: str, endpoint: str = None) -> str:
    return config.get_service_url(service, endpoint)

def get_timeout(category: str, timeout_type: str = 'default', default: float = 60.0) -> float:
    return config.get_timeout(category, timeout_type, default)

def get_redis_config() -> Dict[str, Any]:
    return config.get_redis_config()

# Export commonly used values
BACKEND_HOST = config.get_host('backend')
BACKEND_PORT = config.get_port('backend')
FRONTEND_HOST = config.get_host('frontend')
FRONTEND_PORT = config.get_port('frontend')
REDIS_HOST = config.get_host('redis')
REDIS_PORT = config.get_port('redis')
OLLAMA_HOST = config.get_host('ollama')
OLLAMA_PORT = config.get_port('ollama')

# Service URLs
BACKEND_URL = config.get_service_url('backend')
FRONTEND_URL = config.get_service_url('frontend')
REDIS_URL = config.get_service_url('redis')
OLLAMA_URL = config.get_service_url('ollama')

# Timeouts
DEFAULT_TIMEOUT = config.get_timeout('http', 'standard')
LLM_TIMEOUT = config.get_timeout('llm', 'default')
REDIS_TIMEOUT = config.get_timeout('redis', 'stats_collection')

logger.info(f"Unified config exports - Backend: {BACKEND_URL}, Redis: {REDIS_URL}, Ollama: {OLLAMA_URL}")
