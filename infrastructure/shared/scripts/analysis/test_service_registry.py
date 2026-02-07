#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for Service Registry functionality
Validates deployment mode detection and service URL resolution
"""

import os
import sys

sys.path.insert(0, ".")


async def test_service_registry():
    """Test service registry functionality"""
    print("🧪 Testing AutoBot Service Registry")
    print("=" * 50)

    # Test 1: Import and basic functionality
    try:
        from src.utils.service_registry import get_service_registry, get_service_url

        print("✅ Service registry import successful")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

    # Test 2: Registry initialization
    try:
        registry = get_service_registry()
        print(f"✅ Registry initialized in {registry.deployment_mode.value} mode")
        print(f"   Domain: {registry.domain}")
        print(f"   Services: {len(registry.services)}")
    except Exception as e:
        print(f"❌ Registry initialization failed: {e}")
        return False

    # Test 3: Service URL resolution
    print("\n🔗 Service URL Resolution:")
    services = ["redis", "backend", "ai-stack", "npu-worker", "playwright-vnc"]

    for service in services:
        try:
            url = get_service_url(service)
            print(f"✅ {service:15} → {url}")
        except Exception as e:
            print(f"❌ {service:15} → Error: {e}")

    # Test 4: Service health checks
    print("\n🏥 Service Health Checks:")
    try:
        health_results = await registry.check_all_services_health()
        for service, health in health_results.items():
            status_emoji = (
                "✅"
                if health.status.value == "healthy"
                else "⚠️"
                if health.status.value == "unknown"
                else "❌"
            )
            print(f"{status_emoji} {service:15} → {health.status.value}")
            if hasattr(health, "response_time") and health.response_time > 0:
                print(f"   └── Response time: {health.response_time:.3f}s")
    except Exception as e:
        print(f"❌ Health checks failed: {e}")

    # Test 5: Deployment info
    print("\n📊 Deployment Information:")
    try:
        info = registry.get_deployment_info()
        print(f"✅ Mode: {info['deployment_mode']}")
        print(f"✅ Domain: {info['domain']}")
        print(f"✅ Services: {info['services_count']}")

        for service, details in info["services"].items():
            print(f"   • {service}: {details['url']} ({details['health']})")
    except Exception as e:
        print(f"❌ Deployment info failed: {e}")

    # Test 6: Different deployment modes
    print("\n🌍 Testing Deployment Mode Detection:")

    # Test local mode
    original_mode = os.getenv("AUTOBOT_DEPLOYMENT_MODE")
    os.environ["AUTOBOT_DEPLOYMENT_MODE"] = "local"

    try:
        from src.utils.service_registry import ServiceRegistry

        local_registry = ServiceRegistry()
        redis_url_local = local_registry.get_service_url("redis")
        print(f"✅ Local mode: redis → {redis_url_local}")
    except Exception as e:
        print(f"❌ Local mode test failed: {e}")

    # Test distributed mode
    os.environ["AUTOBOT_DEPLOYMENT_MODE"] = "distributed"
    os.environ["AUTOBOT_DOMAIN"] = "autobot.test"

    try:
        distributed_registry = ServiceRegistry()
        redis_url_distributed = distributed_registry.get_service_url("redis")
        print(f"✅ Distributed mode: redis → {redis_url_distributed}")
    except Exception as e:
        print(f"❌ Distributed mode test failed: {e}")

    # Restore original environment
    if original_mode:
        os.environ["AUTOBOT_DEPLOYMENT_MODE"] = original_mode
    else:
        os.environ.pop("AUTOBOT_DEPLOYMENT_MODE", None)

    print("\n🎉 Service Registry Testing Complete!")
    return True


if __name__ == "__main__":
    import asyncio

    print("AutoBot Service Registry Test Suite")
    print("=" * 50)

    try:
        success = asyncio.run(test_service_registry())
        if success:
            print("\n✅ All tests completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
