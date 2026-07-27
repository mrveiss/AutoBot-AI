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

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

sys.path.insert(0, ".")


def test_redis_connection():
    """Test Redis connection using service registry"""
    logger.info("🔗 Testing Redis Connection via Service Registry")
    logger.info("=" * 50)

    try:
        # Import service registry
        from utils.service_registry import get_service_url

        logger.info("✅ Service registry imported successfully")

        # Get Redis URL using service registry
        redis_url = get_service_url("redis")
        logger.info(f"✅ Redis URL resolved: {redis_url}")

        # Test with redis-py
        import redis

        # Parse URL to get connection parameters
        if redis_url.startswith("redis://"):
            redis_client = redis.from_url(redis_url)
        else:
            logger.error("❌ Invalid Redis URL format")
            return False

        # Test connection
        logger.info("🔄 Testing Redis connection...")
        result = redis_client.ping()
        if result:
            logger.info("✅ Redis PING successful!")

            # Test basic operations
            test_key = "service_registry_test"
            test_value = "connection_successful"

            redis_client.set(test_key, test_value)
            retrieved_value = redis_client.get(test_key)

            if retrieved_value.decode() == test_value:
                logger.info("✅ Redis SET/GET operations working!")
            else:
                logger.error("❌ Redis operations failed")
                return False

            # Cleanup
            redis_client.delete(test_key)
            logger.info("✅ Redis cleanup completed")

        else:
            logger.error("❌ Redis PING failed")
            return False

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except redis.ConnectionError as e:
        logger.error(f"❌ Redis connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test with Redis Database Manager
    logger.info("\n🗄️ Testing Redis Database Manager with Service Registry")
    try:
        from utils.redis_database_manager import RedisDatabaseManager

        manager = RedisDatabaseManager()
        logger.info("✅ Redis Database Manager initialized")
        logger.info(f"   Host: {manager.host}")
        logger.info(f"   Port: {manager.port}")

        # Test connection to main database
        main_client = manager.get_connection("main")
        ping_result = main_client.ping()

        if ping_result:
            logger.info("✅ Redis Database Manager connection successful!")

            # Test database separation
            databases = ["main", "knowledge", "agents", "prompts"]
            for db_name in databases:
                try:
                    client = manager.get_connection(db_name)
                    client.ping()
                    logger.info(f"✅ Database '{db_name}' connection successful")
                except Exception as e:
                    logger.error(f"❌ Database '{db_name}' connection failed: {e}")

        else:
            logger.error("❌ Redis Database Manager connection failed")
            return False

    except Exception as e:
        logger.error(f"❌ Redis Database Manager error: {e}")
        return False

    return True


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
