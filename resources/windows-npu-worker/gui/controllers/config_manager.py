"""
Configuration Manager - YAML Configuration Handling
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from datetime import datetime


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

            with open(self.config_file, 'r') as f:
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
            with open(self.config_file, 'w') as f:
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

            with open(self.config_file, 'r') as f:
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
            with open(self.config_file, 'w') as f:
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

            with open(self.config_file, 'r') as src:
                with open(backup_file, 'w') as dst:
                    dst.write(src.read())

            # Keep only last 10 backups
            self.cleanup_old_backups()

        except Exception as e:
            print(f"Warning: Failed to create backup: {e}")

    def cleanup_old_backups(self):
        """Remove old backup files, keeping only the 10 most recent"""
        try:
            backups = sorted(self.backup_dir.glob("npu_worker_*.yaml"))
            if len(backups) > 10:
                for backup in backups[:-10]:
                    backup.unlink()
        except Exception as e:
            print(f"Warning: Failed to cleanup backups: {e}")

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'service': {
                'host': '0.0.0.0',
                'port': 8082,
                'workers': 1,
            },
            'backend': {
                'host': '172.16.168.20',
                'port': 8001,
            },
            'redis': {
                'host': '172.16.168.23',
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
