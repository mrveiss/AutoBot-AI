# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Issues #512, #513, #514 Concurrency Fixes

Verifies thread safety of:
1. Issue #513: websockets.py _npu_events_subscribed locking
2. Issue #514: filesystem_mcp.py per-file locking
3. Issue #514: prompts.py per-file locking
4. Issue #514: logs.py per-file locking

These tests verify the acceptance criteria:
- Thread-safe lazy initialization (#512 - verified in test_issue481)
- Concurrent global state access safety (#513)
- Concurrent file write safety (#514)
"""

import asyncio
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Enough concurrency to lose an unguarded double-check reliably on WSL2/CI.
THREAD_COUNT = 20


class TestWebsocketsNPUEventsLocking:
    """Test Issue #513: websockets.py _npu_events_subscribed thread safety"""

    def test_npu_events_lock_exists(self):
        """Test that websockets module has the NPU events lock"""
        from api import websockets

        assert hasattr(websockets, "_npu_events_lock")
        assert isinstance(websockets._npu_events_lock, type(threading.Lock()))

    def test_npu_events_subscribed_flag_exists(self):
        """Test that _npu_events_subscribed flag exists"""
        from api import websockets

        assert hasattr(websockets, "_npu_events_subscribed")

    def test_subscription_happens_exactly_once_under_contention(self):
        """The #513 defect: without the lock, racing callers each subscribed.

        This used to grep ``inspect.getsource`` for ``with _npu_events_lock:``
        and count occurrences of the flag name (#13311) -- a pattern match that
        passes for a lock held around the wrong thing, and breaks on any
        refactor. The observable is duplicate subscriptions: a handler
        registered N times fires N times per event.
        """
        import threading

        from api import websockets

        websockets._npu_events_subscribed = False
        subscriptions = []
        barrier = threading.Barrier(THREAD_COUNT)
        errors = []

        bus = MagicMock()

        def _record(topic, handler):
            # Widen the race the lock has to close: a slow subscribe is what
            # lets a second thread through an unguarded check.
            subscriptions.append(topic)
            time.sleep(0.001)

        bus.subscribe = _record

        def _init():
            try:
                barrier.wait(timeout=5)
                websockets.init_npu_worker_websocket()
            except Exception as exc:  # noqa: BLE001 - reported via `errors`
                errors.append(exc)

        with patch.object(websockets, "get_event_bus", lambda: bus):
            threads = [threading.Thread(target=_init) for _ in range(THREAD_COUNT)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        assert not errors, f"errors during concurrent init: {errors}"
        assert len(subscriptions) == len(set(subscriptions)), (
            f"#513 regression: {len(subscriptions)} subscribe() calls for "
            f"{len(set(subscriptions))} distinct topics — every event would be "
            f"broadcast more than once"
        )
        assert websockets._npu_events_subscribed is True

    def test_a_failed_subscribe_does_not_latch_the_flag(self):
        """The mirror: the flag must not claim success the bus never gave."""
        from api import websockets

        websockets._npu_events_subscribed = False
        bus = MagicMock()
        bus.subscribe = MagicMock(side_effect=RuntimeError("bus down"))

        with patch.object(websockets, "get_event_bus", lambda: bus):
            websockets.init_npu_worker_websocket()

        assert websockets._npu_events_subscribed is False, "a failed subscribe must stay retryable"

    def test_concurrent_init_npu_worker_websocket(self):
        """Test concurrent calls to init_npu_worker_websocket"""
        from api import websockets

        # Reset state for clean test
        websockets._npu_events_subscribed = False

        errors = []
        call_count = {"count": 0}

        # Mock the event_manager to avoid actual subscriptions.
        # #7184: pre-fix patched ``event_manager.event_manager`` (a stale
        # module-level singleton attribute that no longer exists after the
        # lazy_singleton refactor — see event_manager.py:102 where
        # ``get_event_manager = lazy_singleton(EventManager)``). Patch the
        # canonical accessor and configure the singleton it returns so
        # init_npu_worker_websocket's repeated ``get_event_manager().subscribe(...)``
        # calls hit the mock instead of the real EventManager.
        with patch.object(websockets, "broadcast_npu_worker_event", MagicMock()):
            with patch("event_manager.get_event_manager") as mock_get_em:
                mock_em = MagicMock()
                mock_em.subscribe = MagicMock()
                mock_get_em.return_value = mock_em

                def init_websocket():
                    try:
                        websockets.init_npu_worker_websocket()
                        call_count["count"] += 1
                    except Exception as e:
                        errors.append(e)

                # Run 20 concurrent initializations
                threads = [threading.Thread(target=init_websocket) for _ in range(20)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

        assert len(errors) == 0, f"Errors during concurrent init: {errors}"
        assert call_count["count"] == 20
        # After all calls, flag should be True
        assert websockets._npu_events_subscribed is True


class TestFilesystemMCPPerFileLocking:
    """Test Issue #514: filesystem_mcp.py per-file locking"""

    def test_file_locks_dict_exists(self):
        """Test that file locks dictionary exists"""
        from api import filesystem_mcp

        assert hasattr(filesystem_mcp, "_file_locks")
        assert isinstance(filesystem_mcp._file_locks, dict)

    def test_file_locks_lock_exists(self):
        """Test that lock for file locks dict exists"""
        from api import filesystem_mcp

        assert hasattr(filesystem_mcp, "_file_locks_lock")
        assert isinstance(filesystem_mcp._file_locks_lock, asyncio.Lock)

    def test_get_file_lock_function_exists(self):
        """Test that _get_file_lock helper exists"""
        from api import filesystem_mcp

        assert hasattr(filesystem_mcp, "_get_file_lock")
        assert asyncio.iscoroutinefunction(filesystem_mcp._get_file_lock)

    @pytest.mark.asyncio
    async def test_get_file_lock_returns_lock(self):
        """Test that _get_file_lock returns an asyncio.Lock"""
        from api.filesystem_mcp import _get_file_lock

        lock = await _get_file_lock("/test/path/file.txt")
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_file_lock_same_path_same_lock(self):
        """Test that same path returns same lock instance"""
        from api.filesystem_mcp import _get_file_lock

        lock1 = await _get_file_lock("/test/path/same.txt")
        lock2 = await _get_file_lock("/test/path/same.txt")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_get_file_lock_different_paths_different_locks(self):
        """Test that different paths return different locks"""
        from api.filesystem_mcp import _get_file_lock

        lock1 = await _get_file_lock("/test/path/file1.txt")
        lock2 = await _get_file_lock("/test/path/file2.txt")
        assert lock1 is not lock2

    @pytest.mark.asyncio
    async def test_concurrent_get_file_lock(self):
        """Test concurrent calls to _get_file_lock"""
        from api.filesystem_mcp import _get_file_lock

        locks = []
        errors = []

        async def get_lock():
            try:
                lock = await _get_file_lock("/test/concurrent/path.txt")
                locks.append(lock)
            except Exception as e:
                errors.append(e)

        # Run 50 concurrent lock acquisitions for same path
        await asyncio.gather(*[get_lock() for _ in range(50)])

        assert len(errors) == 0, f"Errors during concurrent lock get: {errors}"
        assert len(locks) == 50
        # All should be the same lock instance
        first_lock = locks[0]
        for lock in locks[1:]:
            assert lock is first_lock


class TestPromptsPyPerFileLocking:
    """Test Issue #514: prompts.py per-file locking"""

    def test_prompt_file_locks_dict_exists(self):
        """Test that prompt file locks dictionary exists"""
        from api import prompts

        assert hasattr(prompts, "_prompt_file_locks")
        assert isinstance(prompts._prompt_file_locks, dict)

    def test_prompt_locks_lock_exists(self):
        """Test that lock for prompt locks dict exists"""
        from api import prompts

        assert hasattr(prompts, "_prompt_locks_lock")
        assert isinstance(prompts._prompt_locks_lock, asyncio.Lock)

    def test_get_prompt_file_lock_function_exists(self):
        """Test that _get_prompt_file_lock helper exists"""
        from api import prompts

        assert hasattr(prompts, "_get_prompt_file_lock")
        assert asyncio.iscoroutinefunction(prompts._get_prompt_file_lock)

    @pytest.mark.asyncio
    async def test_get_prompt_file_lock_returns_lock(self):
        """Test that _get_prompt_file_lock returns an asyncio.Lock"""
        from api.prompts import _get_prompt_file_lock

        lock = await _get_prompt_file_lock("/test/prompts/test.md")
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_prompt_file_lock_same_path_same_lock(self):
        """Test that same path returns same lock instance"""
        from api.prompts import _get_prompt_file_lock

        lock1 = await _get_prompt_file_lock("/test/prompts/same.md")
        lock2 = await _get_prompt_file_lock("/test/prompts/same.md")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_concurrent_get_prompt_file_lock(self):
        """Test concurrent calls to _get_prompt_file_lock"""
        from api.prompts import _get_prompt_file_lock

        locks = []
        errors = []

        async def get_lock():
            try:
                lock = await _get_prompt_file_lock("/test/concurrent/prompt.md")
                locks.append(lock)
            except Exception as e:
                errors.append(e)

        # Run 50 concurrent lock acquisitions
        await asyncio.gather(*[get_lock() for _ in range(50)])

        assert len(errors) == 0, f"Errors during concurrent lock get: {errors}"
        assert len(locks) == 50
        first_lock = locks[0]
        for lock in locks[1:]:
            assert lock is first_lock


class TestLogsPyPerFileLocking:
    """Test Issue #514: logs.py per-file locking"""

    def test_log_file_locks_dict_exists(self):
        """Test that log file locks dictionary exists"""
        from api import logs

        assert hasattr(logs, "_log_file_locks")
        assert isinstance(logs._log_file_locks, dict)

    def test_log_locks_lock_exists(self):
        """Test that lock for log locks dict exists"""
        from api import logs

        assert hasattr(logs, "_log_locks_lock")
        assert isinstance(logs._log_locks_lock, asyncio.Lock)

    def test_get_log_file_lock_function_exists(self):
        """Test that _get_log_file_lock helper exists"""
        from api import logs

        assert hasattr(logs, "_get_log_file_lock")
        assert asyncio.iscoroutinefunction(logs._get_log_file_lock)

    @pytest.mark.asyncio
    async def test_get_log_file_lock_returns_lock(self):
        """Test that _get_log_file_lock returns an asyncio.Lock"""
        from api.logs import _get_log_file_lock

        lock = await _get_log_file_lock("/test/logs/test.log")
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_log_file_lock_same_path_same_lock(self):
        """Test that same path returns same lock instance"""
        from api.logs import _get_log_file_lock

        lock1 = await _get_log_file_lock("/test/logs/same.log")
        lock2 = await _get_log_file_lock("/test/logs/same.log")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_concurrent_get_log_file_lock(self):
        """Test concurrent calls to _get_log_file_lock"""
        from api.logs import _get_log_file_lock

        locks = []
        errors = []

        async def get_lock():
            try:
                lock = await _get_log_file_lock("/test/concurrent/log.log")
                locks.append(lock)
            except Exception as e:
                errors.append(e)

        # Run 50 concurrent lock acquisitions
        await asyncio.gather(*[get_lock() for _ in range(50)])

        assert len(errors) == 0, f"Errors during concurrent lock get: {errors}"
        assert len(locks) == 50
        first_lock = locks[0]
        for lock in locks[1:]:
            assert lock is first_lock


class TestConcurrentFileWriteSafety:
    """Integration tests for concurrent file write safety"""

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_file_no_corruption(self):
        """Test that concurrent writes to same file don't corrupt data.

        #13284 measured this at 13.62s on CI and deliberately left it alone:
        it is not the module's first import of api.filesystem_mcp (that is
        test_file_locks_dict_exists above), so the usual first-import
        explanation does not apply, and no other cause was identified. The
        assertions are a real corruption guard (#514) worth keeping on the PR
        gate, so it is not marked. Cause tracked in #13287.
        """
        import aiofiles

        from api.filesystem_mcp import _get_file_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "concurrent_test.txt"
            errors = []
            write_count = {"count": 0}

            async def write_to_file(content: str):
                try:
                    lock = await _get_file_lock(str(test_file))
                    async with lock:
                        async with aiofiles.open(test_file, "w", encoding="utf-8") as f:
                            await f.write(content)
                    write_count["count"] += 1
                except Exception as e:
                    errors.append(e)

            # Run 20 concurrent writes
            await asyncio.gather(*[write_to_file(f"Content from writer {i}\n" * 100) for i in range(20)])

            assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
            assert write_count["count"] == 20

            # Verify file is not corrupted (contains valid content)
            async with aiofiles.open(test_file, "r", encoding="utf-8") as f:
                content = await f.read()
                assert "Content from writer" in content
                # All lines should be complete (no interleaving)
                lines = content.strip().split("\n")
                for line in lines:
                    assert line.startswith("Content from writer")

    @pytest.mark.asyncio
    async def test_different_files_can_write_concurrently(self):
        """Writes to different files must hold their locks concurrently.

        Issue #13162: the previous version inferred concurrency from wall-clock
        elapsed time (<0.04s for five 10ms critical sections), which reported a
        serialization regression whenever the machine was merely busy — it was
        already relaxed once for the same reason (#11954). This version proves
        the property directly: every writer parks inside its own critical
        section until all five are inside simultaneously. A shared (serialized)
        lock makes that state unreachable, so the wait times out and the test
        fails with a clear message instead of depending on scheduler timing.
        """
        import aiofiles

        from api.filesystem_mcp import _get_file_lock

        writer_count = 5
        # Generous: only a genuinely serialized lock can exhaust this.
        rendezvous_timeout = 10.0

        with tempfile.TemporaryDirectory() as tmpdir:
            inside = 0
            all_inside = asyncio.Event()
            peak_concurrency = 0

            async def write_to_file(file_num: int):
                nonlocal inside, peak_concurrency
                test_file = Path(tmpdir) / f"file_{file_num}.txt"
                lock = await _get_file_lock(str(test_file))
                async with lock:
                    async with aiofiles.open(test_file, "w", encoding="utf-8") as f:
                        await f.write(f"Content {file_num}")
                    inside += 1
                    peak_concurrency = max(peak_concurrency, inside)
                    if inside == writer_count:
                        all_inside.set()
                    try:
                        await asyncio.wait_for(all_inside.wait(), timeout=rendezvous_timeout)
                    except asyncio.TimeoutError:
                        # Serialized: release the other writers so the run ends
                        # cleanly; peak_concurrency below reports the failure.
                        all_inside.set()
                    finally:
                        inside -= 1

            await asyncio.gather(*[write_to_file(i) for i in range(writer_count)])

            assert peak_concurrency == writer_count, (
                f"Writes to different files are serialized: only {peak_concurrency} of "
                f"{writer_count} per-file locks were held at the same time"
            )
            for file_num in range(writer_count):
                assert (Path(tmpdir) / f"file_{file_num}.txt").read_text(encoding="utf-8") == f"Content {file_num}"


class TestLockPatternConsistency:
    """Test that all per-file locking implementations follow the same pattern"""

    @pytest.mark.asyncio
    async def test_all_locks_are_asyncio_locks(self):
        """Verify all file locks use asyncio.Lock"""
        from api.filesystem_mcp import _get_file_lock as fs_lock
        from api.logs import _get_log_file_lock as log_lock
        from api.prompts import _get_prompt_file_lock as prompt_lock

        fs = await fs_lock("/test/fs.txt")
        prompt = await prompt_lock("/test/prompt.md")
        log = await log_lock("/test/log.log")

        assert isinstance(fs, asyncio.Lock)
        assert isinstance(prompt, asyncio.Lock)
        assert isinstance(log, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_lock_dicts_are_isolated(self):
        """Test that each module has its own lock dictionary"""
        from api import filesystem_mcp, logs, prompts

        # Each should have its own dict, not shared
        assert filesystem_mcp._file_locks is not prompts._prompt_file_locks
        assert prompts._prompt_file_locks is not logs._log_file_locks
        assert filesystem_mcp._file_locks is not logs._log_file_locks


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
