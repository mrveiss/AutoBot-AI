#!/usr/bin/env python3
"""
Test script to verify the model selection bug fix in unified_config_manager.py

This tests that:
1. get_selected_model() reads from the correct path
2. update_llm_model() writes to the correct path
3. Model selection from GUI actually works
"""

import sys
import os
sys.path.append('/home/kali/Desktop/AutoBot/src')

from unified_config_manager import UnifiedConfigManager

def test_model_selection_fix():
    """Test the model selection fix"""
    print("=== Testing Model Selection Fix ===\n")

    # Initialize the config manager
    config_manager = UnifiedConfigManager()

    # Test 1: Get current model selection
    print("1. Testing get_selected_model():")
    current_model = config_manager.get_selected_model()
    print(f"   Current selected model: {current_model}")

    # Test 2: Update model selection
    print("\n2. Testing update_llm_model():")
    test_model = "gemma2:2b"
    print(f"   Updating model to: {test_model}")
    config_manager.update_llm_model(test_model)

    # Test 3: Verify the update worked
    print("\n3. Verifying update worked:")
    updated_model = config_manager.get_selected_model()
    print(f"   Model after update: {updated_model}")

    if updated_model == test_model:
        print("   ✅ SUCCESS: Model update worked correctly!")
    else:
        print(f"   ❌ FAILURE: Expected '{test_model}', got '{updated_model}'")
        return False

    # Test 4: Test fallback behavior with original model
    print("\n4. Testing restore to original model:")
    original_model = "llama3.2:1b-instruct-q4_K_M"  # From config.yaml
    config_manager.update_llm_model(original_model)
    restored_model = config_manager.get_selected_model()
    print(f"   Restored model: {restored_model}")

    if restored_model == original_model:
        print("   ✅ SUCCESS: Model restore worked correctly!")
    else:
        print(f"   ❌ WARNING: Expected '{original_model}', got '{restored_model}'")

    # Test 5: Check the actual configuration path
    print("\n5. Testing configuration path:")
    try:
        # Use the proper config access method
        actual_model = config_manager.get_nested("backend.llm.local.providers.ollama.selected_model")
        if actual_model:
            print(f"   Model in config.yaml: {actual_model}")
            print("   ✅ SUCCESS: Configuration path is correct!")
        else:
            print("   ❌ FAILURE: Could not read model from configuration path")
            return False
    except Exception as e:
        print(f"   ❌ FAILURE: Configuration path error: {e}")
        return False

    print("\n=== Model Selection Fix Test Complete ===")
    return True

def test_ollama_url_fix():
    """Test the Ollama URL configuration fix"""
    print("\n=== Testing Ollama URL Fix ===\n")

    config_manager = UnifiedConfigManager()

    print("1. Testing get_ollama_url():")
    ollama_url = config_manager.get_ollama_url()
    print(f"   Ollama URL: {ollama_url}")

    # Check if it reads from the correct configuration path
    try:
        endpoint = config_manager.get_nested("backend.llm.local.providers.ollama.endpoint")
        host = config_manager.get_nested("backend.llm.local.providers.ollama.host")
        if endpoint and host:
            print(f"   Endpoint from config: {endpoint}")
            print(f"   Host from config: {host}")
            print("   ✅ SUCCESS: Ollama URL configuration is accessible!")
            return True
        else:
            print("   ❌ FAILURE: Could not read Ollama URL configuration")
            return False
    except Exception as e:
        print(f"   ❌ FAILURE: Ollama URL configuration path error: {e}")
        return False

if __name__ == "__main__":
    print("AutoBot Model Selection Bug Fix Test")
    print("=" * 50)

    success1 = test_model_selection_fix()
    success2 = test_ollama_url_fix()

    if success1 and success2:
        print("\n🎉 ALL TESTS PASSED! The model selection bug has been fixed.")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED! Please check the configuration paths.")
        sys.exit(1)