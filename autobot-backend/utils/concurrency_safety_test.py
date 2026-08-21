# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for race condition fixes in AutoBot

Tests three critical concurrency fixes:
1. Terminal output buffer race (asyncio.Lock)
2. File write atomicity (fcntl.flock + atomic rename)
3. Chat save race (message merging)

Author: AutoBot Code Skeptic Agent
Date: 2025-10-24
"""

import asyncio
import json
import os
import statistics
import tempfile
import time
from unittest.mock import AsyncMock, Mock

import aiofiles
import pytest

# Test Issue 3: Terminal Output Buffer Race


class TestTerminalBufferRace:
    """Test terminal output buffer concurrency safety"""

    @pytest.mark.asyncio
    async def test_concurrent_buffer_access(self):
        """Test that concurrent output writes don't corrupt buffer"""
        # Mock terminal with buffer and lock
        from api.terminal import TerminalWebSocket

        mock_websocket = AsyncMock()
        mock_redis = Mock()

        terminal = TerminalWebSocket(
            websocket=mock_websocket,
            session_id="test_session",
            conversation_id="test_conv",
            redis_client=mock_redis,
        )

        # #13284: passing conversation_id makes __init__ build a real
        # ChatHistoryManager, and every "Output i\n" contains a newline, so
        # _save_to_chat_buffered persists on all 100 writes. That is real chat
        # persistence, not buffer-race verification, and it measured 51.22s on
        # CI — the second-largest entry in the suite. Stub the save the same way
        # test_buffer_lock_prevents_interleaving below already does; the buffer
        # still resets through the same _output_lock path, so the assertion
        # underneath is unchanged.
        terminal.chat_history_manager.add_message = AsyncMock()
        # #13284: send_output also calls _log_to_transcript, which does a real
        # aiofiles append per write whenever conversation_id is set — 100 more
        # filesystem round-trips that have nothing to do with the buffer race.
        terminal._log_to_transcript = AsyncMock()

        # Simulate 100 concurrent output writes
        async def write_output(text: str):
            await terminal.send_output(text)

        tasks = [write_output(f"Output {i}\n") for i in range(100)]
        await asyncio.gather(*tasks)

        # Verify no corruption or data loss
        # Buffer should be empty after all saves complete
        assert terminal._output_buffer == "" or len(terminal._output_buffer) < 500

    @pytest.mark.asyncio
    async def test_buffer_lock_prevents_interleaving(self):
        """Test that lock prevents output interleaving"""
        from api.terminal import TerminalWebSocket

        mock_websocket = AsyncMock()
        mock_redis = Mock()

        terminal = TerminalWebSocket(
            websocket=mock_websocket,
            session_id="test_session",
            conversation_id="test_conv",
            redis_client=mock_redis,
        )

        # Track call order
        call_order = []

        async def slow_add_message(*args, **kwargs):
            call_order.append("start")
            await asyncio.sleep(0.01)  # Simulate slow save
            call_order.append("end")

        terminal.chat_history_manager.add_message = slow_add_message

        # Two concurrent writes
        await asyncio.gather(
            terminal.send_output("A" * 600),  # Triggers save
            terminal.send_output("B" * 600),  # Triggers save
        )

        # Verify no interleaving (should be: start, end, start, end)
        assert call_order.count("start") == call_order.count("end")


# Test Issue 2: File Write Atomicity
class TestFileWriteAtomicity:
    """Test atomic file write with locking"""

    @pytest.mark.asyncio
    async def test_atomic_write_creates_temp_file(self):
        """Test that atomic write uses temporary file"""
        from chat_history import ChatHistoryManager

        manager = ChatHistoryManager()
        await manager.initialize()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "test.json")
            content = '{"test": "data"}'

            await manager._atomic_write(target_file, content)

            # Verify target file exists and contains correct content
            assert os.path.exists(target_file)
            with open(target_file, "r", encoding="utf-8") as f:
                assert f.read() == content

            # Verify no temp files left behind
            temp_files = [f for f in os.listdir(tmpdir) if f.startswith(".tmp_chat_")]
            assert len(temp_files) == 0

    @pytest.mark.asyncio
    async def test_atomic_write_cleanup_on_failure(self):
        """Test that temp file is cleaned up on write failure"""
        from chat_history import ChatHistoryManager

        manager = ChatHistoryManager()
        await manager.initialize()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use invalid path to trigger failure
            invalid_file = os.path.join(tmpdir, "nonexistent_dir", "test.json")

            with pytest.raises(Exception):
                await manager._atomic_write(invalid_file, "test")

            # Verify no temp files left in tmpdir
            temp_files = [f for f in os.listdir(tmpdir) if f.startswith(".tmp_chat_")]
            assert len(temp_files) == 0

    @pytest.mark.asyncio
    async def test_concurrent_atomic_writes(self):
        """Test that concurrent atomic writes don't corrupt file"""
        from chat_history import ChatHistoryManager

        manager = ChatHistoryManager()
        await manager.initialize()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "concurrent.json")

            # Write 100 times concurrently
            async def write_data(i: int):
                content = json.dumps({"write": i, "timestamp": time.time()})
                await manager._atomic_write(target_file, content)

            await asyncio.gather(*[write_data(i) for i in range(100)])

            # Verify file is valid JSON (not corrupted)
            assert os.path.exists(target_file)
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)  # Should not raise JSONDecodeError
                assert "write" in data
                assert "timestamp" in data


# Test Issue 1: Chat Save Race
class TestChatSaveRace:
    """Test message merging to prevent save race conditions"""

    @pytest.mark.asyncio
    async def test_merge_preserves_backend_messages(self):
        """Test that merge preserves backend-added terminal messages"""
        from api.chat import merge_messages

        existing = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "Hello"},
            {"timestamp": "2025-01-01 10:00:01", "sender": "assistant", "text": "Hi"},
            {
                "timestamp": "2025-01-01 10:00:02",
                "sender": "terminal",
                "text": "ls output",
                "message_type": "terminal_output",
            },
        ]

        new = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "Hello"},
            {"timestamp": "2025-01-01 10:00:01", "sender": "assistant", "text": "Hi"},
            {
                "timestamp": "2025-01-01 10:00:03",
                "sender": "user",
                "text": "New message",
            },
        ]

        merged = await merge_messages(existing, new)

        # Verify terminal message is preserved
        assert len(merged) == 4  # 3 unique + 1 new
        terminal_msgs = [m for m in merged if m.get("sender") == "terminal"]
        assert len(terminal_msgs) == 1
        assert terminal_msgs[0]["text"] == "ls output"

    @pytest.mark.asyncio
    async def test_merge_deduplicates_messages(self):
        """Test that merge removes duplicate messages"""
        from api.chat import merge_messages

        existing = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "Message 1"},
            {"timestamp": "2025-01-01 10:00:01", "sender": "user", "text": "Message 2"},
        ]

        new = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "Message 1"},
            {"timestamp": "2025-01-01 10:00:01", "sender": "user", "text": "Message 2"},
            {"timestamp": "2025-01-01 10:00:02", "sender": "user", "text": "Message 3"},
        ]

        merged = await merge_messages(existing, new)

        # Should have 3 unique messages
        assert len(merged) == 3

    @pytest.mark.asyncio
    async def test_merge_sorts_by_timestamp(self):
        """Test that merged messages are sorted chronologically"""
        from api.chat import merge_messages

        existing = [
            {
                "timestamp": "2025-01-01 10:00:02",
                "sender": "terminal",
                "text": "Output",
            },
        ]

        new = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "First"},
            {"timestamp": "2025-01-01 10:00:03", "sender": "user", "text": "Last"},
        ]

        merged = await merge_messages(existing, new)

        # Verify chronological order
        assert merged[0]["timestamp"] == "2025-01-01 10:00:00"
        assert merged[1]["timestamp"] == "2025-01-01 10:00:02"
        assert merged[2]["timestamp"] == "2025-01-01 10:00:03"

    @pytest.mark.asyncio
    async def test_merge_handles_large_messages(self):
        """Test merge with large message lists (performance test)"""
        from api.chat import merge_messages

        # Create 1000 existing messages
        existing = [
            {
                "timestamp": f"2025-01-01 10:00:{i:02d}",
                "sender": "user",
                "text": f"Message {i}",
            }
            for i in range(1000)
        ]

        # Create 1000 new messages (500 duplicates, 500 new)
        new = [
            {
                "timestamp": f"2025-01-01 10:00:{i:02d}",
                "sender": "user",
                "text": f"Message {i}",
            }
            for i in range(500)
        ] + [
            {
                "timestamp": f"2025-01-01 11:00:{i:02d}",
                "sender": "user",
                "text": f"New {i}",
            }
            for i in range(500)
        ]

        start_time = time.time()
        merged = await merge_messages(existing, new)
        elapsed = time.time() - start_time

        # Verify correctness
        assert len(merged) == 1500  # 1000 unique + 500 new

        # Verify performance (<50ms for 2000 message merge)
        assert elapsed < 0.05, f"Merge took {elapsed:.3f}s, expected <0.05s"


# Test Integration: All Fixes Working Together
class TestIntegration:
    """Integration tests for all three fixes working together"""

    @pytest.mark.asyncio
    async def test_concurrent_terminal_and_save(self):
        """Test concurrent terminal output + chat save (real-world scenario)"""
        from api.chat import merge_messages

        # Simulate real scenario: terminal adding messages while frontend saves
        # Initial chat state
        existing = [
            {"timestamp": "2025-01-01 10:00:00", "sender": "user", "text": "ls"},
            {
                "timestamp": "2025-01-01 10:00:01",
                "sender": "assistant",
                "text": "Running ls",
            },
        ]

        # Frontend save request (doesn't include terminal output yet)
        new = existing.copy()

        # Simulate terminal output added during save
        existing.append(
            {
                "timestamp": "2025-01-01 10:00:02",
                "sender": "terminal",
                "text": "file1.txt\nfile2.txt",
            }
        )

        # Merge should preserve terminal output
        merged = await merge_messages(existing, new)

        terminal_msgs = [m for m in merged if m.get("sender") == "terminal"]
        assert len(terminal_msgs) == 1
        assert "file1.txt" in terminal_msgs[0]["text"]


# Performance Benchmarks
class TestPerformance:
    """Performance tests for overhead measurements"""

    @pytest.mark.asyncio
    async def test_terminal_lock_overhead(self):
        """Measure asyncio.Lock overhead in terminal buffer"""
        from api.terminal import TerminalWebSocket

        mock_websocket = AsyncMock()
        terminal = TerminalWebSocket(
            websocket=mock_websocket,
            session_id="perf_test",
        )

        # Measure 1000 buffer operations
        start = time.time()
        for i in range(1000):
            async with terminal._output_lock:
                terminal._output_buffer += f"test {i}\n"
        elapsed = time.time() - start

        # Should be <2ms per operation (requirement from plan)
        avg_per_op = elapsed / 1000
        assert avg_per_op < 0.002, f"Lock overhead {avg_per_op*1000:.2f}ms > 2ms"

    @pytest.mark.asyncio
    async def test_atomic_write_overhead(self):
        """Atomic write must not cost more than its own executor round-trips.

        #13162 replaced a fixed wall-clock budget with a ratio against a plain
        write, on the reasoning that load inflates both sides and cancels.
        #14691: it does not cancel, because the two sides are not the same
        shape. ``_atomic_write`` makes five executor round-trips (mkstemp,
        flock, replace, exists, unlink) plus one aiofiles write; a plain write
        makes one. Contention is paid per hand-off, so it lands on the atomic
        side five times and on the denominator once. The ratio therefore grows
        with load instead of holding steady, and a shard running twelve ways
        pushed it to 17.4x against a 15.0x bound while nothing about the write
        had changed.

        Modelling that: with the denominator making one round-trip, the median
        ratio ranged 2.4x-40x across load levels for identical code. With the
        denominator making the SAME number of round-trips, it ranged 0.43x-2.70x
        — because the contention now cancels for real.

        So the control below is structurally identical to ``_atomic_write``:
        the same number of executor round-trips, plus one aiofiles write. The
        count is measured from the implementation rather than hardcoded, so
        adding or removing a round-trip moves the control with it instead of
        silently changing what the assertion means.

        What still fails: a regression that adds *work* rather than a
        hand-off — a synchronous call, an fsync per chunk, a lost executor —
        moves the atomic side only, and the ratio moves with it.
        """
        from chat_history import ChatHistoryManager

        # Create manager BEFORE timing (exclude initialization overhead)
        manager = ChatHistoryManager()
        await manager.initialize()

        rounds = 15
        content = '{"test": "data"}' * 100  # ~1.5KB

        with tempfile.TemporaryDirectory() as tmpdir:
            probe_target = os.path.join(tmpdir, "probe.json")
            control_target = os.path.join(tmpdir, "control.json")
            atomic_target = os.path.join(tmpdir, "atomic.json")

            # Count the executor round-trips _atomic_write actually makes, by
            # wrapping the one seam every offload goes through.
            trips = 0
            original_executor = manager._run_in_io_executor

            async def counting_executor(func, *args, **kwargs):
                nonlocal trips
                trips += 1
                return await original_executor(func, *args, **kwargs)

            manager._run_in_io_executor = counting_executor
            try:
                await manager._atomic_write(probe_target, content)
            finally:
                manager._run_in_io_executor = original_executor

            assert trips > 0, (
                "no executor round-trips were observed — _atomic_write no longer "
                "offloads through _run_in_io_executor, so this control cannot "
                "mirror its shape and the comparison below is meaningless"
            )

            async def control_write():
                """The same hand-off count as _atomic_write, minimal work."""
                for _ in range(trips):
                    await manager._run_in_io_executor(os.path.exists, control_target)
                async with aiofiles.open(control_target, "w", encoding="utf-8") as handle:
                    await handle.write(content)

            # Warm both paths so first-time executor start-up is excluded
            await control_write()
            await manager._atomic_write(atomic_target, content)

            control_samples = []
            atomic_samples = []
            for _ in range(rounds):
                start = time.perf_counter()
                await control_write()
                control_samples.append(time.perf_counter() - start)

                start = time.perf_counter()
                await manager._atomic_write(atomic_target, content)
                atomic_samples.append(time.perf_counter() - start)

            # The atomic write must have produced the same content, not just
            # spent time — a fast write of nothing is not a passing result.
            with open(atomic_target, "r", encoding="utf-8") as fh:
                assert fh.read() == content

        control = statistics.median(control_samples)
        atomic = statistics.median(atomic_samples)

        # Both sides now make `trips` executor round-trips and one aiofiles
        # write, so the expected ratio is ~1.0 and the headroom absorbs the
        # real work _atomic_write does inside its hand-offs. Modelling put a
        # healthy ratio under 2.7x even at heavy contention; 4.0 leaves room
        # above that without leaving room for a newly added blocking call.
        max_overhead_ratio = 4.0
        assert atomic <= control * max_overhead_ratio, (
            f"Atomic write {atomic*1000:.2f}ms is {atomic / control:.1f}x a "
            f"structurally identical control ({control*1000:.2f}ms, "
            f"{trips} executor round-trips each), limit {max_overhead_ratio}x. "
            f"Both sides pay the same contention, so this is work, not load."
        )


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
