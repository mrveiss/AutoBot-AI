#!/usr/bin/env python3
"""
Test script for Redis listeners in the Orchestrator.
Creates mock worker messages to test the Redis pub/sub functionality.
"""

import json
import sys
import time

import redis
from config import config as global_config_manager
from utils.redis_client import get_redis_client


def test_worker_capabilities():
    """Test worker capabilities publishing"""
    print("=== TESTING WORKER CAPABILITIES LISTENER ===")  # noqa: print

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get("host", "localhost")
    redis_port = redis_config.get("port", 6379)

    try:
        # Connect to Redis using centralized utility
        client = get_redis_client()
        if client is None:
            print(  # noqa: print
                "❌ Could not get Redis client from centralized utility"
            )  # noqa: print
            return False
        client.ping()
        print(f"✅ Connected to Redis at {redis_host}:{redis_port}")  # noqa: print

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
        print(f"✅ Published worker capabilities to channel '{channel}'")  # noqa: print
        print(f"   Worker ID: {mock_capabilities['worker_id']}")  # noqa: print
        print(  # noqa: print
            f"   Capabilities: {list(mock_capabilities['capabilities'].keys())}"
        )  # noqa: print

        return True

    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")  # noqa: print
        return False
    except Exception as e:
        print(f"❌ Error testing worker capabilities: {e}")  # noqa: print
        return False


def test_command_approval():
    """Test command approval publishing"""
    print("\n=== TESTING COMMAND APPROVAL LISTENER ===")  # noqa: print

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_config.get("host", "localhost")
    redis_config.get("port", 6379)

    try:
        # Connect to Redis using centralized utility
        client = get_redis_client()
        if client is None:
            print(  # noqa: print
                "❌ Could not get Redis client from centralized utility"
            )  # noqa: print
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
        print(f"✅ Published command approval to channel '{channel}'")  # noqa: print
        print(f"   Task ID: {mock_approval['task_id']}")  # noqa: print
        print(f"   Approved: {mock_approval['approved']}")  # noqa: print

        return True

    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")  # noqa: print
        return False
    except Exception as e:
        print(f"❌ Error testing command approval: {e}")  # noqa: print
        return False


def test_redis_connection():
    """Test basic Redis connection"""
    print("=== TESTING REDIS CONNECTION ===")  # noqa: print

    # Get Redis configuration
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get("host", "localhost")
    redis_port = redis_config.get("port", 6379)

    try:
        client = get_redis_client()
        if client is None:
            print(  # noqa: print
                "❌ Could not get Redis client from centralized utility"
            )  # noqa: print
            return False
        client.ping()
        print(  # noqa: print
            f"✅ Redis connection successful at {redis_host}:{redis_port}"
        )  # noqa: print

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
            print("✅ Redis pub/sub functionality working")  # noqa: print
            return True
        else:
            print("⚠️  Redis pub/sub test message not received")  # noqa: print
            return False

    except Exception as e:
        print(f"❌ Redis connection test failed: {e}")  # noqa: print
        return False


def main():
    """Run all Redis listener tests"""
    print("Starting Redis Listener Tests...")  # noqa: print
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")  # noqa: print

    results = []

    # Test Redis connection
    results.append(test_redis_connection())

    # Test worker capabilities
    results.append(test_worker_capabilities())

    # Test command approval
    results.append(test_command_approval())

    # Summary
    print("\n=== TEST RESULTS SUMMARY ===")  # noqa: print
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")  # noqa: print

    if passed == total:
        print("✅ All Redis listener tests PASSED")  # noqa: print
        print("\n🎯 INSTRUCTIONS:")  # noqa: print
        print(  # noqa: print
            "   1. Check the AutoBot backend logs to see if the orchestrator received the test messages"
        )
        print(  # noqa: print
            "   2. Look for log entries about worker capabilities updates and command approvals"
        )
        print(  # noqa: print
            "   3. The background Redis listeners should now be fully functional"
        )  # noqa: print
    else:
        print("❌ Some Redis listener tests FAILED")  # noqa: print
        print("   Check Redis connection and configuration")  # noqa: print

    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")  # noqa: print
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")  # noqa: print
        sys.exit(1)
