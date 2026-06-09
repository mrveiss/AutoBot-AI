# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared sentinel for optional dependencies that are not installed.

Issue #6264: Centralise the _MissingDep pattern so every module that has an
optional import raises a clear ImportError instead of a misleading TypeError
or AttributeError when the missing symbol is accidentally called.

Issue #6297: Add __bool__ and __eq__ so the sentinel is falsy and compares
equal to None, allowing `if not dep:` and `dep is None` guards to work
correctly without per-file workaround flags.

Issue #6691: Add ``optional_import(module, names)`` helper to collapse the
verbose ``try: from X import a, b, c; except ImportError: ...`` block —
3-7 lines of repetition per call site — into a single call.

Usage::

    # Single-symbol shape (still supported, sometimes preferable for type
    # hints since the local name retains its original module's type):
    from autobot_shared.missing_dep import MissingDep as _MissingDep
    try:
        import some_optional_lib
    except ImportError as e:
        some_optional_lib = _MissingDep("some_optional_lib", e)

    # Multi-symbol shape (#6691) — expanded into module globals:
    from autobot_shared.missing_dep import optional_import
    globals().update(optional_import("log_forwarder", ["start", "stop", "Forwarder"]))
"""

import importlib
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

        Without the dunder short-circuit, ``missing_dep_instance | None``
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
        """Support ``MissingDep_instance | None`` and similar generic-like
        subscripting at module-load time without raising.

        #6794: previously every caller had to remember to use string forward-
        references (``\"Stub | None\"``) to prevent the type expression from
        crashing the module at import time. The sentinel now no-ops on
        subscript so ``stub | None`` evaluates safely; the actual point of
        failure stays at runtime call / non-dunder attribute access.
        """
        return self


def optional_import(module_name: str, names: list[str]) -> dict[str, object]:
    """Resolve ``names`` from ``module_name``; return ``MissingDep`` stubs on ImportError.

    Collapses the 5-line ``try: from X import a, b; except: a = MissingDep(...);
    b = MissingDep(...)`` boilerplate into a single call. Every name is wired
    consistently so a partial-import failure (e.g. one name missing from a
    real module) doesn't leave callers with inconsistent ``MissingDep``-vs-real
    mixing — when ImportError fires for the *module*, **all** names become
    sentinels.

    Args:
        module_name: dotted import path, e.g. ``"autobot_backend.log_forwarder"``.
        names: symbol names to pull from the module.

    Returns:
        ``{name: real_attribute}`` on success, ``{name: MissingDep(name, err)}``
        on ImportError. Use with ``globals().update(...)`` at module top-level
        to expand into local namespace.

    Example:
        >>> # Equivalent to a 6-line try/except block:
        >>> globals().update(optional_import(
        ...     "autobot_backend.log_forwarder",
        ...     ["start_forwarder", "stop_forwarder", "ForwarderStatus"],
        ... ))

    Raises:
        AttributeError: if the module imports successfully but is missing one
            of ``names``. This is **not** caught — a missing symbol after a
            successful module import is a real bug, not an optional-dep gap.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        return {name: MissingDep(name, e) for name in names}
    return {name: getattr(module, name) for name in names}
