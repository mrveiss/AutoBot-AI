#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verify service authentication is ready for deployment."""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "autobot-backend"))
sys.path.insert(0, str(PROJECT_ROOT / "autobot_shared"))

from autobot_shared.redis_client import get_async_redis_client  # noqa: E402
from security.service_auth import ServiceAuthManager  # noqa: E402

# All 6 services that should have keys
SERVICES = [
    "main-backend",
    "frontend",
    "npu-worker",
    "redis-stack",
    "ai-stack",
    "browser-service",
]


async def _check_service_keys(auth_mgr):
    """Verify all service keys exist in Redis.

    Helper for verify (#1734).
    Returns True if all keys are present.
    """
    logger.info("Checking service keys:")
    logger.info("-" * 50)
    all_present = True
    for service_id in SERVICES:
        key = await auth_mgr.get_service_key(service_id)
        status = "OK" if key else "MISSING"
        key_preview = f"{key[:8]}***" if key else "MISSING"
        logger.info("  %s  %-20s %s", status, service_id, key_preview)
        if not key:
            all_present = False
    logger.info("")
    return all_present


def _check_signature_generation(auth_mgr):
    """Test HMAC signature generation.

    Helper for verify (#1734).
    Returns True if signature generation works.
    """
    logger.info("Testing signature generation:")
    logger.info("-" * 50)
    try:
        test_sig = auth_mgr.generate_signature("test-service", "a" * 64, "POST", "/api/test", 1234567890)
        logger.info("  Signature: %s*** (%d chars)", test_sig[:8], len(test_sig))
        logger.info("")
        return True
    except Exception:
        logger.exception("Signature generation failed")
        logger.info("")
        return False


async def verify():
    """Verify service authentication infrastructure."""
    logger.info("Service Authentication Verification")
    logger.info("=" * 50)
    logger.info("")

    try:
        redis = await get_async_redis_client(database="main")
        auth_mgr = ServiceAuthManager(redis)
        logger.info("ServiceAuthManager initialized successfully")
        logger.info("")

        keys_ok = await _check_service_keys(auth_mgr)
        sig_ok = _check_signature_generation(auth_mgr)

        logger.info("=" * 50)
        if keys_ok and sig_ok:
            logger.info("Service authentication ready for deployment")
            logger.info("  - All %d service keys present", len(SERVICES))
            logger.info("  - Signature generation working")
            return 0

        logger.error("Service authentication NOT ready")
        logger.info("Action: python3 scripts/generate_service_keys.py")
        return 1

    except Exception:
        logger.exception("Fatal error during verification")
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    exit_code = asyncio.run(verify())
    sys.exit(exit_code)
