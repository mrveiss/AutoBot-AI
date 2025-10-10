"""
Performance tests for async chat workflow manager.
Verifies that event loop blocking has been eliminated.
"""

import asyncio
import pytest
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.chat_workflow_manager import ChatWorkflowManager


@pytest.mark.asyncio
async def test_event_loop_no_blocking():
    """Test that chat operations don't block event loop."""
    manager = ChatWorkflowManager()
    await manager.initialize()

    # Measure event loop lag during operations
    start_time = time.time()

    # Perform operations that were previously blocking
    test_session = "test_event_loop_session"

    # Test async Redis operations
    await manager._save_conversation_history(test_session, [
        {"user": "test message", "assistant": "test response"}
    ])
    history = await manager._load_conversation_history(test_session)

    # Test async file operations
    await manager._append_to_transcript(test_session, "user msg", "assistant msg")
    transcript = await manager._load_transcript(test_session)

    # Calculate total time
    total_time = time.time() - start_time

    # Event loop should not be blocked >50ms for these operations
    assert total_time < 0.05, f"Event loop blocked for {total_time}s (>50ms threshold)"

    print(f"✅ Event loop lag test passed: {total_time*1000:.2f}ms")


@pytest.mark.asyncio
async def test_concurrent_chat_requests():
    """Test 50 concurrent chat requests without blocking."""
    manager = ChatWorkflowManager()
    await manager.initialize()

    start_time = time.time()

    async def chat_request(session_id):
        """Simulate a chat request with history operations."""
        # Save history
        await manager._save_conversation_history(f"session_{session_id}", [
            {"user": f"message {session_id}", "assistant": f"response {session_id}"}
        ])
        # Load history
        history = await manager._load_conversation_history(f"session_{session_id}")
        return len(history)

    # 50 concurrent requests
    results = await asyncio.gather(*[chat_request(i) for i in range(50)])

    total_time = time.time() - start_time

    # All requests should complete
    assert len(results) == 50, f"Expected 50 results, got {len(results)}"

    # Average time per request should be reasonable
    avg_time_per_request = total_time / 50
    assert avg_time_per_request < 0.1, f"Average time per request: {avg_time_per_request}s (>100ms threshold)"

    print(f"✅ Concurrent requests test passed: 50 requests in {total_time:.2f}s")
    print(f"   Average per request: {avg_time_per_request*1000:.2f}ms")


@pytest.mark.asyncio
async def test_redis_async_operations():
    """Test that Redis operations are truly async (non-blocking)."""
    manager = ChatWorkflowManager()
    await manager.initialize()

    if manager.redis_client is None:
        pytest.skip("Redis not available for testing")

    # Create a task that monitors event loop responsiveness
    loop_responsive = True

    async def event_loop_monitor():
        """Monitor event loop responsiveness during Redis operations."""
        nonlocal loop_responsive
        for _ in range(10):
            check_start = time.time()
            await asyncio.sleep(0.001)  # 1ms sleep
            check_duration = time.time() - check_start

            # If sleep takes >10ms, event loop is blocked
            if check_duration > 0.01:
                loop_responsive = False
                break

    # Run Redis operations and monitor concurrently
    monitor_task = asyncio.create_task(event_loop_monitor())

    # Perform Redis operations
    for i in range(20):
        await manager._save_conversation_history(f"session_redis_{i}", [
            {"user": f"msg{i}", "assistant": f"resp{i}"}
        ])
        await manager._load_conversation_history(f"session_redis_{i}")

    await monitor_task

    assert loop_responsive, "Event loop was blocked during Redis operations"
    print("✅ Redis async operations test passed: Event loop remained responsive")


@pytest.mark.asyncio
async def test_file_io_async_operations():
    """Test that file I/O operations are truly async (non-blocking)."""
    manager = ChatWorkflowManager()
    await manager.initialize()

    # Create a task that monitors event loop responsiveness
    loop_responsive = True

    async def event_loop_monitor():
        """Monitor event loop responsiveness during file I/O."""
        nonlocal loop_responsive
        for _ in range(20):
            check_start = time.time()
            await asyncio.sleep(0.001)  # 1ms sleep
            check_duration = time.time() - check_start

            # If sleep takes >10ms, event loop is blocked
            if check_duration > 0.01:
                loop_responsive = False
                break

    # Run file I/O and monitor concurrently
    monitor_task = asyncio.create_task(event_loop_monitor())

    # Perform file I/O operations
    for i in range(10):
        await manager._append_to_transcript(f"session_file_{i}", f"user{i}", f"assistant{i}")
        await manager._load_transcript(f"session_file_{i}")

    await monitor_task

    assert loop_responsive, "Event loop was blocked during file I/O operations"
    print("✅ File I/O async operations test passed: Event loop remained responsive")


@pytest.mark.asyncio
async def test_mixed_operations_concurrency():
    """Test mixed Redis and file operations running concurrently."""
    manager = ChatWorkflowManager()
    await manager.initialize()

    async def redis_operation(session_id):
        """Perform Redis operation."""
        await manager._save_conversation_history(f"session_{session_id}", [
            {"user": f"msg{session_id}", "assistant": f"resp{session_id}"}
        ])
        return await manager._load_conversation_history(f"session_{session_id}")

    async def file_operation(session_id):
        """Perform file operation."""
        await manager._append_to_transcript(f"session_{session_id}", f"user{session_id}", f"assistant{session_id}")
        return await manager._load_transcript(f"session_{session_id}")

    start_time = time.time()

    # Mix of 25 Redis operations and 25 file operations running concurrently
    redis_tasks = [redis_operation(i) for i in range(25)]
    file_tasks = [file_operation(i) for i in range(25, 50)]

    results = await asyncio.gather(*(redis_tasks + file_tasks))

    total_time = time.time() - start_time

    # All operations should complete
    assert len(results) == 50, f"Expected 50 results, got {len(results)}"

    # Should complete faster than if they were sequential
    # Sequential would be ~50 * 10ms = 500ms minimum
    # Concurrent should be much faster
    assert total_time < 0.5, f"Mixed operations took {total_time}s (sequential performance detected)"

    print(f"✅ Mixed operations concurrency test passed: 50 operations in {total_time:.2f}s")


if __name__ == "__main__":
    # Run tests directly
    print("Running async chat performance tests...")
    asyncio.run(test_event_loop_no_blocking())
    asyncio.run(test_concurrent_chat_requests())
    asyncio.run(test_redis_async_operations())
    asyncio.run(test_file_io_async_operations())
    asyncio.run(test_mixed_operations_concurrency())
    print("\n✅ All performance tests passed!")
