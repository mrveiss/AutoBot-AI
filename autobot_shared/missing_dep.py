# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared sentinel for optional dependencies that are not installed.

Issue #6264: Centralise the _MissingDep pattern so every module that has an
optional import raises a clear ImportError instead of a misleading TypeError
or AttributeError when the missing symbol is accidentally called.

Issue #6297: Add __bool__ and __eq__ so the sentinel is falsy and compares
equal to None, allowing `if not dep:` and `dep is None` guards to work
correctly without per-file workaround flags.

Usage::

    from autobot_shared.missing_dep import MissingDep as _MissingDep

    try:
        import some_optional_lib
    except ImportError as e:
        some_optional_lib = _MissingDep("some_optional_lib", e)
"""

from typing import NoReturn


class MissingDep:
    """Sentinel for optional dependencies that are not installed.

    Raises a clear ImportError (instead of a misleading TypeError) when the
    missing symbol is called or attribute-accessed at runtime.

    The sentinel is falsy (``bool(dep) == False``) and compares equal to
    ``None`` so callers can use ``if not dep:`` or ``dep is None`` guards
    interchangeably.
    """

    __hash__ = object.__hash__  # retain identity-based hashing alongside __eq__

    def __init__(self, name: str, error: Exception) -> None:
        self._name = name
        self._error = error

    def __repr__(self) -> str:
        return f"MissingDep({self._name!r})"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, MissingDep)

    def __call__(self, *args: object, **kwargs: object) -> NoReturn:
        raise ImportError(
            f"{self._name} is not available — install the optional dependencies "
            f"(original error: {self._error})"
        )

    def __getattr__(self, item: str) -> NoReturn:
        raise ImportError(
            f"{self._name} is not available — install the optional dependencies "
            f"(original error: {self._error})"
        )
