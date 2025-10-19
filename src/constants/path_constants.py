"""
Centralized Path Constants for AutoBot
Single source of truth for all path configurations
"""

import os
from dataclasses import dataclass
from pathlib import Path

from src.constants.network_constants import NetworkConstants


@dataclass(frozen=True)
class PathConstants:
    """Centralized path constants - NO HARDCODED PATHS"""

    # Project root - dynamically determined
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent

    # Core directories
    CONFIG_DIR: Path = PROJECT_ROOT / "config"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    DOCS_DIR: Path = PROJECT_ROOT / "docs"
    SRC_DIR: Path = PROJECT_ROOT / "src"
    TESTS_DIR: Path = PROJECT_ROOT / "tests"
    BACKEND_DIR: Path = PROJECT_ROOT / "backend"

    # Configuration subdirectories
    SECURITY_CONFIG_DIR: Path = CONFIG_DIR / "security"
    REDIS_CONFIG_DIR: Path = CONFIG_DIR / "redis"

    # Data subdirectories
    SECURITY_DATA_DIR: Path = DATA_DIR / "security"
    CHECKPOINTS_DIR: Path = DATA_DIR / "checkpoints"

    # Security data paths
    SSO_PROVIDERS_DIR: Path = SECURITY_DATA_DIR / "sso_providers"
    SSO_KEYS_DIR: Path = SECURITY_DATA_DIR / "sso_keys"
    SECURITY_POLICIES_DIR: Path = SECURITY_DATA_DIR / "policies"
    USER_PROFILES_PATH: Path = SECURITY_DATA_DIR / "user_profiles.pkl"

    # Audit and compliance
    AUDIT_BASE_PATH: Path = LOGS_DIR / "audit"

    # User home directory (from environment)
    USER_HOME: Path = Path(os.path.expanduser("~"))

    @classmethod
    def get_config_path(cls, *parts: str) -> Path:
        """Get configuration file path"""
        return cls.CONFIG_DIR.joinpath(*parts)

    @classmethod
    def get_data_path(cls, *parts: str) -> Path:
        """Get data file path"""
        return cls.DATA_DIR.joinpath(*parts)

    @classmethod
    def get_log_path(cls, *parts: str) -> Path:
        """Get log file path"""
        return cls.LOGS_DIR.joinpath(*parts)

    @classmethod
    def ensure_directory(cls, path: Path) -> Path:
        """Ensure directory exists, create if needed"""
        path.mkdir(parents=True, exist_ok=True)
        return path


# Export constants instance
PATH = PathConstants()
