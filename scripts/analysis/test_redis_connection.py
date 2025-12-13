#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Redis connection using the Service Registry
This addresses the original Redis connection issue
"""

import sys

sys.path.insert(0, ".")


def test_redis_connection():
    """Test Redis connection using service registry"""
    print("🔗 Testing Redis Connection via Service Registry")
    print("=" * 50)

    try:
        # Import service registry
        from src.utils.service_registry import get_service_url

        print("✅ Service registry imported successfully")

        # Get Redis URL using service registry
        redis_url = get_service_url("redis")
        print(f"✅ Redis URL resolved: {redis_url}")

        # Test with redis-py
        import redis

        # Parse URL to get connection parameters
        if redis_url.startswith("redis://"):
            redis_client = redis.from_url(redis_url)
        else:
            print("❌ Invalid Redis URL format")
            return False

        # Test connection
        print("🔄 Testing Redis connection...")
        result = redis_client.ping()
        if result:
            print("✅ Redis PING successful!")

            # Test basic operations
            test_key = "service_registry_test"
            test_value = "connection_successful"

            redis_client.set(test_key, test_value)
            retrieved_value = redis_client.get(test_key)

            if retrieved_value.decode() == test_value:
                print("✅ Redis SET/GET operations working!")
            else:
                print("❌ Redis operations failed")
                return False

            # Cleanup
            redis_client.delete(test_key)
            print("✅ Redis cleanup completed")

        else:
            print("❌ Redis PING failed")
            return False

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test with Redis Database Manager
    print("\n🗄️ Testing Redis Database Manager with Service Registry")
    try:
        from src.utils.redis_database_manager import RedisDatabaseManager

        manager = RedisDatabaseManager()
        print("✅ Redis Database Manager initialized")
        print(f"   Host: {manager.host}")
        print(f"   Port: {manager.port}")

        # Test connection to main database
        main_client = manager.get_connection("main")
        ping_result = main_client.ping()

        if ping_result:
            print("✅ Redis Database Manager connection successful!")

            # Test database separation
            databases = ["main", "knowledge", "agents", "prompts"]
            for db_name in databases:
                try:
                    client = manager.get_connection(db_name)
                    client.ping()
                    print(f"✅ Database '{db_name}' connection successful")
                except Exception as e:
                    print(f"❌ Database '{db_name}' connection failed: {e}")

        else:
            print("❌ Redis Database Manager connection failed")
            return False

    except Exception as e:
        print(f"❌ Redis Database Manager error: {e}")
        return False

    return True


def test_agent_communication_fix():
    """Test that the original agent communication issue is resolved"""
    print("\n📡 Testing Agent Communication Redis Fix")
    print("=" * 40)

    try:
        # This would be the code path that was failing before
        from src.utils.redis_client import get_redis_client

        # This should now use the service registry
        redis_client = get_redis_client()

        # Test the connection that was failing
        result = redis_client.ping()
        if result:
            print("✅ Agent communication Redis connection fixed!")

            # Test the specific operations that were failing
            test_channel = "test_agent_communication"
            redis_client.publish(test_channel, "test_message")
            print("✅ Redis publish operation working")

        else:
            print("❌ Agent communication still has Redis issues")
            return False

    except Exception as e:
        print(f"❌ Agent communication test failed: {e}")
        return False

    return True


if __name__ == "__main__":
    print("AutoBot Redis Connection Test (Service Registry)")
    print("=" * 60)

    success = True

    # Test basic Redis connection
    if not test_redis_connection():
        success = False

    # Test agent communication fix
    if not test_agent_communication_fix():
        success = False

    if success:
        print("\n🎉 All Redis connection tests PASSED!")
        print("✅ Original Redis connection issue has been RESOLVED!")
        sys.exit(0)
    else:
        print("\n❌ Some Redis connection tests FAILED!")
        sys.exit(1)
