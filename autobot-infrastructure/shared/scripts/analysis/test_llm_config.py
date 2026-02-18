#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Check LLM configuration to see what models are being used
"""

import logging
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import config as config
from llm_interface import LLMInterface


def check_llm_config():
    """Check LLM configuration"""
    logger.info("🔧 Checking LLM Configuration...")

    try:
        # Get config
        global_config = config.config

        # Print relevant config sections
        logger.info("\n📋 Global LLM Config:")
        llm_config = global_config.get_nested("llm_config", {})
        for key, value in llm_config.items():
            logger.info("   {key}: %s", value)

        # Check unified LLM config
        logger.info("\n🔗 Unified LLM Config:")
        unified_config = global_config.get_nested("unified_llm_config", {})
        for key, value in unified_config.items():
            logger.info("   {key}: %s", value)

        # Create LLM interface and check its settings
        logger.info("\n🤖 LLM Interface Settings:")
        llm = LLMInterface()

        logger.info("   Orchestrator LLM alias: %s", llm.orchestrator_llm_alias)
        logger.info("   Task LLM alias: %s", llm.task_llm_alias)
        logger.info("   Ollama models: %s", llm.ollama_models)
        logger.info("   Ollama host: %s", llm.ollama_host)

        # Check what model would be used for task LLM
        if llm.task_llm_alias.startswith("ollama_"):
            base_alias = llm.task_llm_alias.replace("ollama_", "")
            model_name = llm.ollama_models.get(base_alias, base_alias)
            logger.info("   Task LLM resolved model: %s", model_name)

        return True

    except Exception as e:
        logger.error("❌ Config check failed: %s", e)
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check_llm_config()
