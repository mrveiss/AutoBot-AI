# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-test time bound for async tests (#20862).

``pytest-timeout`` is not a test dependency, so a test that can block on a lease
or a lock bounds itself: each coroutine test is run under ``asyncio.wait_for``,
which cancels it and fails with ``TimeoutError`` instead of hanging the suite.
"""

import asyncio
import functools
import inspect

DEFAULT_TEST_TIMEOUT_S = 60


def bound_async_tests(namespace: dict, seconds: float = DEFAULT_TEST_TIMEOUT_S) -> None:
    """Wrap every ``test_*`` coroutine function in ``namespace`` with a time bound.

    Call once at the bottom of a test module: ``bound_async_tests(globals())``.
    """
    for name, fn in list(namespace.items()):
        if name.startswith("test_") and inspect.iscoroutinefunction(fn):
            namespace[name] = _bounded(fn, seconds)


def _bounded(fn, seconds: float):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        return await asyncio.wait_for(fn(*args, **kwargs), seconds)

    return wrapper
