# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""OrchestratorConfig — extracted from orchestrator.py (#5060)."""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class OrchestratorConfig:
    """Configuration for the Orchestrator."""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._load_config()

    def _load_config(self):
        llm_config = self.config_manager.get_llm_config()
        self.orchestrator_llm_model = llm_config.get(
            "orchestrator_llm",
            llm_config.get("ollama", {}).get("selected_model"),
        )
        default_model = llm_config.get("ollama", {}).get("selected_model")
        self.task_llm_model = llm_config.get("task_llm", f"ollama_{default_model}")
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False

        self.max_parallel_tasks = self.config_manager.get("orchestrator.max_parallel_tasks", 3)
        self.task_timeout = self.config_manager.get("orchestrator.task_timeout", 300)
        self.retry_attempts = self.config_manager.get("orchestrator.retry_attempts", 3)
        self.agent_timeout = self.config_manager.get("orchestrator.agent_timeout", 120)
        self.max_agents = self.config_manager.get("orchestrator.max_agents", 5)
        self.enable_caching = self.config_manager.get("orchestrator.enable_caching", True)
        self.enable_streaming = self.config_manager.get("orchestrator.enable_streaming", True)

        logger.info("Orchestrator configured with model: %s", self.orchestrator_llm_model)
