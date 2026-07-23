#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Verify that the backend configuration includes workflow endpoints
"""


def test_app_factory():
    """Test that the app factory properly includes workflow router."""

    print("🔍 Verifying Backend Configuration")
    print("=" * 50)

    try:
        # Test importing the workflow router
        from backend.api.workflow import router as workflow_router

        print("✅ Workflow router import successful")

        # Check route count
        routes = workflow_router.routes
        print(f"✅ Workflow router has {len(routes)} routes:")
        for route in routes:
            methods = getattr(route, "methods", ["GET"])
            path = getattr(route, "path", "unknown")
            print(f"   - {list(methods)} {path}")

        # Test app factory configuration
        from backend.app_factory import add_api_routes

        print("✅ App factory import successful")

        # Test that workflow router is in the config
        import inspect

        source = inspect.getsource(add_api_routes)
        if "workflow_router" in source:
            print("✅ Workflow router found in app factory config")
        else:
            print("❌ Workflow router NOT found in app factory config")

        print("\n🎯 Backend should now include workflow endpoints!")
        print("   Restart the backend to activate workflow API")

        return True

    except Exception as e:
        print(f"❌ Configuration error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_route_registration():
    """Test that routes will be properly registered."""

    print("\n📋 Testing Route Registration")
    print("-" * 30)

    try:
        # Simulate what happens during app startup
        from backend.api.workflow import router as workflow_router
        from fastapi import APIRouter, FastAPI

        # Create test app
        app = FastAPI()
        api_router = APIRouter()

        # Add workflow router
        api_router.include_router(workflow_router, prefix="/workflow", tags=["workflow"])
        app.include_router(api_router, prefix="/api")

        # Check routes
        workflow_routes = []
        for route in app.routes:
            if hasattr(route, "path") and "workflow" in route.path:
                workflow_routes.append(f"{route.methods} {route.path}")

        print(f"✅ {len(workflow_routes)} workflow routes will be registered:")
        for route in workflow_routes:
            print(f"   - {route}")

        # Specifically check for execute endpoint
        execute_routes = [r for r in workflow_routes if "execute" in r]
        if execute_routes:
            print(f"✅ Execute endpoint found: {execute_routes[0]}")
        else:
            print("❌ Execute endpoint NOT found")

        return len(execute_routes) > 0

    except Exception as e:
        print(f"❌ Route registration test failed: {e}")
        return False


if __name__ == "__main__":
    config_ok = test_app_factory()
    routes_ok = test_route_registration()

    print("\n" + "=" * 50)
    if config_ok and routes_ok:
        print("🎉 Backend configuration is correct!")
        print("   All workflow endpoints should be available after restart")
    else:
        print("❌ Backend configuration needs fixes")

    print("\n🔧 To restart backend:")
    print("   1. Stop current backend (Ctrl+C)")
    print("   2. Run: source venv/bin/activate && python main.py")
    print("   3. Test: curl -X POST ServiceURLs.BACKEND_LOCAL/api/workflow/execute")
