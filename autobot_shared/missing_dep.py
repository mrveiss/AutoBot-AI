# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared sentinel for optional dependencies that are not installed.

Issue #6264: Centralise the _MissingDep pattern so every module that has an
optional import raises a clear ImportError instead of a misleading TypeError
or AttributeError when the missing symbol is accidentally called.

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
    """

    def __init__(self, name: str, error: Exception) -> None:
        self._name = name
        self._error = error

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
