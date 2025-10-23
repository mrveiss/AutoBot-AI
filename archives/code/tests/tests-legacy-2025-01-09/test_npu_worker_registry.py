"""
Basic validation tests for NPU Worker Registry API

These tests verify that the implementation is correctly structured
and basic functionality works as expected.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")

    try:
        from backend.models.npu_models import (
            NPUWorkerConfig,
            NPUWorkerStatus,
            NPUWorkerMetrics,
            NPUWorkerDetails,
            LoadBalancingConfig,
            WorkerTestResult,
            WorkerStatus,
            LoadBalancingStrategy
        )
        print("✅ All Pydantic models imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import models: {e}")
        return False

    try:
        from backend.services.npu_worker_manager import NPUWorkerManager, get_worker_manager
        print("✅ NPU Worker Manager imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import worker manager: {e}")
        return False

    try:
        from backend.services.load_balancer import NPULoadBalancer, get_load_balancer
        print("✅ Load Balancer imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import load balancer: {e}")
        return False

    try:
        from backend.api.npu_workers import router
        print("✅ NPU Workers API router imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import API router: {e}")
        return False

    return True


def test_pydantic_models():
    """Test that Pydantic models validate correctly"""
    print("\nTesting Pydantic models...")

    from backend.models.npu_models import (
        NPUWorkerConfig,
        NPUWorkerStatus,
        LoadBalancingConfig,
        WorkerStatus,
        LoadBalancingStrategy
    )

    try:
        # Test NPUWorkerConfig validation
        worker_config = NPUWorkerConfig(
            id="test-worker",
            name="Test Worker",
            url="http://172.16.168.22:8081",
            platform="linux",
            enabled=True,
            priority=5,
            weight=1,
            max_concurrent_tasks=4
        )
        print(f"✅ NPUWorkerConfig created: {worker_config.id}")

        # Test URL validation
        try:
            invalid_config = NPUWorkerConfig(
                id="invalid",
                name="Invalid Worker",
                url="invalid-url",  # Should fail validation
                platform="linux"
            )
            print("❌ URL validation failed to catch invalid URL")
            return False
        except ValueError:
            print("✅ URL validation correctly rejected invalid URL")

        # Test NPUWorkerStatus
        status = NPUWorkerStatus(
            id="test-worker",
            status=WorkerStatus.ONLINE,
            current_load=2,
            total_tasks_completed=100,
            total_tasks_failed=5,
            uptime_seconds=3600.5
        )
        print(f"✅ NPUWorkerStatus created: {status.status}")

        # Test LoadBalancingConfig
        lb_config = LoadBalancingConfig(
            strategy=LoadBalancingStrategy.LEAST_LOADED,
            health_check_interval=30,
            timeout_seconds=10
        )
        print(f"✅ LoadBalancingConfig created: {lb_config.strategy}")

        return True

    except Exception as e:
        print(f"❌ Pydantic model test failed: {e}")
        return False


def test_config_file():
    """Test that config file exists and is valid YAML"""
    print("\nTesting configuration file...")

    import yaml

    config_file = Path(__file__).parent.parent / "config" / "npu_workers.yaml"

    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return False

    print(f"✅ Config file exists: {config_file}")

    try:
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)

        # Validate structure
        if "workers" not in config_data:
            print("❌ Config missing 'workers' section")
            return False

        if "load_balancing" not in config_data:
            print("❌ Config missing 'load_balancing' section")
            return False

        print(f"✅ Config has {len(config_data.get('workers', []))} worker(s) defined")
        print(f"✅ Load balancing strategy: {config_data['load_balancing'].get('strategy')}")

        return True

    except Exception as e:
        print(f"❌ Failed to parse config file: {e}")
        return False


def test_api_router():
    """Test that API router is properly configured"""
    print("\nTesting API router...")

    from backend.api.npu_workers import router

    # Get all routes
    routes = [route.path for route in router.routes]

    expected_routes = [
        "/v1/npu/workers",
        "/v1/npu/workers/{worker_id}",
        "/v1/npu/workers/{worker_id}/test",
        "/v1/npu/workers/{worker_id}/metrics",
        "/v1/npu/load-balancing",
        "/v1/npu/status"
    ]

    print(f"✅ Router has {len(routes)} route(s)")

    for expected in expected_routes:
        if any(expected in route for route in routes):
            print(f"✅ Route exists: {expected}")
        else:
            print(f"❌ Missing route: {expected}")
            return False

    return True


def test_router_registration():
    """Test that router is registered in app_factory"""
    print("\nTesting router registration...")

    app_factory_file = Path(__file__).parent.parent / "backend" / "app_factory.py"

    with open(app_factory_file, 'r') as f:
        content = f.read()

    if "npu_workers_router" in content:
        print("✅ Router imported in app_factory.py")
    else:
        print("❌ Router not imported in app_factory.py")
        return False

    if "npu-workers" in content or "npu_workers" in content:
        print("✅ Router registered in optional_routers")
    else:
        print("❌ Router not registered in optional_routers")
        return False

    return True


def run_all_tests():
    """Run all validation tests"""
    print("=" * 60)
    print("NPU Worker Registry Implementation Validation")
    print("=" * 60)

    tests = [
        ("Import Test", test_imports),
        ("Pydantic Models", test_pydantic_models),
        ("Configuration File", test_config_file),
        ("API Router", test_api_router),
        ("Router Registration", test_router_registration)
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ {test_name} crashed: {e}")
            results[test_name] = False

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("=" * 60)
    print(f"Overall: {passed}/{total} tests passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
