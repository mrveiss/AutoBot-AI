# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Skill Framework (Issue #731)

Provides abstract base class and data models for the Skills system.
Skills are self-contained AI capability modules with manifest-driven
configuration, dependency tracking, and lifecycle management.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    """Lifecycle status of a skill."""

    AVAILABLE = "available"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    LOADING = "loading"
    MISSING_DEPS = "missing_deps"


class SkillConfigField(BaseModel):
    """Schema for a single configuration field in a skill manifest."""

    type: str = Field(..., description="Field type: string, int, float, bool, list")
    default: Any = Field(None, description="Default value")
    description: str = Field("", description="Human-readable description")
    required: bool = Field(False, description="Whether this field is required")
    choices: Optional[List[str]] = Field(None, description="Allowed values")


class SkillManifest(BaseModel):
    """Manifest describing a skill package.

    Follows the structure defined in issue #731:
    name, version, description, author, dependencies, config, tools, triggers.
    """

    name: str = Field(..., description="Unique skill identifier (kebab-case)")
    version: str = Field("1.0.0", description="Semantic version")
    description: str = Field(..., description="Human-readable description")
    author: str = Field("mrveiss", description="Skill author")
    category: str = Field("general", description="Skill category for grouping")
    dependencies: List[str] = Field(
        default_factory=list, description="Names of required skills"
    )
    config: Dict[str, SkillConfigField] = Field(
        default_factory=dict, description="Configuration schema"
    )
    tools: List[str] = Field(
        default_factory=list, description="Tool names this skill provides"
    )
    triggers: List[str] = Field(
        default_factory=list, description="Events this skill responds to"
    )
    tags: List[str] = Field(default_factory=list, description="Searchable tags")


class SkillHealth(BaseModel):
    """Health/status response for a skill instance."""

    name: str
    status: SkillStatus
    version: str = ""
    message: Optional[str] = None
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    config_valid: bool = True
    dependencies_met: bool = True
    details: Dict[str, Any] = Field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract base for all skill implementations.

    Subclasses must implement:
    - get_manifest() - return the skill's manifest
    - execute() - run the skill's primary action
    - validate_config() - check if current config is valid
    """

    def __init__(self) -> None:
        self._status = SkillStatus.AVAILABLE
        self._config: Dict[str, Any] = {}
        self._enabled = False
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @staticmethod
    @abstractmethod
    def get_manifest() -> SkillManifest:
        """Return the skill's manifest with metadata and config schema."""
        ...

    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named action with given parameters.

        Args:
            action: The tool/action name to execute.
            params: Parameters for the action.

        Returns:
            Result dictionary with at minimum a 'success' key.
        """
        ...

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration against the manifest schema.

        Returns list of validation error messages (empty if valid).
        """
        errors = []
        manifest = self.get_manifest()
        for field_name, field_schema in manifest.config.items():
            if field_schema.required and field_name not in config:
                errors.append(f"Missing required field: {field_name}")
                continue
            value = config.get(field_name)
            if value is not None and field_schema.choices:
                if value not in field_schema.choices:
                    errors.append(
                        f"{field_name}: '{value}' not in {field_schema.choices}"
                    )
        return errors

    @property
    def status(self) -> SkillStatus:
        """Current skill status."""
        return self._status

    @property
    def enabled(self) -> bool:
        """Whether this skill is currently enabled."""
        return self._enabled

    @property
    def config(self) -> Dict[str, Any]:
        """Current configuration values."""
        return self._config.copy()

    def apply_config(self, config: Dict[str, Any]) -> None:
        """Apply configuration values, filling defaults from manifest."""
        manifest = self.get_manifest()
        merged = {}
        for field_name, field_schema in manifest.config.items():
            if field_name in config:
                merged[field_name] = config[field_name]
            elif field_schema.default is not None:
                merged[field_name] = field_schema.default
        self._config = merged

    def enable(self) -> None:
        """Enable the skill."""
        self._enabled = True
        self._status = SkillStatus.ENABLED
        self.logger.info("Skill enabled: %s", self.get_manifest().name)

    def disable(self) -> None:
        """Disable the skill."""
        self._enabled = False
        self._status = SkillStatus.DISABLED
        self.logger.info("Skill disabled: %s", self.get_manifest().name)

    def get_health(self) -> SkillHealth:
        """Return current health status."""
        manifest = self.get_manifest()
        config_errors = self.validate_config(self._config)
        return SkillHealth(
            name=manifest.name,
            status=self._status,
            version=manifest.version,
            config_valid=len(config_errors) == 0,
            dependencies_met=(self._status != SkillStatus.MISSING_DEPS),
            details={
                "config_errors": config_errors,
                "tools": manifest.tools,
                "triggers": manifest.triggers,
            },
        )

    def get_available_actions(self) -> List[str]:
        """Return list of tool names this skill provides."""
        return self.get_manifest().tools
