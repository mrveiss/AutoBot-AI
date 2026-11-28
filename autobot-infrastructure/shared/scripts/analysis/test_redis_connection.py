#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test Redis connection using the Service Registry
This addresses the original Redis connection issue
"""

import logging
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

import redis

logger = logging.getLogger(__name__)

# A backend tool (#18289): it deliberately drives backend internals. It puts the backend and the
# repository root (for `autobot_shared`) on its own path, so it runs from any directory with no
# PYTHONPATH; the backend's Python dependencies must be installed.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))


def _check_set_get(redis_client) -> bool:
    """PING, then a SET/GET/DELETE round trip on a throwaway key (bytes client)."""
    logger.info("🔄 Testing Redis connection...")
    if not redis_client.ping():
        logger.error("❌ Redis PING failed")
        return False
    logger.info("✅ Redis PING successful!")

    test_key = "service_registry_test"
    test_value = "connection_successful"
    redis_client.set(test_key, test_value)
    if redis_client.get(test_key).decode() != test_value:
        logger.error("❌ Redis operations failed")
        return False
    logger.info("✅ Redis SET/GET operations working!")

    redis_client.delete(test_key)
    logger.info("✅ Redis cleanup completed")
    return True


def _registry_matches_client(redis_url: str, client) -> bool:
    """True when the registry URL names the host and port the canonical client actually dials."""
    dialled = client.connection_pool.connection_kwargs
    registry = urlparse(redis_url)
    if (registry.hostname, str(registry.port)) != (dialled.get("host"), str(dialled.get("port"))):
        logger.error(
            f"❌ Service registry says {registry.hostname}:{registry.port}, but the canonical client "
            f"(SSOT config) dials {dialled.get('host')}:{dialled.get('port')}"
        )
        return False
    logger.info("✅ Service registry and SSOT config agree on the Redis host and port")
    return True


def _check_registry_connection() -> bool:
    """Resolve the Redis URL through the service registry, check it against the canonical client, use it."""
    try:
        from utils.service_registry import get_service_url

        from autobot_shared.redis_client import require_redis_client

        logger.info("✅ Service registry imported successfully")
        redis_url = get_service_url("redis")
        logger.info(f"✅ Redis URL resolved: {redis_url}")
        if not redis_url.startswith("redis://"):
            logger.error("❌ Invalid Redis URL format")
            return False
        # The connection goes through the canonical client (#18553), whose host and port come from
        # SSOT config; the registry is checked by agreeing with what that client dials.
        client = require_redis_client(database="main", decode_responses=False)
        return _registry_matches_client(redis_url, client) and _check_set_get(client)
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
    except (redis.ConnectionError, ConnectionError) as e:
        # ConnectionError (builtin): the canonical client is disabled, unreachable or its circuit is open.
        logger.error(f"❌ Redis connection error: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        traceback.print_exc()
    return False


def _check_database_manager() -> bool:
    """Connect through the deprecated RedisDatabaseManager wrapper and ping four named databases."""
    logger.info("\n🗄️ Testing Redis Database Manager with Service Registry")
    try:
        # #14518: canonical home is autobot_shared/redis_client.py.
        from autobot_shared.redis_client import RedisDatabaseManager

        manager = RedisDatabaseManager()
        logger.info("✅ Redis Database Manager initialized")
        logger.info(f"   Host: {manager.host}")
        logger.info(f"   Port: {manager.port}")

        if not manager.get_connection("main").ping():
            logger.error("❌ Redis Database Manager connection failed")
            return False
        logger.info("✅ Redis Database Manager connection successful!")

        for db_name in ("main", "knowledge", "agents", "prompts"):
            try:
                manager.get_connection(db_name).ping()
                logger.info(f"✅ Database '{db_name}' connection successful")
            except Exception as e:
                logger.error(f"❌ Database '{db_name}' connection failed: {e}")
    except Exception as e:
        logger.error(f"❌ Redis Database Manager error: {e}")
        return False
    return True


def test_redis_connection():
    """Test Redis connection using service registry"""
    logger.info("🔗 Testing Redis Connection via Service Registry")
    logger.info("=" * 50)
    return _check_registry_connection() and _check_database_manager()


def test_agent_communication_fix():
    """Test that the original agent communication issue is resolved"""
    logger.info("\n📡 Testing Agent Communication Redis Fix")
    logger.info("=" * 40)

    try:
        # This would be the code path that was failing before
        from autobot_shared.redis_client import get_redis_client

        # This should now use the service registry
        redis_client = get_redis_client()

        # Test the connection that was failing
        result = redis_client.ping()
        if result:
            logger.info("✅ Agent communication Redis connection fixed!")

            # Test the specific operations that were failing
            test_channel = "test_agent_communication"
            redis_client.publish(test_channel, "test_message")
            logger.info("✅ Redis publish operation working")

        else:
            logger.error("❌ Agent communication still has Redis issues")
            return False

    except Exception as e:
        logger.error(f"❌ Agent communication test failed: {e}")
        return False

    return True


if __name__ == "__main__":
    logger.info("AutoBot Redis Connection Test (Service Registry)")
    logger.info("=" * 60)

    success = True

    # Test basic Redis connection
    if not test_redis_connection():
        success = False

    # Test agent communication fix
    if not test_agent_communication_fix():
        success = False

    if success:
        logger.info("\n🎉 All Redis connection tests PASSED!")
        logger.info("✅ Original Redis connection issue has been RESOLVED!")
        sys.exit(0)
    else:
        logger.error("\n❌ Some Redis connection tests FAILED!")
        sys.exit(1)
