"""
Centralized configuration service for backend API.
Eliminates duplication across settings.py, llm.py, and redis.py
"""
import logging
import yaml
import os
from typing import Dict, Any, Optional
from src.config import global_config_manager

logger = logging.getLogger(__name__)


class ConfigService:
    """Centralized configuration management service"""
    
    @staticmethod
    def get_full_config() -> Dict[str, Any]:
        """Get complete application configuration"""
        try:
            # Get the current LLM to determine which model is actually being used
            current_llm = global_config_manager.get_nested('llm_config.default_llm', 'ollama_tinyllama')
            
            # Build comprehensive config structure matching frontend expectations
            # Note: Prompts section is excluded as it's managed separately
            config_data = {
                'message_display': {
                    'show_thoughts': global_config_manager.get_nested('message_display.show_thoughts', True),
                    'show_json': global_config_manager.get_nested('message_display.show_json', False),
                    'show_utility': global_config_manager.get_nested('message_display.show_utility', False),
                    'show_planning': global_config_manager.get_nested('message_display.show_planning', True),
                    'show_debug': global_config_manager.get_nested('message_display.show_debug', False)
                },
                'chat': {
                    'auto_scroll': global_config_manager.get_nested('chat.auto_scroll', True),
                    'max_messages': global_config_manager.get_nested('chat.max_messages', 100),
                    'message_retention_days': global_config_manager.get_nested('chat.message_retention_days', 30)
                },
                'backend': {
                    'api_endpoint': global_config_manager.get_nested('backend.api_endpoint', 'http://localhost:8001'),
                    'server_host': global_config_manager.get_nested('backend.server_host', '0.0.0.0'),
                    'server_port': global_config_manager.get_nested('backend.server_port', 8001),
                    'chat_data_dir': global_config_manager.get_nested('backend.chat_data_dir', 'data/chats'),
                    'chat_history_file': global_config_manager.get_nested('backend.chat_history_file', 'data/chat_history.json'),
                    'knowledge_base_db': global_config_manager.get_nested('backend.knowledge_base_db', 'data/knowledge_base.db'),
                    'reliability_stats_file': global_config_manager.get_nested('backend.reliability_stats_file', 'data/reliability_stats.json'),
                    'audit_log_file': global_config_manager.get_nested('backend.audit_log_file', 'data/audit.log'),
                    'cors_origins': global_config_manager.get_nested('backend.cors_origins', []),
                    'timeout': global_config_manager.get_nested('backend.timeout', 60),
                    'max_retries': global_config_manager.get_nested('backend.max_retries', 3),
                    'streaming': global_config_manager.get_nested('backend.streaming', False),
                    'llm': {
                        'provider_type': 'local',  # Default to local
                        'local': {
                            'provider': 'ollama',  # Default to ollama
                            'providers': {
                                'ollama': {
                                    'endpoint': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434') + '/api/generate',
                                    'host': global_config_manager.get_nested('llm_config.ollama.host', 'http://localhost:11434'),
                                    'models': [],  # Will be loaded dynamically
                                    'selected_model': current_llm
                                },
                                'lmstudio': {
                                    'endpoint': 'http://localhost:1234/v1',
                                    'models': [],
                                    'selected_model': ''
                                }
                            }
                        },
                        'cloud': {
                            'provider': 'openai',
                            'providers': {
                                'openai': {
                                    'api_key': global_config_manager.get_nested('llm_config.openai.api_key', ''),
                                    'endpoint': global_config_manager.get_nested('llm_config.openai.endpoint', 'https://api.openai.com/v1'),
                                    'models': global_config_manager.get_nested('llm_config.openai.models', ['gpt-3.5-turbo', 'gpt-4']),
                                    'selected_model': ''
                                },
                                'anthropic': {
                                    'api_key': global_config_manager.get_nested('llm_config.anthropic.api_key', ''),
                                    'endpoint': global_config_manager.get_nested('llm_config.anthropic.endpoint', 'https://api.anthropic.com/v1'),
                                    'models': global_config_manager.get_nested('llm_config.anthropic.models', ['claude-3-sonnet-20240229', 'claude-3-haiku-20240307']),
                                    'selected_model': ''
                                }
                            }
                        }
                    }
                },
                'ui': {
                    'theme': global_config_manager.get_nested('ui.theme', 'light'),
                    'font_size': global_config_manager.get_nested('ui.font_size', 'medium'),
                    'language': global_config_manager.get_nested('ui.language', 'en'),
                    'animations': global_config_manager.get_nested('ui.animations', True),
                    'developer_mode': global_config_manager.get_nested('ui.developer_mode', False)
                },
                'security': {
                    'enable_encryption': global_config_manager.get_nested('security.enable_encryption', False),
                    'session_timeout_minutes': global_config_manager.get_nested('security.session_timeout_minutes', 30)
                },
                'logging': {
                    'log_level': global_config_manager.get_nested('logging.log_level', 'info'),
                    'log_to_file': global_config_manager.get_nested('logging.log_to_file', True),
                    'log_file_path': global_config_manager.get_nested('logging.log_file_path', 'logs/autobot.log')
                },
                'knowledge_base': {
                    'enabled': global_config_manager.get_nested('knowledge_base.enabled', True),
                    'update_frequency_days': global_config_manager.get_nested('knowledge_base.update_frequency_days', 7)
                },
                'voice_interface': {
                    'enabled': global_config_manager.get_nested('voice_interface.enabled', False),
                    'voice': global_config_manager.get_nested('voice_interface.voice', 'default'),
                    'speech_rate': global_config_manager.get_nested('voice_interface.speech_rate', 1.0)
                },
                'memory': {
                    'long_term': {
                        'enabled': global_config_manager.get_nested('memory.long_term.enabled', True),
                        'retention_days': global_config_manager.get_nested('memory.long_term.retention_days', 30)
                    },
                    'short_term': {
                        'enabled': global_config_manager.get_nested('memory.short_term.enabled', True),
                        'duration_minutes': global_config_manager.get_nested('memory.short_term.duration_minutes', 30)
                    },
                    'vector_storage': {
                        'enabled': global_config_manager.get_nested('memory.vector_storage.enabled', True),
                        'update_frequency_days': global_config_manager.get_nested('memory.vector_storage.update_frequency_days', 7)
                    },
                    'chromadb': {
                        'enabled': global_config_manager.get_nested('memory.chromadb.enabled', True),
                        'path': global_config_manager.get_nested('memory.chromadb.path', 'data/chromadb'),
                        'collection_name': global_config_manager.get_nested('memory.chromadb.collection_name', 'autobot_memory')
                    },
                    'redis': {
                        'enabled': global_config_manager.get_nested('memory.redis.enabled', False),
                        'host': global_config_manager.get_nested('memory.redis.host', 'localhost'),
                        'port': global_config_manager.get_nested('memory.redis.port', 6379)
                    }
                },
                'developer': {
                    'enabled': global_config_manager.get_nested('developer.enabled', False),
                    'enhanced_errors': global_config_manager.get_nested('developer.enhanced_errors', True),
                    'endpoint_suggestions': global_config_manager.get_nested('developer.endpoint_suggestions', True),
                    'debug_logging': global_config_manager.get_nested('developer.debug_logging', False)
                },
                'prompts': {
                    'list': [],
                    'selectedPrompt': None,
                    'editedContent': '',
                    'defaults': {}
                }
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
    def save_full_config(config_data: Dict[str, Any]) -> Dict[str, str]:
        """Save complete application configuration to config.yaml and reload"""
        try:
            # Save configuration to config.yaml
            ConfigService._save_config_to_file(config_data)
            
            # Reload the global config manager to pick up changes
            global_config_manager.reload()
            
            logger.info("Full configuration saved and reloaded successfully")
            return {"status": "success", "message": "Configuration saved and reloaded successfully"}
        except Exception as e:
            logger.error(f"Error saving full config: {str(e)}")
            raise

    @staticmethod
    def get_backend_settings() -> Dict[str, Any]:
        """Get backend-specific settings from config.yaml"""
        try:
            return global_config_manager.get('backend', {})
        except Exception as e:
            logger.error(f"Error loading backend settings: {str(e)}")
            raise

    @staticmethod
    def update_backend_settings(backend_settings: Dict[str, Any]) -> Dict[str, str]:
        """Update backend-specific settings in config.yaml"""
        try:
            # Load current config
            current_config = global_config_manager.to_dict()
            
            # Update backend settings
            current_config['backend'] = backend_settings
            
            # Save updated config to file
            ConfigService._save_config_to_file(current_config)
            
            # Reload the global config manager
            global_config_manager.reload()
            
            logger.info("Updated backend settings in config.yaml")
            return {"status": "success", "message": "Backend settings updated successfully"}
        except Exception as e:
            logger.error(f"Error updating backend settings: {str(e)}")
            raise

    @staticmethod
    def _save_config_to_file(config: Dict[str, Any]) -> None:
        """Save configuration to config.yaml file"""
        # Use the same dynamic path resolution as the config manager
        config_file_path = global_config_manager.base_config_file
        config_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
