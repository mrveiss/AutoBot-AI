#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Verify service authentication is ready for deployment."""

import asyncio
import logging
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.security.service_auth import ServiceAuthManager
from utils.redis_client import get_redis_client as get_redis_manager

# All 6 services that should have keys
SERVICES = [
    "main-backend",
    "frontend",
    "npu-worker",
    "redis-stack",
    "ai-stack",
    "browser-service",
]


async def verify():
    """Verify service authentication infrastructure."""
    logger.info("🔐 Service Authentication Verification")
    logger.info("=" * 50)
    logger.info("")

    try:
        # Get Redis connection
        redis_mgr = await get_redis_manager()
        redis = await redis_mgr.main()
        auth_mgr = ServiceAuthManager(redis)

        logger.info("✅ ServiceAuthManager initialized successfully")
        logger.info("")

        # Verify all service keys
        logger.info("Checking service keys:")
        logger.info("-" * 50)
        all_present = True
        for service_id in SERVICES:
            key = await auth_mgr.get_service_key(service_id)
            status = "✅" if key else "❌"
            key_preview = f"{key[:16]}..." if key else "MISSING"
            logger.info(f"{status} {service_id:<20} {key_preview}")
            if not key:
                all_present = False

        logger.info("")

        # Test signature generation
        logger.info("Testing signature generation:")
        logger.info("-" * 50)
        try:
            test_sig = auth_mgr.generate_signature(
                "test-service",
                "a" * 64,  # 256-bit hex key
                "POST",
                "/api/test",
                1234567890,
            )
            logger.info(f"✅ Signature generated: {test_sig[:32]}...")
            logger.info(f"   Full length: {len(test_sig)} chars")
            logger.info("")
        except Exception as e:
            logger.error(f"❌ Signature generation failed: {e}")
            logger.info("")
            all_present = False

        # Summary
        logger.info("=" * 50)
        if all_present:
            logger.info("✅ Service authentication ready for deployment")
            logger.info("")
            logger.info("All checks passed:")
            logger.info("  • All 6 service keys present")
            logger.info("  • Signature generation working")
            logger.info("  • ServiceAuthManager operational")
            return 0
        else:
            logger.error("❌ Service authentication NOT ready")
            logger.info("")
            logger.info("Issues detected:")
            missing_count = sum(
                1 for svc in SERVICES if not await auth_mgr.get_service_key(svc)
            )
            if missing_count > 0:
                logger.info(f"  • {missing_count} service key(s) missing")
            logger.info("")
            logger.info("Action required:")
            logger.info("  Run: python3 scripts/generate_service_keys.py")
            return 1

    except Exception as e:
        logger.error(f"❌ Fatal error during verification: {e}")
        logger.info("")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(verify())
    sys.exit(exit_code)
