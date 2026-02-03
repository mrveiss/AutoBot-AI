#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Verify service authentication is ready for deployment."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.redis_client import get_redis_client as get_redis_manager
from backend.security.service_auth import ServiceAuthManager

# All 6 services that should have keys
SERVICES = [
    'main-backend',
    'frontend',
    'npu-worker',
    'redis-stack',
    'ai-stack',
    'browser-service'
]


async def verify():
    """Verify service authentication infrastructure."""
    print("🔐 Service Authentication Verification")
    print("=" * 50)
    print("")

    try:
        # Get Redis connection
        redis_mgr = await get_redis_manager()
        redis = await redis_mgr.main()
        auth_mgr = ServiceAuthManager(redis)

        print("✅ ServiceAuthManager initialized successfully")
        print("")

        # Verify all service keys
        print("Checking service keys:")
        print("-" * 50)
        all_present = True
        for service_id in SERVICES:
            key = await auth_mgr.get_service_key(service_id)
            status = "✅" if key else "❌"
            key_preview = f"{key[:16]}..." if key else "MISSING"
            print(f"{status} {service_id:<20} {key_preview}")
            if not key:
                all_present = False

        print("")

        # Test signature generation
        print("Testing signature generation:")
        print("-" * 50)
        try:
            test_sig = auth_mgr.generate_signature(
                'test-service',
                'a' * 64,  # 256-bit hex key
                'POST',
                '/api/test',
                1234567890
            )
            print(f"✅ Signature generated: {test_sig[:32]}...")
            print(f"   Full length: {len(test_sig)} chars")
            print("")
        except Exception as e:
            print(f"❌ Signature generation failed: {e}")
            print("")
            all_present = False

        # Summary
        print("=" * 50)
        if all_present:
            print("✅ Service authentication ready for deployment")
            print("")
            print("All checks passed:")
            print("  • All 6 service keys present")
            print("  • Signature generation working")
            print("  • ServiceAuthManager operational")
            return 0
        else:
            print("❌ Service authentication NOT ready")
            print("")
            print("Issues detected:")
            missing_count = sum(1 for svc in SERVICES if not await auth_mgr.get_service_key(svc))
            if missing_count > 0:
                print(f"  • {missing_count} service key(s) missing")
            print("")
            print("Action required:")
            print("  Run: python3 scripts/generate_service_keys.py")
            return 1

    except Exception as e:
        print(f"❌ Fatal error during verification: {e}")
        print("")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(verify())
    sys.exit(exit_code)
