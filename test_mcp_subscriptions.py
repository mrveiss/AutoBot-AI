#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Manual test script for MCP resource subscriptions (MVA-2166)

Tests the subscription infrastructure without requiring a running backend.
"""

import asyncio
import tempfile
from pathlib import Path

from autobot-backend.services.mcp_subscription_manager import (
    MCPSubscriptionManager,
    _uri_to_channel,
)


async def test_subscription_manager():
    """Test basic subscription manager functionality."""
    print("Testing MCPSubscriptionManager...")

    manager = MCPSubscriptionManager()

    # Test file:// URI subscription
    session1 = "test-session-1"
    uri1 = "file:///tmp/test.txt"

    print(f"\n1. Subscribing {session1} to {uri1}")
    success = await manager.subscribe(session1, uri1)
    assert success, "Subscription should succeed"

    stats = manager.get_subscription_stats()
    print(f"   Stats: {stats}")
    assert stats["total_subscriptions"] == 1
    assert stats["active_sessions"] == 1

    # Test channel generation
    channel = _uri_to_channel(uri1)
    print(f"   Channel: {channel}")
    assert channel.startswith("mcp:resource:")

    # Test multiple sessions
    session2 = "test-session-2"
    print(f"\n2. Subscribing {session2} to {uri1}")
    await manager.subscribe(session2, uri1)

    stats = manager.get_subscription_stats()
    print(f"   Stats: {stats}")
    assert stats["total_subscriptions"] == 2
    assert stats["active_sessions"] == 2

    # Test unsubscribe
    print(f"\n3. Unsubscribing {session1} from {uri1}")
    await manager.unsubscribe(session1, uri1)

    stats = manager.get_subscription_stats()
    print(f"   Stats: {stats}")
    assert stats["total_subscriptions"] == 1
    assert stats["active_sessions"] == 2  # session1 still has no subscriptions

    # Test unsubscribe all for session
    print(f"\n4. Unsubscribing {session2} from all")
    count = await manager.unsubscribe_session(session2)
    print(f"   Removed {count} subscriptions")
    assert count == 1

    stats = manager.get_subscription_stats()
    print(f"   Stats: {stats}")
    assert stats["total_subscriptions"] == 0

    print("\n✅ All subscription manager tests passed!")


async def test_file_watcher():
    """Test file watcher functionality."""
    print("\nTesting file watcher...")

    manager = MCPSubscriptionManager()

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        temp_path = f.name
        f.write("Initial content\n")

    try:
        uri = f"file://{temp_path}"
        session = "watcher-test"

        print(f"\n1. Subscribing to {uri}")
        await manager.subscribe(session, uri)

        stats = manager.get_subscription_stats()
        print(f"   Stats: {stats}")
        # File watcher should be started
        assert stats["active_file_watchers"] >= 1

        print("\n2. Waiting 2 seconds (watcher should detect no changes)")
        await asyncio.sleep(2)

        print("\n3. Modifying file")
        Path(temp_path).write_text("Modified content\n")

        print("   Waiting 2 seconds (watcher should detect modification)")
        await asyncio.sleep(2)

        print("\n4. Unsubscribing")
        await manager.unsubscribe(session, uri)

        stats = manager.get_subscription_stats()
        print(f"   Stats: {stats}")
        # File watcher should be stopped
        assert stats["active_file_watchers"] == 0

        print("\n✅ File watcher test passed!")

    finally:
        # Cleanup
        Path(temp_path).unlink()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("MCP Subscription Tests (MVA-2166)")
    print("=" * 60)

    try:
        await test_subscription_manager()
        await test_file_watcher()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
