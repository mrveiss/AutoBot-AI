# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wait on an observable, not on the clock (#16009).

A test that sleeps a fixed interval and then counts what happened is a claim
about how much wall clock a shared runner grants a coroutine: a busy runner
produces exactly the count a broken loop produces, so the red cannot say which
one it saw. Waiting on the condition makes a slow runner merely slower, and
keeps the timeout as what it should be -- a deadlock guard far above the
expected time, not a budget the test has to fit inside.
"""

import asyncio
from typing import Callable, Optional

#: A deadlock guard, not a budget: at least an order of magnitude above any
#: wait it is used for, so reaching it means "never happened", not "slow box".
DEFAULT_DEADLINE_S = 30.0
_POLL_S = 0.01


async def eventually(
    condition: Callable[[], object],
    *,
    deadline: float = DEFAULT_DEADLINE_S,
    watch: Optional[asyncio.Task] = None,
) -> None:
    """Return once *condition()* is truthy; raise if *watch* ends first or *deadline* passes.

    *watch* is the task under test. If it finishes before the condition holds,
    its own exception is re-raised -- or an AssertionError if it returned -- so
    a loop that died reports why, instead of waiting out the deadline.
    """

    async def _poll() -> None:
        while not condition():
            if watch is not None and watch.done():
                watch.result()
                raise AssertionError("the watched task finished before the condition held")
            await asyncio.sleep(_POLL_S)

    await asyncio.wait_for(_poll(), timeout=deadline)
