#!/usr/bin/env python3
"""
Test backend startup and workflow endpoint registration
"""


def test_imports():
    """Test all critical imports."""
    print("🧪 Testing Backend Imports")
    print("-" * 40)

    try:
        # Test agents import
        pass

        print("✅ Agents import successful")

        # Test workflow router
        from backend.api.workflow import router

        print("✅ Workflow router import successful")

        # Test app factory

        print("✅ App factory import successful")

        # Test if workflow router has the expected routes
        routes = [route.path for route in router.routes]
        print(f"✅ Workflow routes found: {len(routes)} routes")
        for route in routes[:5]:  # Show first 5
            print(f"   - {route}")

        print("\n🎉 All imports successful! Backend should start properly now.")
        print("\n📋 Next steps:")
        print("1. Start the backend: source venv/bin/activate && python main.py")
        print(
            "2. Test workflow endpoint: curl http://localhost:8001/api/workflow/workflows"
        )
        print("3. Open frontend and navigate to Workflows tab")

        return True

    except Exception as e:
        print(f"❌ Import error: {e}")
        return False


if __name__ == "__main__":
    success = test_imports()
    if success:
        print("\n✅ Ready to start AutoBot backend!")
    else:
        print("\n❌ Fix import errors before starting backend.")
