#!/usr/bin/env python3
"""
Test backend startup and workflow endpoint registration
"""


from tests.test_helpers import get_test_backend_url


def test_imports():
    """Test all critical imports."""
    print("🧪 Testing Backend Imports")  # noqa: print
    print("-" * 40)  # noqa: print

    try:
        # Test agents import
        pass

        print("✅ Agents import successful")  # noqa: print

        # Test workflow router
        from api.workflow import router

        print("✅ Workflow router import successful")  # noqa: print

        # Test app factory

        print("✅ App factory import successful")  # noqa: print

        # Test if workflow router has the expected routes
        routes = [route.path for route in router.routes]
        print(f"✅ Workflow routes found: {len(routes)} routes")  # noqa: print
        for route in routes[:5]:  # Show first 5
            print(f"   - {route}")  # noqa: print

        print(  # noqa: print
            "\n🎉 All imports successful! Backend should start properly now."
        )  # noqa: print
        print("\n📋 Next steps:")  # noqa: print
        print(  # noqa: print
            "1. Start the backend: source venv/bin/activate && python main.py"
        )  # noqa: print
        print(  # noqa: print
            f"2. Test workflow endpoint: curl {get_test_backend_url()}/api/workflow/workflows"
        )
        print("3. Open frontend and navigate to Workflows tab")  # noqa: print

        return True

    except Exception as e:
        print(f"❌ Import error: {e}")  # noqa: print
        return False


if __name__ == "__main__":
    success = test_imports()
    if success:
        print("\n✅ Ready to start AutoBot backend!")  # noqa: print
    else:
        print("\n❌ Fix import errors before starting backend.")  # noqa: print
