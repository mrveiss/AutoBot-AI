#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
from tests.test_helpers import get_test_backend_url


async def test_config_service():
    """Test ConfigService directly"""
    print("Testing ConfigService.get_full_config()...")  # noqa: print

    start_time = time.time()
    try:
        config = ConfigService.get_full_config()
        end_time = time.time()

        print(f"✅ ConfigService.get_full_config() completed in {end_time - start_time:.2f} seconds")  # noqa: print
        print(f"Config keys: {list(config.keys())}")  # noqa: print
        return True
    except Exception as e:
        end_time = time.time()
        print(  # noqa: print
            f"❌ ConfigService.get_full_config() failed after {end_time - start_time:.2f} seconds: {e}"
        )
        import traceback

        traceback.print_exc()
        return False


async def test_global_config_manager():
    """Test global_config_manager directly"""
    print("Testing global_config_manager...")  # noqa: print

    start_time = time.time()
    try:
        # Test a simple get operation
        value = global_config_manager.get_nested("message_display.show_thoughts", True)
        end_time = time.time()

        print(f"✅ global_config_manager test completed in {end_time - start_time:.2f} seconds")  # noqa: print
        print(f"Retrieved value: {value}")  # noqa: print
        return True
    except Exception as e:
        end_time = time.time()
        print(f"❌ global_config_manager test failed after {end_time - start_time:.2f} seconds: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return False


async def test_api_endpoint():
    """Test the API endpoint directly"""
    print("Testing API endpoint with timeout...")  # noqa: print

    try:
        start_time = time.time()
        response = requests.get(get_test_backend_url() + "/api/settings/", timeout=10)
        end_time = time.time()

        if response.status_code == 200:
            print(f"✅ API endpoint responded in {end_time - start_time:.2f} seconds")  # noqa: print  # noqa: print
            data = response.json()
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")  # noqa: print
            return True
        else:
            print(f"❌ API endpoint returned status {response.status_code}")  # noqa: print  # noqa: print
            return False
    except requests.exceptions.Timeout:
        end_time = time.time()
        print(f"❌ API endpoint timed out after {end_time - start_time:.2f} seconds")  # noqa: print  # noqa: print
        return False
    except Exception as e:
        end_time = time.time()
        print(f"❌ API endpoint error after {end_time - start_time:.2f} seconds: {e}")  # noqa: print  # noqa: print
        return False


async def main() -> None:
    print("🔍 Debug Testing Settings Components")  # noqa: print
    print("=" * 50)  # noqa: print

    # Test components in order
    tests = [
        ("Global Config Manager", test_global_config_manager),
        ("Config Service", test_config_service),
        ("API Endpoint", test_api_endpoint),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n🧪 Testing: {test_name}")  # noqa: print
        print("-" * 30)  # noqa: print

        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")  # noqa: print
            results.append((test_name, False))

    print("\n📊 SUMMARY")  # noqa: print
    print("=" * 50)  # noqa: print

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")  # noqa: print

    # Determine root cause
    if not results[0][1]:  # global_config_manager failed
        print("\n🎯 ROOT CAUSE: global_config_manager is blocking")  # noqa: print
    elif not results[1][1]:  # ConfigService failed
        print("\n🎯 ROOT CAUSE: ConfigService is blocking")  # noqa: print
    elif not results[2][1]:  # API endpoint failed
        print("\n🎯 ROOT CAUSE: API endpoint/routing issue")  # noqa: print
    else:
        print("\n🎯 All components working - issue may be intermittent")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
