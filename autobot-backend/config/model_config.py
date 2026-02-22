#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM and model configuration management.
"""

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ModelConfigMixin:
    """Mixin providing LLM and model configuration management"""

    def get_selected_model(self) -> str:
        """Get the currently selected model from config.yaml (CRITICAL FIX)"""
        # This is the key method that was broken in the original global_config_manager
        # It must read from config.yaml, NOT return hardcoded values

        selected_model = self.get_nested(
            "backend.llm.local.providers.ollama.selected_model"
        )

        if selected_model:
            logger.info(
                "UNIFIED CONFIG: Selected model from config.yaml: %s", selected_model
            )
            return selected_model

        # Only fall back to environment if config.yaml doesn't have the value
        env_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL")
        if env_model:
            logger.info(
                "UNIFIED CONFIG: Selected model from environment: %s", env_model
            )
            return env_model

        # Final fallback - use centralized constant (lazy import to avoid circular dep)
        from constants.model_constants import ModelConstants

        fallback_model = ModelConstants.DEFAULT_OLLAMA_MODEL
        logger.warning(
            "UNIFIED CONFIG: No model configured, using fallback: %s", fallback_model
        )
        return fallback_model

    def update_llm_model(self, model_name: str) -> None:
        """Update the selected LLM model in config.yaml (GUI integration)"""
        logger.info("UNIFIED CONFIG: Updating selected model to '%s'", model_name)

        # Update the configuration in memory
        self.set_nested("backend.llm.local.providers.ollama.selected_model", model_name)

        # Save both settings.json and config.yaml
        self.save_settings()
        self.save_config_to_yaml()

        logger.info("Model updated to '%s' in unified configuration", model_name)

    def _create_default_llm_structure(self) -> Dict[str, Any]:
        """
        Create default LLM configuration structure.

        Returns default backend.llm configuration with Ollama provider settings.
        Issue #620.
        """
        # Lazy import to avoid circular dependency
        from constants.network_constants import NetworkConstants

        return {
            "provider_type": "local",
            "local": {
                "provider": "ollama",
                "providers": {
                    "ollama": {
                        "selected_model": self.get_selected_model(),
                        "models": [],
                        "endpoint": (
                            f"http://{NetworkConstants.LOCALHOST_NAME}"
                            f":{NetworkConstants.OLLAMA_PORT}/api/generate"
                        ),
                        "host": (
                            f"http://{NetworkConstants.LOCALHOST_NAME}"
                            f":{NetworkConstants.OLLAMA_PORT}"
                        ),
                    }
                },
            },
        }

    def get_ollama_endpoint_for_model(self, model_name: str) -> str:
        """Get Ollama endpoint routed by model name (#1070).

        Checks backend.llm.ollama.gpu_endpoint and gpu_models in
        config.yaml. Falls back to the default endpoint when GPU
        routing is not configured or the model is not in gpu_models.

        Args:
            model_name: Ollama model name (e.g. 'mistral:7b-instruct')

        Returns:
            Ollama base URL (no /api/generate suffix)
        """
        ollama_cfg = self.get_nested("backend.llm.ollama", {})
        gpu_endpoint = ollama_cfg.get("gpu_endpoint", "")
        gpu_models = ollama_cfg.get("gpu_models", [])
        if gpu_endpoint and gpu_models:
            gpu_set = {m.strip().lower() for m in gpu_models}
            if model_name.strip().lower() in gpu_set:
                return gpu_endpoint
        # Fall back to default endpoint
        return self._resolve_default_ollama_endpoint()

    def _resolve_default_ollama_endpoint(self) -> str:
        """Get the default (CPU) Ollama endpoint URL."""
        endpoint = self.get_nested("backend.llm.ollama.endpoint")
        if endpoint:
            return endpoint
        ollama_host = self.get_host("ollama")
        ollama_port = self.get_port("ollama")
        return f"http://{ollama_host}:{ollama_port}"

    def _resolve_ollama_endpoint(self, backend_llm: Dict[str, Any]) -> str:
        """
        Resolve Ollama endpoint from config or infrastructure settings.

        Args:
            backend_llm: Backend LLM configuration dictionary.

        Returns:
            Ollama endpoint URL string.
        Issue #620.
        """
        ollama_endpoint = (
            backend_llm.get("local", {})
            .get("providers", {})
            .get("ollama", {})
            .get("endpoint")
        )

        # If not explicitly configured, construct from infrastructure config
        if not ollama_endpoint:
            ollama_host = self.get_host("ollama")
            ollama_port = self.get_port("ollama")
            ollama_endpoint = f"http://{ollama_host}:{ollama_port}"

        return ollama_endpoint

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration with correct model reading"""
        # Get the full backend.llm configuration
        backend_llm = self.get_nested("backend.llm", {})

        # Ensure we have proper structure
        if not backend_llm:
            backend_llm = self._create_default_llm_structure()
            self.set_nested("backend.llm", backend_llm)

        # CRITICAL: Always use the selected model from config, not hardcoded values
        selected_model = self.get_selected_model()
        if backend_llm.get("local", {}).get("providers", {}).get("ollama"):
            backend_llm["local"]["providers"]["ollama"][
                "selected_model"
            ] = selected_model

        # Build Ollama endpoint from config instead of hardcoded IP
        ollama_endpoint = self._resolve_ollama_endpoint(backend_llm)

        # Return legacy-compatible format for existing code
        return {
            "ollama": {
                "selected_model": selected_model,
                "models": (
                    backend_llm.get("local", {})
                    .get("providers", {})
                    .get("ollama", {})
                    .get("models", [])
                ),
                "endpoint": ollama_endpoint,
            },
            "unified": backend_llm,  # New unified format
        }
