# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15637: the observability write helper must retain its task and say so.

``run_redis_write`` carries audit-log, JWT-revocation and event-log writes. It
used to schedule them with a bare ``asyncio.get_running_loop().create_task()``
and throw the handle away, so the loop's weak reference was the only thing
holding the task and it could be collected mid-flight (#15522) — a missing
audit record, under load, non-deterministically. The failure path logged at
``debug``, so a lost record produced no warning and no visible gap.

It lived in ``autobot_shared/fire_and_forget.py``, next to the CORRECT retaining
helper in ``autobot_shared/async_compat.py``. The obvious name held the weaker
implementation and collected twice the consumers; the module is now named for
the one thing it provides.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging

from autobot_shared.async_compat import pending_background_tasks
from autobot_shared.redis_write import run_redis_write


class TestRetention:
    async def test_the_write_is_retained_until_it_completes(self) -> None:
        """The #15522 shape: nothing but this registry holds the task."""
        release = asyncio.Event()
        written: list[str] = []

        async def write() -> None:
            await release.wait()
            written.append("record")

        before = pending_background_tasks()
        run_redis_write(write(), label="audit-probe")
        launched = pending_background_tasks() - before

        assert len(launched) == 1, (
            "run_redis_write did not retain its task — a discarded handle can be garbage-collected "
            "before the write lands"
        )
        task = next(iter(launched))
        assert "audit-probe" in task.get_name()

        release.set()
        await task
        assert written == ["record"]
        await asyncio.sleep(0)
        assert task not in pending_background_tasks(), "the done callback never released the reference"

    async def test_the_caller_is_never_made_to_handle_the_failure(self) -> None:
        """An observability write must not break the path it hangs off."""

        async def explodes() -> None:
            raise RuntimeError("redis unreachable")

        run_redis_write(explodes(), label="audit-probe-raises")
        await asyncio.sleep(0.05)


class TestFailureVisibility:
    async def test_a_lost_write_is_not_a_debug_level_event(self, caplog) -> None:
        """The old wrapper logged at DEBUG, so nothing ever surfaced."""

        async def explodes() -> None:
            raise RuntimeError("redis unreachable")

        with caplog.at_level(logging.ERROR):
            run_redis_write(explodes(), label="audit-probe-visible")
            for _ in range(200):
                await asyncio.sleep(0.01)
                if caplog.records:
                    break

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "audit-probe-visible" in logged, f"the failing write was not named at ERROR: {logged!r}"
        assert "redis unreachable" in logged, f"the exception was swallowed: {logged!r}"

    def test_no_running_loop_is_reported_and_the_coroutine_is_closed(self, caplog) -> None:
        """The RuntimeError branch is correct and stays: it closes the coroutine."""
        ran: list[str] = []

        async def write() -> None:
            ran.append("record")

        coro = write()
        with caplog.at_level(logging.WARNING):
            run_redis_write(coro, label="audit-probe-no-loop")

        assert ran == []
        assert coro.cr_frame is None, "the coroutine was not closed — it will warn 'never awaited'"
        assert "audit-probe-no-loop" in "\n".join(record.getMessage() for record in caplog.records)


class TestTheNamingCollisionIsResolved:
    def test_the_module_that_lied_about_its_contents_is_gone(self) -> None:
        """``autobot_shared.fire_and_forget`` held the NON-retaining launcher.

        Two helpers, and the obvious name pointed at the weaker one with more
        than twice the consumers. Anyone reaching for the obvious import got it.
        """
        assert importlib.util.find_spec("autobot_shared.fire_and_forget") is None, (
            "autobot_shared/fire_and_forget.py is back. The canonical retaining launcher is "
            "autobot_shared.async_compat.fire_and_forget; this module is the Redis-write helper "
            "that delegates to it (#15637)."
        )

    def test_the_canonical_launcher_is_importable_under_its_own_name(self) -> None:
        assert importlib.util.find_spec("autobot_shared.async_compat") is not None
        assert importlib.util.find_spec("autobot_shared.redis_write") is not None
