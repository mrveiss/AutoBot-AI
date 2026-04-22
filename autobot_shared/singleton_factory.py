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

    Raises RuntimeError if called again with different args than the first
    call, to prevent silent mis-configuration.
    """
    instance: Optional[T] = None
    lock = Lock()
    _first_args: Optional[tuple] = None
    _first_kwargs: Optional[dict] = None

    def get(*args, **kwargs) -> T:
        nonlocal instance, _first_args, _first_kwargs
        if instance is None:
            with lock:
                if instance is None:
                    instance = factory(*args, **kwargs)
                    _first_args = args
                    _first_kwargs = dict(kwargs)
        elif args or kwargs:
            if args != _first_args or kwargs != _first_kwargs:
                raise RuntimeError(
                    f"lazy_singleton: called with different args after first construction. "
                    f"First: args={_first_args!r}, kwargs={_first_kwargs!r}. "
                    f"Now: args={args!r}, kwargs={kwargs!r}."
                )
        return instance

    return get
