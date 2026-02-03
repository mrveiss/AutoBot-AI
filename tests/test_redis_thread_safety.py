"""
Test thread-safety fixes for Redis connection pool

Tests for the two code review warnings that were fixed:
1. Pool statistics race condition (get_pool_statistics with pool._lock)
2. Idle cleanup list mutation (cleanup_idle_connections with proper synchronization)
"""

import asyncio
import concurrent.futures
import time
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.utils.redis_client import RedisConnectionManager


class TestPoolStatisticsThreadSafety:
    """Test thread-safe pool statistics access"""

    def test_get_pool_statistics_uses_lock(self):
        """Verify get_pool_statistics accesses pool internals within lock"""
        manager = RedisConnectionManager()

        # Create mock pool with lock
        mock_pool = Mock()
        mock_pool._lock = MagicMock()
        mock_pool._created_connections = 5

        # Create mock connections without _last_use (won't be counted as idle)
        conn1 = Mock(spec=[])  # No _last_use attribute
        conn2 = Mock(spec=[])
        conn3 = Mock(spec=[])

        mock_pool._available_connections = [conn1, conn2, conn3]
        mock_pool._in_use_connections = [Mock(spec=[]), Mock(spec=[])]
        mock_pool.max_connections = 100

        # Add pool to manager
        manager._sync_pools["test_db"] = mock_pool

        # Call get_pool_statistics
        stats = manager.get_pool_statistics("test_db")

        # Verify lock was acquired
        mock_pool._lock.__enter__.assert_called_once()
        mock_pool._lock.__exit__.assert_called_once()

        # Verify statistics are correct
        assert stats.database_name == "test_db"
        assert stats.created_connections == 5
        assert stats.available_connections == 3
        assert stats.in_use_connections == 2
        assert stats.max_connections == 100
        assert stats.idle_connections == 0  # No connections have _last_use

    def test_get_pool_statistics_concurrent_access(self):
        """Test pool statistics under concurrent access from multiple threads"""
        manager = RedisConnectionManager()

        # Create mock pool with real lock
        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()
        mock_pool._created_connections = 10
        # Create connections without _last_use attribute
        mock_pool._available_connections = [Mock(spec=[]) for _ in range(5)]
        mock_pool._in_use_connections = [Mock(spec=[]) for _ in range(5)]
        mock_pool.max_connections = 100

        manager._sync_pools["test_db"] = mock_pool

        # Run concurrent statistics access from multiple threads
        results = []
        errors = []

        def get_stats():
            try:
                stats = manager.get_pool_statistics("test_db")
                results.append(stats)
            except Exception as e:
                errors.append(e)

        # Execute 50 concurrent calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_stats) for _ in range(50)]
            concurrent.futures.wait(futures)

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"

        # Verify all calls got valid statistics
        assert len(results) == 50
        for stats in results:
            assert stats.created_connections == 10
            assert stats.available_connections == 5
            assert stats.in_use_connections == 5

    def test_get_pool_statistics_handles_missing_pool(self):
        """Verify get_pool_statistics raises ValueError for missing pool"""
        manager = RedisConnectionManager()

        with pytest.raises(
            ValueError, match="No sync pool found for database 'nonexistent'"
        ):
            manager.get_pool_statistics("nonexistent")


class TestIdleCleanupThreadSafety:
    """Test thread-safe idle connection cleanup"""

    @pytest.mark.asyncio
    async def test_cleanup_idle_connections_uses_lock(self):
        """Verify cleanup_idle_connections accesses pool internals within lock"""
        manager = RedisConnectionManager()

        # Create mock pool with lock
        mock_pool = Mock()
        mock_pool._lock = MagicMock()

        # Create mock idle connections
        idle_conn = Mock()
        idle_conn._last_use = datetime.now()
        idle_conn.disconnect = Mock()

        # Mock time to make connection appear idle (>300s)
        _old_time = datetime.now()
        with patch("src.utils.redis_client.datetime") as mock_datetime:
            # First call: get current time for idle check
            # Second call: return time 400s in the future
            mock_datetime.now.side_effect = [
                datetime(2025, 1, 1, 12, 0, 0),  # Start time
                datetime(2025, 1, 1, 12, 10, 0),  # 600s later (idle check)
            ]

            mock_pool._available_connections = [idle_conn]
            manager._sync_pools["test_db"] = mock_pool
            manager._max_idle_time_seconds = 300

            # Run cleanup
            await manager.cleanup_idle_connections()

        # Verify lock was acquired
        mock_pool._lock.__enter__.assert_called()
        mock_pool._lock.__exit__.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_idle_connections_builds_removal_list_first(self):
        """Verify cleanup identifies connections to remove before modifying list"""
        manager = RedisConnectionManager()

        # Create mock pool with real lock
        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()

        # Create mock connections (some idle, some not)
        old_time = datetime(2025, 1, 1, 12, 0, 0)  # 10 minutes ago
        recent_time = datetime(2025, 1, 1, 12, 9, 0)  # 1 minute ago

        idle_conn_1 = Mock()
        idle_conn_1._last_use = old_time
        idle_conn_1.disconnect = Mock()

        idle_conn_2 = Mock()
        idle_conn_2._last_use = old_time
        idle_conn_2.disconnect = Mock()

        active_conn = Mock()
        active_conn._last_use = recent_time
        active_conn.disconnect = Mock()

        available_connections = [idle_conn_1, active_conn, idle_conn_2]
        mock_pool._available_connections = available_connections

        manager._sync_pools["test_db"] = mock_pool
        manager._max_idle_time_seconds = 300  # 5 minutes

        # Mock current time to be 10 minutes after old_time
        with patch("src.utils.redis_client.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 10, 0)

            # Run cleanup
            await manager.cleanup_idle_connections()

        # Verify idle connections were disconnected
        idle_conn_1.disconnect.assert_called_once()
        idle_conn_2.disconnect.assert_called_once()

        # Verify active connection was NOT disconnected
        active_conn.disconnect.assert_not_called()

        # Verify only idle connections were removed from list
        assert len(mock_pool._available_connections) == 1
        assert mock_pool._available_connections[0] == active_conn

    @pytest.mark.asyncio
    async def test_cleanup_handles_concurrent_pool_modifications(self):
        """Test cleanup handles connections removed by other threads"""
        manager = RedisConnectionManager()

        # Create mock pool with real lock
        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()

        # Create mock idle connection
        idle_conn = Mock()
        idle_conn._last_use = datetime(2025, 1, 1, 12, 0, 0)

        # Mock disconnect to simulate concurrent removal (raises ValueError)
        def disconnect_with_removal():
            # Simulate another thread removing connection
            if idle_conn in mock_pool._available_connections:
                mock_pool._available_connections.remove(idle_conn)
            raise ValueError("Connection already removed")

        idle_conn.disconnect = Mock(side_effect=disconnect_with_removal)

        mock_pool._available_connections = [idle_conn]
        manager._sync_pools["test_db"] = mock_pool
        manager._max_idle_time_seconds = 300

        # Mock current time
        with patch("src.utils.redis_client.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 10, 0)

            # Run cleanup - should not raise exception
            await manager.cleanup_idle_connections()

        # Verify disconnect was attempted
        idle_conn.disconnect.assert_called_once()

        # Verify no errors were raised (ValueError was caught)
        # Test passes if no exception propagated

    @pytest.mark.asyncio
    async def test_cleanup_doesnt_affect_active_connections(self):
        """Verify cleanup only removes idle connections, not active ones"""
        manager = RedisConnectionManager()

        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()

        # Create connections with different idle times
        very_old = datetime(2025, 1, 1, 11, 0, 0)  # 1 hour ago
        old = datetime(2025, 1, 1, 11, 54, 0)  # 6 minutes ago (idle)
        recent = datetime(2025, 1, 1, 11, 59, 30)  # 30 seconds ago (active)

        conn_1 = Mock()
        conn_1._last_use = very_old
        conn_1.disconnect = Mock(return_value=None)

        conn_2 = Mock()
        conn_2._last_use = old
        conn_2.disconnect = Mock(return_value=None)

        conn_3 = Mock()
        conn_3._last_use = recent
        conn_3.disconnect = Mock(return_value=None)

        conn_4 = Mock(spec=[])  # No _last_use attribute (shouldn't be removed)
        conn_4.disconnect = Mock(return_value=None)

        # Need to use list() so pool can modify it
        mock_pool._available_connections = [conn_1, conn_2, conn_3, conn_4]
        manager._sync_pools["test_db"] = mock_pool
        manager._max_idle_time_seconds = 300  # 5 minutes

        # Use freezegun or manual datetime mocking
        # Mock datetime.now() to return consistent value
        import src.utils.redis_client as redis_client_module

        original_datetime = redis_client_module.datetime

        class MockDatetime:
            @staticmethod
            def now():
                return datetime(2025, 1, 1, 12, 0, 0)

        redis_client_module.datetime = MockDatetime

        try:
            # Run cleanup
            await manager.cleanup_idle_connections()

            # Verify only old connections were disconnected
            conn_1.disconnect.assert_called_once()  # 1 hour old - removed
            conn_2.disconnect.assert_called_once()  # 6 minutes old - removed
            conn_3.disconnect.assert_not_called()  # 30 seconds old - kept
            conn_4.disconnect.assert_not_called()  # No _last_use - kept

            # Verify correct connections remain
            assert len(mock_pool._available_connections) == 2
            assert conn_3 in mock_pool._available_connections
            assert conn_4 in mock_pool._available_connections
        finally:
            # Restore original datetime
            redis_client_module.datetime = original_datetime


class TestRaceConditionPrevention:
    """Test race condition prevention in fixed methods"""

    def test_pool_statistics_no_race_with_pool_operations(self):
        """Test statistics access doesn't race with pool operations"""
        manager = RedisConnectionManager()

        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()
        mock_pool._created_connections = 10
        # Create connections without _last_use
        mock_pool._available_connections = [Mock(spec=[]) for _ in range(5)]
        mock_pool._in_use_connections = [Mock(spec=[]) for _ in range(5)]
        mock_pool.max_connections = 100

        manager._sync_pools["test_db"] = mock_pool

        results = []

        def get_stats_and_modify():
            """Simulate getting stats while another thread modifies pool"""
            # Get statistics
            stats = manager.get_pool_statistics("test_db")
            results.append(stats)

            # Simulate pool modification
            with mock_pool._lock:
                mock_pool._available_connections.append(Mock(spec=[]))

        # Run concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_stats_and_modify) for _ in range(20)]
            concurrent.futures.wait(futures)

        # Verify all operations completed without errors
        assert len(results) == 20

        # All initial reads should see original state (5 available)
        # Later reads may see more connections added
        for stats in results:
            assert stats.available_connections >= 5

    @pytest.mark.asyncio
    async def test_cleanup_no_race_with_statistics(self):
        """Test cleanup doesn't race with statistics gathering"""
        manager = RedisConnectionManager()

        from threading import Lock

        mock_pool = Mock()
        mock_pool._lock = Lock()

        # Create connections
        old_conn = Mock()
        old_conn._last_use = datetime(2025, 1, 1, 12, 0, 0)
        old_conn.disconnect = Mock()

        recent_conn = Mock()
        recent_conn._last_use = datetime(2025, 1, 1, 12, 9, 0)
        recent_conn.disconnect = Mock()

        mock_pool._created_connections = 2
        mock_pool._available_connections = [old_conn, recent_conn]
        mock_pool._in_use_connections = []
        mock_pool.max_connections = 100

        manager._sync_pools["test_db"] = mock_pool
        manager._max_idle_time_seconds = 300

        stats_results = []
        cleanup_done = False

        def get_stats_repeatedly():
            """Get statistics in a loop"""
            for _ in range(10):
                try:
                    stats = manager.get_pool_statistics("test_db")
                    stats_results.append(stats)
                    time.sleep(0.001)  # Small delay
                except Exception as e:
                    stats_results.append(f"Error: {e}")

        async def run_cleanup():
            """Run cleanup once"""
            nonlocal cleanup_done
            with patch("src.utils.redis_client.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 10, 0)
                await manager.cleanup_idle_connections()
            cleanup_done = True

        # Run statistics gathering and cleanup concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            stats_future = executor.submit(get_stats_repeatedly)
            cleanup_future = asyncio.create_task(run_cleanup())

            # Wait for both
            await cleanup_future
            stats_future.result()

        # Verify cleanup completed
        assert cleanup_done

        # Verify statistics were gathered without errors
        assert len([s for s in stats_results if isinstance(s, str)]) == 0
        assert len(stats_results) >= 10

        # Verify old connection was cleaned up
        old_conn.disconnect.assert_called_once()
        recent_conn.disconnect.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
