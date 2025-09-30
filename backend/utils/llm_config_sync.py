#!/usr/bin/env python3
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
from typing import Dict, Any, Optional

# Import network constants
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class LLMConfigurationSynchronizer:
    """Synchronizes LLM configuration across the system"""

    @staticmethod
    def sync_llm_config_with_agents() -> Dict[str, Any]:
        """
        Synchronize global LLM configuration with agent configurations
        
        Returns:
            Dict containing the synchronization result
        """
        try:
            from src.unified_config_manager import config as global_config_manager
            from backend.api.agent_config import DEFAULT_AGENT_CONFIGS
            
            logger.info("Starting LLM configuration synchronization...")
            
            # Get current LLM configuration
            current_llm_config = global_config_manager.get_llm_config()
            current_selected_model = (
                current_llm_config.get("unified", {})
                .get("local", {})
                .get("providers", {})
                .get("ollama", {})
                .get("selected_model", "")
            )
            
            logger.info(f"Raw LLM config structure: {current_llm_config}")
            logger.info(f"Checking path: local.providers.ollama.selected_model")
            
            logger.info(f"Current global LLM model: '{current_selected_model}'")
            
            # Check what models agents are using
            agent_models = {}
            common_model = None
            
            for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
                agent_model = global_config_manager.get_nested(
                    f"agents.{agent_id}.model", config["default_model"]
                )
                agent_enabled = global_config_manager.get_nested(
                    f"agents.{agent_id}.enabled", config["enabled"]
                )
                
                agent_models[agent_id] = {
                    "model": agent_model,
                    "enabled": agent_enabled
                }
                
                # Track the most common model among enabled agents
                if agent_enabled and agent_model:
                    if common_model is None:
                        common_model = agent_model
                    elif common_model != agent_model:
                        logger.warning(f"Agent {agent_id} uses different model: {agent_model}")
            
            logger.info(f"Agent models: {agent_models}")
            logger.info(f"Most common agent model: {common_model}")
            
            # Determine if sync is needed
            sync_needed = False
            sync_reason = ""
            
            if not current_selected_model:
                sync_needed = True
                sync_reason = "No global LLM model configured"
            elif common_model and current_selected_model != common_model:
                sync_needed = True
                sync_reason = f"Global model '{current_selected_model}' differs from agent model '{common_model}'"
            
            # Perform synchronization if needed
            if sync_needed and common_model:
                logger.info(f"SYNC NEEDED: {sync_reason}")
                logger.info(f"Setting global LLM model to: {common_model}")
                
                # Update the global configuration
                global_config_manager.update_llm_model(common_model)
                
                # Verify the change
                updated_config = global_config_manager.get_llm_config()
                updated_model = (
                    updated_config.get("unified", {})
                    .get("local", {})
                    .get("providers", {})
                    .get("ollama", {})
                    .get("selected_model", "")
                )
                
                logger.info(f"Updated config structure: {updated_config}")
                logger.info(f"Verification path result: '{updated_model}'")
                
                if updated_model == common_model:
                    logger.info(f"✅ Successfully synchronized global LLM model to: {common_model}")
                    return {
                        "status": "synchronized",
                        "previous_model": current_selected_model,
                        "new_model": common_model,
                        "reason": sync_reason,
                        "agent_models": agent_models
                    }
                else:
                    logger.error(f"❌ Failed to update global model. Expected: {common_model}, Got: {updated_model}")
                    return {
                        "status": "sync_failed",
                        "error": "Model update verification failed",
                        "expected": common_model,
                        "actual": updated_model
                    }
                    
            else:
                logger.info("✅ LLM configuration is already synchronized")
                return {
                    "status": "already_synchronized",
                    "current_model": current_selected_model,
                    "agent_models": agent_models
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to synchronize LLM configuration: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    @staticmethod
    async def ensure_models_populated() -> Dict[str, Any]:
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
                logger.error(f"Failed to get available models: {result['error']}")
                return {
                    "status": "error",
                    "error": result["error"]
                }
            
            models = result["models"]
            model_names = [
                model.get("name", "") if isinstance(model, dict) else str(model)
                for model in models
            ]
            
            logger.info(f"Found {len(model_names)} available models: {model_names}")
            
            # Update the configuration with available models
            global_config_manager.set_nested(
                "backend.llm.local.providers.ollama.models", 
                model_names
            )
            
            # Save the configuration
            global_config_manager.save_settings()
            
            logger.info("✅ Models list populated successfully")
            return {
                "status": "success",
                "models": model_names,
                "count": len(model_names)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to populate models list: {e}")
            return {
                "status": "error", 
                "error": str(e)
            }

    @staticmethod
    async def full_synchronization() -> Dict[str, Any]:
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
            "overall_status": "unknown"
        }
        
        try:
            from datetime import datetime
            results["timestamp"] = datetime.now().isoformat()
            
            # Step 1: Synchronize agent configurations with global LLM config
            results["sync_result"] = await asyncio.to_thread(
                LLMConfigurationSynchronizer.sync_llm_config_with_agents
            )
            
            # Step 2: Populate available models list  
            results["models_result"] = await LLMConfigurationSynchronizer.ensure_models_populated()
            
            # Determine overall status
            sync_ok = results["sync_result"]["status"] in ["synchronized", "already_synchronized"]
            models_ok = results["models_result"]["status"] == "success"
            
            if sync_ok and models_ok:
                results["overall_status"] = "success"
                logger.info("✅ Full LLM configuration synchronization completed successfully")
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
            logger.error(f"❌ Full synchronization failed with exception: {e}")
            results["overall_status"] = "error"
            results["error"] = str(e)
        
        return results


# Convenience function for easy import
async def sync_llm_configuration() -> Dict[str, Any]:
    """Convenience function to perform full LLM configuration synchronization"""
    return await LLMConfigurationSynchronizer.full_synchronization()


# Additional convenience function for backward compatibility
async def sync_llm_config_async() -> Dict[str, Any]:
    """Async function to synchronize LLM configuration with agents"""
    return await LLMConfigurationSynchronizer.full_synchronization()


if __name__ == "__main__":
    # Direct execution for testing/debugging
    import asyncio
    
    async def main():
        result = await sync_llm_configuration()
        print("Synchronization result:")
        import json
        print(json.dumps(result, indent=2))
    
    asyncio.run(main())