#!/usr/bin/env python3
"""
Debug script to test settings endpoint directly
"""

import asyncio
import os
import sys
import time

import requests

# Add the project root to Python path
sys.path.insert(0, os.getcwd())

from config import global_config_manager
from services.config_service import ConfigService


async def test_config_service():
    """Test ConfigService directly"""
    print("Testing ConfigService.get_full_config()...")

    start_time = time.time()
    try:
        config = ConfigService.get_full_config()
        end_time = time.time()

        print(
            f"✅ ConfigService.get_full_config() completed in {end_time - start_time:.2f} seconds"
        )
        print(f"Config keys: {list(config.keys())}")
        return True
    except Exception as e:
        end_time = time.time()
        print(
            f"❌ ConfigService.get_full_config() failed after {end_time - start_time:.2f} seconds: {e}"
        )
        import traceback

        traceback.print_exc()
        return False


async def test_global_config_manager():
    """Test global_config_manager directly"""
    print("Testing global_config_manager...")

    start_time = time.time()
    try:
        # Test a simple get operation
        value = global_config_manager.get_nested("message_display.show_thoughts", True)
        end_time = time.time()

        print(
            f"✅ global_config_manager test completed in {end_time - start_time:.2f} seconds"
        )
        print(f"Retrieved value: {value}")
        return True
    except Exception as e:
        end_time = time.time()
        print(
            f"❌ global_config_manager test failed after {end_time - start_time:.2f} seconds: {e}"
        )
        import traceback

        traceback.print_exc()
        return False


async def test_api_endpoint():
    """Test the API endpoint directly"""
    print("Testing API endpoint with timeout...")

    try:
        start_time = time.time()
        response = requests.get("http://localhost:8001/api/settings/", timeout=10)
        end_time = time.time()

        if response.status_code == 200:
            print(f"✅ API endpoint responded in {end_time - start_time:.2f} seconds")
            data = response.json()
            print(
                f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
            )
            return True
        else:
            print(f"❌ API endpoint returned status {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        end_time = time.time()
        print(f"❌ API endpoint timed out after {end_time - start_time:.2f} seconds")
        return False
    except Exception as e:
        end_time = time.time()
        print(f"❌ API endpoint error after {end_time - start_time:.2f} seconds: {e}")
        return False


async def main():
    print("🔍 Debug Testing Settings Components")
    print("=" * 50)

    # Test components in order
    tests = [
        ("Global Config Manager", test_global_config_manager),
        ("Config Service", test_config_service),
        ("API Endpoint", test_api_endpoint),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n🧪 Testing: {test_name}")
        print("-" * 30)

        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))

    print("\n📊 SUMMARY")
    print("=" * 50)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    # Determine root cause
    if not results[0][1]:  # global_config_manager failed
        print("\n🎯 ROOT CAUSE: global_config_manager is blocking")
    elif not results[1][1]:  # ConfigService failed
        print("\n🎯 ROOT CAUSE: ConfigService is blocking")
    elif not results[2][1]:  # API endpoint failed
        print("\n🎯 ROOT CAUSE: API endpoint/routing issue")
    else:
        print("\n🎯 All components working - issue may be intermittent")


if __name__ == "__main__":
    asyncio.run(main())
