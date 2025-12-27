"""
Configuration Manager - YAML Configuration Handling

Issue #640: Added re-pairing functionality to reset worker pairing with master.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manager for NPU worker configuration"""

    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_file = self.config_dir / "npu_worker.yaml"
        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            if not self.config_file.exists():
                return self.get_default_config()

            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")
        except Exception as e:
            raise IOError(f"Failed to load config: {e}")

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to YAML file"""
        try:
            # Create backup
            self.create_backup()

            # Save config
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

        except Exception as e:
            raise IOError(f"Failed to save config: {e}")

    def get_yaml_text(self) -> str:
        """Get YAML configuration as text"""
        try:
            if not self.config_file.exists():
                return yaml.safe_dump(
                    self.get_default_config(),
                    default_flow_style=False,
                    sort_keys=False
                )

            with open(self.config_file, 'r', encoding='utf-8') as f:
                return f.read()

        except Exception as e:
            raise IOError(f"Failed to read config: {e}")

    def save_yaml(self, yaml_text: str):
        """Save YAML configuration from text"""
        try:
            # Validate first
            yaml.safe_load(yaml_text)

            # Create backup
            self.create_backup()

            # Save
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write(yaml_text)

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")
        except Exception as e:
            raise IOError(f"Failed to save config: {e}")

    def validate_yaml(self, yaml_text: str) -> bool:
        """Validate YAML text"""
        try:
            yaml.safe_load(yaml_text)
            return True
        except yaml.YAMLError:
            return False

    def create_backup(self):
        """Create backup of current configuration"""
        try:
            if not self.config_file.exists():
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"npu_worker_{timestamp}.yaml"

            with open(self.config_file, 'r', encoding='utf-8') as src:
                with open(backup_file, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())

            # Keep only last 10 backups
            self.cleanup_old_backups()

        except Exception as e:
            logger.warning("Failed to create backup: %s", e)

    def cleanup_old_backups(self):
        """Remove old backup files, keeping only the 10 most recent"""
        try:
            backups = sorted(self.backup_dir.glob("npu_worker_*.yaml"))
            if len(backups) > 10:
                for backup in backups[:-10]:
                    backup.unlink()
        except Exception as e:
            logger.warning("Failed to cleanup backups: %s", e)

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration

        Note: Backend and Redis hosts are intentionally blank.
        These values are fetched via bootstrap from the main AutoBot backend,
        or must be configured by the user in the GUI.
        """
        return {
            'service': {
                'host': '0.0.0.0',
                'port': 8082,
                'workers': 1,
            },
            'backend': {
                'host': '',  # Configure via GUI or bootstrap
                'port': 8001,
            },
            'redis': {
                'host': '',  # Fetched from backend via bootstrap
                'port': 6379,
            },
            'npu': {
                'enabled': True,
                'fallback_to_cpu': True,
                'optimization': {
                    'precision': 'INT8',
                    'batch_size': 32,
                    'num_streams': 2,
                    'num_threads': 4,
                }
            },
            'logging': {
                'level': 'INFO',
                'directory': 'logs',
                'max_size_mb': 100,
                'backup_count': 5,
            }
        }

    # =========================================================================
    # Re-pairing functionality (Issue #640)
    # =========================================================================

    def get_worker_id_file(self) -> Path:
        """Get path to worker ID file"""
        return self.config_dir / ".worker_id"

    def get_bootstrap_cache_file(self) -> Path:
        """Get path to bootstrap cache file"""
        return self.config_dir / ".bootstrap_cache"

    def get_current_worker_id(self) -> Optional[str]:
        """Get current worker ID if paired"""
        worker_id_file = self.get_worker_id_file()
        if worker_id_file.exists():
            try:
                return worker_id_file.read_text(encoding='utf-8').strip()
            except Exception as e:
                logger.warning(f"Failed to read worker ID: {e}")
        return None

    def get_pairing_status(self) -> Dict[str, Any]:
        """Get current pairing status"""
        worker_id = self.get_current_worker_id()
        config = self.load_config()
        backend_host = config.get('backend', {}).get('host', '')

        return {
            'paired': bool(worker_id and backend_host),
            'worker_id': worker_id,
            'backend_host': backend_host,
            'backend_port': config.get('backend', {}).get('port', 8001),
            'redis_host': config.get('redis', {}).get('host', ''),
        }

    def clear_pairing(self) -> Dict[str, Any]:
        """
        Clear pairing data to allow re-pairing with master.

        Issue #640: Removes worker ID and clears backend/redis config,
        forcing the worker to re-register with the master on next start.

        Returns:
            Dict with status and details of what was cleared
        """
        result = {
            'success': True,
            'cleared': [],
            'errors': [],
        }

        # 1. Remove worker ID file
        worker_id_file = self.get_worker_id_file()
        if worker_id_file.exists():
            try:
                old_id = worker_id_file.read_text(encoding='utf-8').strip()
                worker_id_file.unlink()
                result['cleared'].append(f"Worker ID: {old_id}")
                logger.info(f"Cleared worker ID: {old_id}")
            except Exception as e:
                result['errors'].append(f"Failed to remove worker ID file: {e}")
                logger.error(f"Failed to remove worker ID file: {e}")

        # 2. Remove bootstrap cache if exists
        bootstrap_cache = self.get_bootstrap_cache_file()
        if bootstrap_cache.exists():
            try:
                bootstrap_cache.unlink()
                result['cleared'].append("Bootstrap cache")
                logger.info("Cleared bootstrap cache")
            except Exception as e:
                result['errors'].append(f"Failed to remove bootstrap cache: {e}")

        # 3. Clear backend and redis config (but keep other settings)
        try:
            config = self.load_config()
            if config.get('backend', {}).get('host'):
                result['cleared'].append(f"Backend host: {config['backend']['host']}")
                config['backend']['host'] = ''

            if config.get('redis', {}).get('host'):
                result['cleared'].append(f"Redis host: {config['redis']['host']}")
                config['redis']['host'] = ''

            self.save_config(config)
            logger.info("Cleared backend and Redis host configuration")

        except Exception as e:
            result['errors'].append(f"Failed to clear config: {e}")
            logger.error(f"Failed to clear config: {e}")

        result['success'] = len(result['errors']) == 0
        return result

    def is_paired(self) -> bool:
        """Check if worker is currently paired with a master"""
        status = self.get_pairing_status()
        return status['paired']
