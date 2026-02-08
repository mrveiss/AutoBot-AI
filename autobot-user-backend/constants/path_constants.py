# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Path Constants for AutoBot
Single source of truth for all path configurations
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathConstants:
    """Centralized path constants - NO HARDCODED PATHS"""

    # Project root - dynamically determined
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent

    # Backend resources (#793)
    PROMPTS_DIR: Path = PROJECT_ROOT / "autobot-user-backend" / "resources" / "prompts"

    # Core directories (updated for #781 reorganization)
    CONFIG_DIR: Path = PROJECT_ROOT / "infrastructure" / "shared" / "config"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    DOCS_DIR: Path = PROJECT_ROOT / "docs"
    SRC_DIR: Path = PROJECT_ROOT / "autobot-user-backend"
    TESTS_DIR: Path = PROJECT_ROOT / "autobot-user-backend"
    BACKEND_DIR: Path = PROJECT_ROOT / "autobot-user-backend"
    DATABASE_DIR: Path = PROJECT_ROOT / "autobot-user-backend" / "database"
    FRONTEND_DIR: Path = PROJECT_ROOT / "autobot-user-frontend"
    SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"
    UTILITIES_DIR: Path = SCRIPTS_DIR / "utilities"
    ANALYSIS_DIR: Path = PROJECT_ROOT / "infrastructure" / "shared" / "analysis"
    REPORTS_DIR: Path = PROJECT_ROOT / "data" / "reports"
    REFACTORING_REPORTS_DIR: Path = REPORTS_DIR / "refactoring"
    MCP_TOOLS_DIR: Path = PROJECT_ROOT / "infrastructure" / "shared" / "mcp"
    TEMP_DIR: Path = PROJECT_ROOT / "temp"
    ARCHIVE_DIR: Path = PROJECT_ROOT / "docs" / "archives"
    ANSIBLE_DIR: Path = PROJECT_ROOT / "autobot-slm-backend" / "ansible"
    ANSIBLE_PLAYBOOKS_DIR: Path = ANSIBLE_DIR / "playbooks"

    # Configuration subdirectories
    SECURITY_CONFIG_DIR: Path = CONFIG_DIR / "security"
    REDIS_CONFIG_DIR: Path = CONFIG_DIR / "redis"
    ENV_FILE: Path = PROJECT_ROOT / ".env"

    # Data subdirectories
    SECURITY_DATA_DIR: Path = DATA_DIR / "security"
    CHECKPOINTS_DIR: Path = DATA_DIR / "checkpoints"
    CONVERSATIONS_DIR: Path = DATA_DIR / "conversations"
    CHAT_HISTORY_DIR: Path = DATA_DIR / "chat_history"
    SYSTEM_KNOWLEDGE_DIR: Path = DATA_DIR / "system_knowledge"

    # Security data paths
    SSO_PROVIDERS_DIR: Path = SECURITY_DATA_DIR / "sso_providers"
    SSO_KEYS_DIR: Path = SECURITY_DATA_DIR / "sso_keys"
    SECURITY_POLICIES_DIR: Path = SECURITY_DATA_DIR / "policies"
    USER_PROFILES_PATH: Path = SECURITY_DATA_DIR / "user_profiles.pkl"

    # Audit and compliance
    AUDIT_BASE_PATH: Path = LOGS_DIR / "audit"

    # Specific log file paths
    BACKEND_LOG: Path = LOGS_DIR / "backend.log"
    FRONTEND_LOG: Path = LOGS_DIR / "frontend.log"
    REDIS_LOG: Path = LOGS_DIR / "redis.log"
    CHAT_LOG: Path = LOGS_DIR / "chat.log"

    # User home directory (from environment)
    USER_HOME: Path = Path.home()

    # SSH keys for VM access
    SSH_DIR: Path = USER_HOME / ".ssh"
    SSH_AUTOBOT_KEY: Path = SSH_DIR / "autobot_key"

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
