#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration validation for unified config manager.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ValidationMixin:
    """Mixin providing configuration validation"""

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get_nested(f"features.{feature}", False)

    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get_nested(
            "security",
            {"session": {"timeout_minutes": 30}, "encryption": {"enabled": False}},
        )

    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return status"""
        status = {
            "config_loaded": True,
            "llm_config": self.get_llm_config(),
            "redis_config": self.get_redis_config(),
            "issues": [],
        }

        # Validate LLM configuration
        llm_config = status["llm_config"]
        if not llm_config.get("ollama", {}).get("selected_model"):
            status["issues"].append("No selected_model specified in LLM config")

        # Validate Redis configuration
        redis_config = status["redis_config"]
        if redis_config.get("enabled", True) and not redis_config.get("host"):
            status["issues"].append("Redis enabled but no host specified")

        return status
