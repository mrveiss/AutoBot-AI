#!/usr/bin/env python3
"""
Test script to verify all backend routers can be imported successfully
This will help identify any remaining import errors.
"""

import sys
import traceback
from pathlib import Path

# Add AutoBot paths
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

def test_import(module_name, module_path):
    """Test importing a specific module and return result"""
    print(f"\n{'='*60}")
    print(f"Testing import: {module_name}")
    print(f"Path: {module_path}")
    print('-' * 60)

    try:
        # Import the module
        if module_name == "backend.api.monitoring":
            from backend.api.monitoring import router
            print("✅ SUCCESS: Monitoring router imported")
            return True
        elif module_name == "backend.api.analytics":
            from backend.api.analytics import router
            print("✅ SUCCESS: Analytics router imported")
            return True
        elif module_name == "backend.api.multimodal":
            from backend.api.multimodal import router
            print("✅ SUCCESS: Multimodal router imported")
            return True
        elif module_name == "backend.api.long_running_operations":
            from backend.api.long_running_operations import router
            print("✅ SUCCESS: Long running operations router imported")
            return True
        elif module_name == "src.utils.performance_monitor":
            from src.utils.performance_monitor import phase9_monitor
            print("✅ SUCCESS: Performance monitor imported")
            return True
        elif module_name == "src.enhanced_memory_manager_async":
            from src.enhanced_memory_manager_async import TaskPriority
            print("✅ SUCCESS: Enhanced memory manager with TaskPriority imported")
            return True
        elif module_name == "backend.utils.llm_config_sync":
            from backend.utils.llm_config_sync import sync_llm_config_async
            print("✅ SUCCESS: LLM config sync imported")
            return True
        else:
            print(f"❓ UNKNOWN: Module {module_name} not in test list")
            return True

    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False

def main():
    """Run all import tests"""
    print("Backend Router Import Testing")
    print("=" * 60)

    # Test modules that were mentioned in the original error report
    test_modules = [
        ("src.utils.performance_monitor", "/home/kali/Desktop/AutoBot/src/utils/performance_monitor.py"),
        ("src.enhanced_memory_manager_async", "/home/kali/Desktop/AutoBot/src/enhanced_memory_manager_async.py"),
        ("backend.utils.llm_config_sync", "/home/kali/Desktop/AutoBot/backend/utils/llm_config_sync.py"),
        ("backend.api.long_running_operations", "/home/kali/Desktop/AutoBot/backend/api/long_running_operations.py"),
        ("backend.api.monitoring", "/home/kali/Desktop/AutoBot/backend/api/monitoring.py"),
        ("backend.api.analytics", "/home/kali/Desktop/AutoBot/backend/api/analytics.py"),
        ("backend.api.multimodal", "/home/kali/Desktop/AutoBot/backend/api/multimodal.py"),
    ]

    results = []
    for module_name, module_path in test_modules:
        # Check if file exists
        if not Path(module_path).exists():
            print(f"\n❌ MISSING FILE: {module_path}")
            results.append(False)
            continue

        success = test_import(module_name, module_path)
        results.append(success)

    # Summary
    print(f"\n{'='*60}")
    print("IMPORT TEST SUMMARY")
    print('=' * 60)

    successful = sum(results)
    total = len(results)

    print(f"Successful imports: {successful}/{total}")

    if successful == total:
        print("🎉 ALL IMPORTS SUCCESSFUL!")
        return 0
    else:
        print(f"⚠️  {total - successful} imports failed")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)