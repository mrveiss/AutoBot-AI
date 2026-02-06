#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test real AutoBot startup time without importing heavy libraries
"""
import os
import sys
import time


def test_backend_import():
    """Test just importing backend without creating app"""
    print("🔍 Testing AutoBot Backend Import Speed")
    print("=" * 50)

    start_time = time.time()

    # Add project root to path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("📦 Importing backend.main (with lazy loading)...")
    import_start = time.time()
    from backend import main

    import_duration = time.time() - import_start

    print(f"✅ backend.main imported in: {import_duration:.3f}s")

    # Test that the app isn't created yet
    print(f"📋 App type: {type(main.app)}")
    print(f"📋 App class: {main.app.__class__.__name__}")

    # Now test app creation (this should be the heavy part)
    print("\n🚀 Creating FastAPI app...")
    app_start = time.time()
    actual_app = main.app._ensure_app()  # Force app creation
    app_duration = time.time() - app_start

    print(f"✅ FastAPI app created in: {app_duration:.3f}s")
    print(f"📋 Actual app type: {type(actual_app)}")

    total_time = time.time() - start_time
    print("\n🎯 SUMMARY:")
    print(
        f"Import time       : {import_duration:6.3f}s ({import_duration/total_time*100:4.1f}%)"
    )
    print(
        f"App creation time : {app_duration:6.3f}s ({app_duration/total_time*100:4.1f}%)"
    )
    print(f"Total time        : {total_time:6.3f}s")

    return import_duration, app_duration


def test_uvicorn_startup():
    """Test uvicorn startup simulation"""
    print("\n\n🚀 Testing Uvicorn-style Startup")
    print("=" * 50)

    # Simulate what uvicorn does - it imports the module and accesses app attributes
    start_time = time.time()

    # This is what uvicorn roughly does:
    # 1. Import the module
    from backend import main

    import_time = time.time() - start_time

    # 2. Access app attributes (this should trigger lazy creation)
    access_start = time.time()
    app_type = type(main.app)  # This might trigger app creation
    routes = (
        len(main.app.routes) if hasattr(main.app, "routes") else 0
    )  # This definitely will
    access_time = time.time() - access_start

    total_time = time.time() - start_time

    print(f"✅ Module import      : {import_time:6.3f}s")
    print(f"✅ App access/creation: {access_time:6.3f}s")
    print(f"📋 App has {routes} routes")
    print(f"🎯 Total uvicorn-style: {total_time:6.3f}s")

    return total_time


if __name__ == "__main__":
    import_dur, app_dur = test_backend_import()
    uvicorn_total = test_uvicorn_startup()

    print("\n🏆 PERFORMANCE ANALYSIS:")
    print(f"Just importing backend: {import_dur:6.3f}s")
    print(f"Full app creation:      {app_dur:6.3f}s")
    print(f"Uvicorn simulation:     {uvicorn_total:6.3f}s")

    if import_dur < 1.0:
        print("✅ Import speed is GOOD (< 1s)")
    elif import_dur < 5.0:
        print("⚠️  Import speed is OK (1-5s)")
    else:
        print("❌ Import speed is SLOW (> 5s)")

    if app_dur < 10.0:
        print("✅ App creation speed is GOOD (< 10s)")
    elif app_dur < 30.0:
        print("⚠️  App creation speed is OK (10-30s)")
    else:
        print("❌ App creation speed is SLOW (> 30s)")
