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
            f"{self._name} is not available — install the optional dependencies " f"(original error: {self._error})"
        )

    def __getattr__(self, item: str) -> object:
        """Raise ImportError on real attribute access — but stay silent for
        dunder attributes the Python ``typing`` module probes during type
        expression evaluation (#6794).

        Without the dunder short-circuit, ``Optional[missing_dep_instance]``
        triggers ``hasattr(t, '__typing_subst__')`` which fires this method
        and crashes module load.
        """
        # typing.Union / typing.Optional probe these dunders; absence is
        # signalled by AttributeError, not ImportError.
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        raise ImportError(
            f"{self._name} is not available — install the optional dependencies " f"(original error: {self._error})"
        )

    def __getitem__(self, _params: object) -> "MissingDep":
        """Support ``Optional[MissingDep_instance]`` and similar generic-like
        subscripting at module-load time without raising.

        #6794: previously every caller had to remember to use string forward-
        references (``\"Optional[Stub]\"``) to prevent the type expression from
        crashing the module at import time. The sentinel now no-ops on
        subscript so ``Optional[stub]`` evaluates safely; the actual point of
        failure stays at runtime call / non-dunder attribute access.
        """
        return self
