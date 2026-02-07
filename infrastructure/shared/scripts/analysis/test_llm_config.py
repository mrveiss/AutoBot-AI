#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Check LLM configuration to see what models are being used
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import src.config as config
from src.llm_interface import LLMInterface


def check_llm_config():
    """Check LLM configuration"""
    print("🔧 Checking LLM Configuration...")

    try:
        # Get config
        global_config = config.config

        # Print relevant config sections
        print("\n📋 Global LLM Config:")
        llm_config = global_config.get_nested("llm_config", {})
        for key, value in llm_config.items():
            print(f"   {key}: {value}")

        # Check unified LLM config
        print("\n🔗 Unified LLM Config:")
        unified_config = global_config.get_nested("unified_llm_config", {})
        for key, value in unified_config.items():
            print(f"   {key}: {value}")

        # Create LLM interface and check its settings
        print("\n🤖 LLM Interface Settings:")
        llm = LLMInterface()

        print(f"   Orchestrator LLM alias: {llm.orchestrator_llm_alias}")
        print(f"   Task LLM alias: {llm.task_llm_alias}")
        print(f"   Ollama models: {llm.ollama_models}")
        print(f"   Ollama host: {llm.ollama_host}")

        # Check what model would be used for task LLM
        if llm.task_llm_alias.startswith("ollama_"):
            base_alias = llm.task_llm_alias.replace("ollama_", "")
            model_name = llm.ollama_models.get(base_alias, base_alias)
            print(f"   Task LLM resolved model: {model_name}")

        return True

    except Exception as e:
        print(f"❌ Config check failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    check_llm_config()
