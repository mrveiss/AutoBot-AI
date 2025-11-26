#!/usr/bin/env python3
"""
Test service_monitor router import to identify issues
"""

import sys
import traceback

def test_service_monitor_import():
    """Test importing service_monitor router"""
    try:
        print("1. Testing basic import...")
        import backend.api.service_monitor
        print("✅ Basic import successful")

        print("2. Testing router attribute...")
        router = backend.api.service_monitor.router
        print(f"✅ Router object: {type(router)}")

        print("3. Testing router routes...")
        routes = [route.path for route in router.routes]
        print(f"✅ Routes found: {routes}")

        print("4. Testing problematic imports inside module...")
        # Try to trigger any problematic imports
        from src.constants import NetworkConstants, ServiceURLs
        print("✅ Constants import successful")

        print("5. Testing ServiceURLs usage...")
        print(f"✅ ServiceURLs.BACKEND_LOCAL: {ServiceURLs.BACKEND_LOCAL}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        print("Traceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_service_monitor_import()
    sys.exit(0 if success else 1)
