#!/usr/bin/env python3
"""
Test script for Redis listeners in the Orchestrator.
Creates mock worker messages to test the Redis pub/sub functionality.
"""

import redis
import json
import time
import sys
from src.config import config as global_config_manager
from src.utils.redis_client import get_redis_client


def test_worker_capabilities():
    """Test worker capabilities publishing"""
    print("=== TESTING WORKER CAPABILITIES LISTENER ===")

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get("host", "localhost")
    redis_port = redis_config.get("port", 6379)

    try:
        # Connect to Redis using centralized utility
        client = get_redis_client()
        if client is None:
            print(f"❌ Could not get Redis client from centralized utility")
            return False
        client.ping()
        print(f"✅ Connected to Redis at {redis_host}:{redis_port}")

        # Publish mock worker capabilities
        mock_capabilities = {
            "worker_id": "test_worker_001",
            "capabilities": {
                "system_commands": True,
                "file_operations": True,
                "gui_automation": False,
                "network_operations": True,
                "supported_commands": ["ls", "ps", "whoami", "ifconfig", "netstat"],
            },
            "timestamp": time.time(),
        }

        channel = "worker_capabilities"
        client.publish(channel, json.dumps(mock_capabilities))
        print(f"✅ Published worker capabilities to channel '{channel}'")
        print(f"   Worker ID: {mock_capabilities['worker_id']}")
        print(f"   Capabilities: {list(mock_capabilities['capabilities'].keys())}")

        return True

    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing worker capabilities: {e}")
        return False


def test_command_approval():
    """Test command approval publishing"""
    print("\n=== TESTING COMMAND APPROVAL LISTENER ===")

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get("host", "localhost")
    redis_port = redis_config.get("port", 6379)

    try:
        # Connect to Redis using centralized utility
        client = get_redis_client()
        if client is None:
            print(f"❌ Could not get Redis client from centralized utility")
            return False
        client.ping()

        # Publish mock command approval
        mock_approval = {
            "task_id": "test_task_12345",
            "approved": True,
            "timestamp": time.time(),
            "user": "test_user",
        }

        # Use the approval response channel format
        channel = "command_approval_test_task_12345"
        client.publish(channel, json.dumps(mock_approval))
        print(f"✅ Published command approval to channel '{channel}'")
        print(f"   Task ID: {mock_approval['task_id']}")
        print(f"   Approved: {mock_approval['approved']}")

        return True

    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing command approval: {e}")
        return False


def test_redis_connection():
    """Test basic Redis connection"""
    print("=== TESTING REDIS CONNECTION ===")

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get("host", "localhost")
    redis_port = redis_config.get("port", 6379)

    try:
        client = get_redis_client()
        if client is None:
            print(f"❌ Could not get Redis client from centralized utility")
            return False
        client.ping()
        print(f"✅ Redis connection successful at {redis_host}:{redis_port}")

        # Test pub/sub functionality
        pubsub = client.pubsub()
        test_channel = "test_channel"
        pubsub.subscribe(test_channel)

        # Publish a test message
        client.publish(test_channel, "test message")

        # Try to receive the message
        message = pubsub.get_message(timeout=1)
        if message and message["type"] == "subscribe":
            message = pubsub.get_message(timeout=1)

        pubsub.unsubscribe(test_channel)
        pubsub.close()

        if message and message["type"] == "message":
            print("✅ Redis pub/sub functionality working")
            return True
        else:
            print("⚠️  Redis pub/sub test message not received")
            return False

    except Exception as e:
        print(f"❌ Redis connection test failed: {e}")
        return False


def main():
    """Run all Redis listener tests"""
    print("Starting Redis Listener Tests...")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # Test Redis connection
    results.append(test_redis_connection())

    # Test worker capabilities
    results.append(test_worker_capabilities())

    # Test command approval
    results.append(test_command_approval())

    # Summary
    print(f"\n=== TEST RESULTS SUMMARY ===")
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("✅ All Redis listener tests PASSED")
        print("\n🎯 INSTRUCTIONS:")
        print(
            "   1. Check the AutoBot backend logs to see if the orchestrator received the test messages"
        )
        print(
            "   2. Look for log entries about worker capabilities updates and command approvals"
        )
        print("   3. The background Redis listeners should now be fully functional")
    else:
        print("❌ Some Redis listener tests FAILED")
        print("   Check Redis connection and configuration")

    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
