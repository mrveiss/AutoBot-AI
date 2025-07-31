"""
Centralized configuration service for backend API.
Eliminates duplication across settings.py, llm.py, and redis.py
"""
import logging
import yaml
import os
import json
from typing import Dict, Any, Optional
from src.config import global_config_manager

logger = logging.getLogger(__name__)

# Path for settings file
SETTINGS_FILE = "config/settings.json"


class ConfigService:
    """Centralized configuration management service"""
    
    @staticmethod
    def get_full_config() -> Dict[str, Any]:
        """Get complete application configuration"""
        try:
            config_data = {
                'backend': {
                    'server_host': global_config_manager.get_nested('backend.server_host', '0.0.0.0'),
                    'server_port': global_config_manager.get_nested('backend.server_port', 8001),
                    'chat_data_dir': global_config_manager.get_nested('backend.chat_data_dir', 'data/chats'),
                    'cors_origins': global_config_manager.get_nested('backend.cors_origins', []),
                    'llm': {
                        'provider_type': 'local',  # Always local for this config
                        'local': {
                            'provider': 'ollama',  # Primary provider from config
                            'providers': {
                                'ollama': {
                                    'endpoint': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434') + '/api/generate',
                                    'host': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434'),
                                    'models': [],  # Will be loaded dynamically
                                    'configured_models': global_config_manager.get_nested('llm_config.ollama.models', {}),
                                    'selected_model': global_config_manager.get_nested('llm_config.default_llm', 'ollama_tinyllama')
                                }
                            }
                        }
                    }
                },
                'llm_config': global_config_manager.get('llm_config', {}),
                'task_transport': global_config_manager.get('task_transport', {}),
                'memory': {
                    'redis': {
                        'enabled': global_config_manager.get_nested('memory.redis.enabled', False),
                        'host': global_config_manager.get_nested('memory.redis.host', 'localhost'),
                        'port': global_config_manager.get_nested('memory.redis.port', 6379)
                    }
                },
                'data': global_config_manager.get_nested('data', {}),
                'hardware_acceleration': global_config_manager.get_nested('hardware_acceleration', {})
            }
            return config_data
        except Exception as e:
            logger.error(f"Error getting full config: {str(e)}")
            raise

    @staticmethod
    def get_llm_config() -> Dict[str, Any]:
        """Get current LLM configuration"""
        try:
            llm_config = global_config_manager.get('llm_config', {})
            backend_config = global_config_manager.get('backend', {})

            # Get default values from config with fallbacks
            default_llm_fallback = global_config_manager.get_nested('defaults.llm.default_llm', 'ollama_tinyllama')
            task_llm_fallback = global_config_manager.get_nested('defaults.llm.task_llm', 'ollama_tinyllama')
            ollama_endpoint_fallback = global_config_manager.get_nested('defaults.llm.ollama.endpoint', 'http://localhost:11434/api/generate')
            ollama_model_fallback = global_config_manager.get_nested('defaults.llm.ollama.model', 'tinyllama:latest')
            ollama_host_fallback = global_config_manager.get_nested('defaults.llm.ollama.host', 'http://localhost:11434')

            return {
                "default_llm": llm_config.get('default_llm', default_llm_fallback),
                "task_llm": llm_config.get('task_llm', task_llm_fallback),
                "ollama": {
                    "endpoint": backend_config.get('ollama_endpoint', ollama_endpoint_fallback),
                    "model": backend_config.get('ollama_model', ollama_model_fallback),
                    "host": llm_config.get('ollama', {}).get('host', ollama_host_fallback),
                    "models": llm_config.get('ollama', {}).get('models', {})
                },
                "openai": llm_config.get('openai', {}),
                "orchestrator_llm_settings": llm_config.get('orchestrator_llm_settings', {}),
                "task_llm_settings": llm_config.get('task_llm_settings', {})
            }
        except Exception as e:
            logger.error(f"Error getting LLM config: {str(e)}")
            raise

    @staticmethod
    def get_redis_config() -> Dict[str, Any]:
        """Get current Redis configuration"""
        try:
            task_transport_config = global_config_manager.get('task_transport', {})
            redis_config = task_transport_config.get('redis', {})

            return {
                "type": task_transport_config.get('type', 'local'),
                "host": redis_config.get('host', 'localhost'),
                "port": redis_config.get('port', 6379),
                "channels": redis_config.get('channels', {}),
                "priority": redis_config.get('priority', 10)
            }
        except Exception as e:
            logger.error(f"Error getting Redis config: {str(e)}")
            raise

    @staticmethod
    def update_llm_config(config_data: Dict[str, Any]) -> Dict[str, str]:
        """Update LLM configuration"""
        try:
            # Load current config
            current_config = global_config_manager.to_dict()

            # Update LLM configuration
            if 'llm_config' not in current_config:
                current_config['llm_config'] = {}
            if 'backend' not in current_config:
                current_config['backend'] = {}

            llm_config = current_config['llm_config']
            backend_config = current_config['backend']

            # Update basic LLM settings
            if 'default_llm' in config_data:
                llm_config['default_llm'] = config_data['default_llm']
            if 'task_llm' in config_data:
                llm_config['task_llm'] = config_data['task_llm']

            # Update Ollama settings
            if 'ollama' in config_data:
                ollama_data = config_data['ollama']
                if 'ollama' not in llm_config:
                    llm_config['ollama'] = {}

                if 'endpoint' in ollama_data:
                    backend_config['ollama_endpoint'] = ollama_data['endpoint']
                if 'model' in ollama_data:
                    backend_config['ollama_model'] = ollama_data['model']
                if 'host' in ollama_data:
                    llm_config['ollama']['host'] = ollama_data['host']
                if 'models' in ollama_data:
                    llm_config['ollama']['models'] = ollama_data['models']

            # Update OpenAI settings
            if 'openai' in config_data:
                llm_config['openai'] = config_data['openai']

            # Update orchestrator and task LLM settings
            if 'orchestrator_llm_settings' in config_data:
                llm_config['orchestrator_llm_settings'] = config_data['orchestrator_llm_settings']
            if 'task_llm_settings' in config_data:
                llm_config['task_llm_settings'] = config_data['task_llm_settings']

            # Save updated config to file
            ConfigService._save_config_to_file(current_config)

            # Reload the global config manager
            global_config_manager.reload()

            logger.info(f"Updated LLM configuration: {config_data}")
            return {"status": "success", "message": "LLM configuration updated successfully"}
        except Exception as e:
            logger.error(f"Error updating LLM config: {str(e)}")
            raise

    @staticmethod
    def update_redis_config(config_data: Dict[str, Any]) -> Dict[str, str]:
        """Update Redis configuration"""
        try:
            # Load current config
            current_config = global_config_manager.to_dict()

            # Update task transport configuration
            if 'task_transport' not in current_config:
                current_config['task_transport'] = {}

            # Update transport type
            if 'type' in config_data:
                current_config['task_transport']['type'] = config_data['type']

            # Update Redis-specific settings
            if 'redis' not in current_config['task_transport']:
                current_config['task_transport']['redis'] = {}

            redis_config = current_config['task_transport']['redis']

            if 'host' in config_data:
                redis_config['host'] = config_data['host']
            if 'port' in config_data:
                redis_config['port'] = int(config_data['port'])
            if 'channels' in config_data:
                redis_config['channels'] = config_data['channels']
            if 'priority' in config_data:
                redis_config['priority'] = int(config_data['priority'])

            # Save updated config to file
            ConfigService._save_config_to_file(current_config)

            # Reload the global config manager
            global_config_manager.reload()

            logger.info(f"Updated Redis configuration: {config_data}")
            return {"status": "success", "message": "Redis configuration updated successfully"}
        except Exception as e:
            logger.error(f"Error updating Redis config: {str(e)}")
            raise

    @staticmethod
    def get_settings() -> Dict[str, Any]:
        """Get settings from settings.json file"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            logger.info("No settings file found, returning empty dict")
            return {}
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            raise

    @staticmethod
    def save_settings(settings_data: Dict[str, Any]) -> Dict[str, str]:
        """Save settings to settings.json file"""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings_data, f, indent=2)
            logger.info("Saved settings")
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
            raise

    @staticmethod
    def get_backend_settings() -> Dict[str, Any]:
        """Get backend-specific settings"""
        try:
            settings = ConfigService.get_settings()
            return settings.get('backend', {})
        except Exception as e:
            logger.error(f"Error loading backend settings: {str(e)}")
            raise

    @staticmethod
    def update_backend_settings(backend_settings: Dict[str, Any]) -> Dict[str, str]:
        """Update backend-specific settings"""
        try:
            # Load current settings
            current_settings = ConfigService.get_settings()
            
            # Update backend settings
            current_settings['backend'] = backend_settings
            
            # Save updated settings
            return ConfigService.save_settings(current_settings)
        except Exception as e:
            logger.error(f"Error updating backend settings: {str(e)}")
            raise

    @staticmethod
    def _save_config_to_file(config: Dict[str, Any]) -> None:
        """Save configuration to config.yaml file"""
        config_file_path = 'config/config.yaml'
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        with open(config_file_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
