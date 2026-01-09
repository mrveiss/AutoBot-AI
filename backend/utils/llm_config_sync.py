#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Configuration Synchronization Utility

This module ensures that the global LLM configuration is synchronized with
the actual models being used by agents. It fixes the issue where:
- Settings > Backend > LLM shows "disconnected"
- Model dropdown is empty
- Agents show "connected" but global LLM config is not set

This runs as part of the system startup to ensure configuration consistency.
"""

import asyncio
import logging

from backend.type_defs.common import Metadata

# Import network constants

logger = logging.getLogger(__name__)


class LLMConfigurationSynchronizer:
    """Synchronizes LLM configuration across the system"""

    @staticmethod
    def _get_current_llm_model(config_manager) -> str:
        """Extract current selected model from config (Issue #315: extracted helper)."""
        current_llm_config = config_manager.get_llm_config()
        return (
            current_llm_config.get("unified", {})
            .get("local", {})
            .get("providers", {})
            .get("ollama", {})
            .get("selected_model", "")
        )

    @staticmethod
    def _collect_agent_models(config_manager, agent_configs) -> tuple:
        """Collect models from all agents and find common model (Issue #315: extracted helper).

        Returns:
            Tuple of (agent_models dict, common_model)
        """
        agent_models = {}
        common_model = None

        for agent_id, config in agent_configs.items():
            agent_model = config_manager.get_nested(
                f"agents.{agent_id}.model", config["default_model"]
            )
            agent_enabled = config_manager.get_nested(
                f"agents.{agent_id}.enabled", config["enabled"]
            )

            agent_models[agent_id] = {"model": agent_model, "enabled": agent_enabled}

            if agent_enabled and agent_model:
                if common_model is None:
                    common_model = agent_model
                elif common_model != agent_model:
                    logger.warning("Agent %s uses different model: %s", agent_id, agent_model)

        return agent_models, common_model

    @staticmethod
    def _check_sync_needed(current_model: str, common_model: str) -> tuple:
        """
        Check if LLM config sync is needed.

        Issue #665: Extracted from sync_llm_config_with_agents to reduce function length.

        Args:
            current_model: Currently configured global model
            common_model: Most common model used by agents

        Returns:
            Tuple of (sync_needed: bool, sync_reason: str)
        """
        if not current_model:
            return True, "No global LLM model configured"
        if common_model and current_model != common_model:
            return True, (
                f"Global model '{current_model}' differs from agent model '{common_model}'"
            )
        return False, ""

    @staticmethod
    def _perform_sync_update(
        config_manager, previous_model: str, target_model: str,
        sync_reason: str, agent_models: dict
    ) -> Metadata:
        """
        Perform the actual sync update and verification.

        Issue #665: Extracted from sync_llm_config_with_agents to reduce function length.

        Args:
            config_manager: Global config manager instance
            previous_model: Previously configured model
            target_model: Model to sync to
            sync_reason: Reason for sync
            agent_models: Dict of agent models

        Returns:
            Sync result dictionary
        """
        logger.info("SYNC NEEDED: %s", sync_reason)
        logger.info("Setting global LLM model to: %s", target_model)
        config_manager.update_llm_model(target_model)

        # Verify the change
        updated_model = LLMConfigurationSynchronizer._get_current_llm_model(config_manager)

        if updated_model == target_model:
            logger.info("✅ Successfully synchronized global LLM model to: %s", target_model)
            return {
                "status": "synchronized",
                "previous_model": previous_model,
                "new_model": target_model,
                "reason": sync_reason,
                "agent_models": agent_models,
            }

        logger.error(
            "❌ Failed to update global model. Expected: %s, Got: %s",
            target_model, updated_model
        )
        return {
            "status": "sync_failed",
            "error": "Model update verification failed",
            "expected": target_model,
            "actual": updated_model,
        }

    @staticmethod
    def sync_llm_config_with_agents() -> Metadata:
        """
        Synchronize global LLM configuration with agent configurations

        Returns:
            Dict containing the synchronization result
        """
        try:
            from backend.api.agent_config import DEFAULT_AGENT_CONFIGS
            from src.unified_config_manager import config as global_config_manager

            logger.info("Starting LLM configuration synchronization...")

            # Get current model using helper (Issue #315: reduced nesting)
            current_selected_model = LLMConfigurationSynchronizer._get_current_llm_model(
                global_config_manager
            )
            logger.info("Current global LLM model: '%s'", current_selected_model)

            # Collect agent models using helper
            agent_models, common_model = LLMConfigurationSynchronizer._collect_agent_models(
                global_config_manager, DEFAULT_AGENT_CONFIGS
            )
            logger.info("Agent models: %s", agent_models)
            logger.info("Most common agent model: %s", common_model)

            # Check if sync needed (Issue #665: extracted helper)
            sync_needed, sync_reason = LLMConfigurationSynchronizer._check_sync_needed(
                current_selected_model, common_model
            )

            # No sync needed
            if not (sync_needed and common_model):
                logger.info("✅ LLM configuration is already synchronized")
                return {
                    "status": "already_synchronized",
                    "current_model": current_selected_model,
                    "agent_models": agent_models,
                }

            # Perform sync and return result (Issue #665: extracted helper)
            return LLMConfigurationSynchronizer._perform_sync_update(
                global_config_manager, current_selected_model, common_model,
                sync_reason, agent_models
            )

        except Exception as e:
            logger.error("❌ Failed to synchronize LLM configuration: %s", e)
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def ensure_models_populated() -> Metadata:
        """
        Ensure that the available models list is populated in the configuration

        Returns:
            Dict containing the population result
        """
        try:
            from backend.utils.connection_utils import ModelManager
            from src.unified_config_manager import config as global_config_manager

            logger.info("Ensuring models list is populated...")

            # Get available models
            result = await ModelManager.get_available_models()
            if result["status"] == "error":
                logger.error("Failed to get available models: %s", result['error'])
                return {"status": "error", "error": result["error"]}

            models = result["models"]
            model_names = [
                model.get("name", "") if isinstance(model, dict) else str(model)
                for model in models
            ]

            logger.info("Found %s available models: %s", len(model_names), model_names)

            # Update the configuration with available models
            global_config_manager.set_nested(
                "backend.llm.local.providers.ollama.models", model_names
            )

            # Save the configuration
            global_config_manager.save_settings()

            logger.info("✅ Models list populated successfully")
            return {
                "status": "success",
                "models": model_names,
                "count": len(model_names),
            }

        except Exception as e:
            logger.error("❌ Failed to populate models list: %s", e)
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def full_synchronization() -> Metadata:
        """
        Perform a complete LLM configuration synchronization

        Returns:
            Dict containing the full synchronization result
        """
        logger.info("🔄 Starting full LLM configuration synchronization...")

        results = {
            "timestamp": None,
            "sync_result": None,
            "models_result": None,
            "overall_status": "unknown",
        }

        try:
            from datetime import datetime

            results["timestamp"] = datetime.now().isoformat()

            # Step 1: Synchronize agent configurations with global LLM config
            results["sync_result"] = await asyncio.to_thread(
                LLMConfigurationSynchronizer.sync_llm_config_with_agents
            )

            # Step 2: Populate available models list
            results["models_result"] = (
                await LLMConfigurationSynchronizer.ensure_models_populated()
            )

            # Determine overall status
            sync_ok = results["sync_result"]["status"] in [
                "synchronized",
                "already_synchronized",
            ]
            models_ok = results["models_result"]["status"] == "success"

            if sync_ok and models_ok:
                results["overall_status"] = "success"
                logger.info(
                    "✅ Full LLM configuration synchronization completed successfully"
                )
            elif sync_ok:
                results["overall_status"] = "partial"
                logger.warning("⚠️ LLM sync succeeded but model population failed")
            elif models_ok:
                results["overall_status"] = "partial"
                logger.warning("⚠️ Model population succeeded but LLM sync failed")
            else:
                results["overall_status"] = "failed"
                logger.error("❌ Full LLM configuration synchronization failed")

        except Exception as e:
            logger.error("❌ Full synchronization failed with exception: %s", e)
            results["overall_status"] = "error"
            results["error"] = str(e)

        return results


# Convenience function for easy import
async def sync_llm_configuration() -> Metadata:
    """Convenience function to perform full LLM configuration synchronization"""
    return await LLMConfigurationSynchronizer.full_synchronization()


# Additional convenience function for backward compatibility
async def sync_llm_config_async() -> Metadata:
    """Async function to synchronize LLM configuration with agents"""
    return await LLMConfigurationSynchronizer.full_synchronization()


if __name__ == "__main__":
    # Direct execution for testing/debugging
    async def main():
        """Test LLM configuration synchronization."""
        result = await sync_llm_configuration()
        logger.info("Synchronization result:")
        import json

        logger.info(json.dumps(result, indent=2))

    asyncio.run(main())
