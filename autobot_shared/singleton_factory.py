# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Thread-safe lazy singleton factory primitive.

Issue #5423: extracted from the repeated double-checked locking pattern in
``utils/semantic_chunker*.py``.  Third-occurrence rule triggered extraction.
"""

from threading import Lock
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


def lazy_singleton(factory: Callable[..., T]) -> Callable[..., T]:
    """Return a factory that creates and caches a thread-safe singleton.

    Uses double-checked locking so the common (already-initialised) path
    never acquires the lock.
    """
    instance: Optional[T] = None
    lock = Lock()

    def get(*args, **kwargs) -> T:
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = factory(*args, **kwargs)
        return instance

    return get
