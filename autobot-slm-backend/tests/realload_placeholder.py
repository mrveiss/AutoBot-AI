# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Placeholder for a listed service module that could not be real-loaded (#15563).

``autobot-slm-backend/conftest.py`` eagerly real-loads every name in
``_REAL_SERVICE_MODULES``. When a third-party dependency one of them needs is
absent from the environment that load raises ``ImportError``, and the conftest
has to leave *something* behind.

A MagicMock is not it (#14307): a MagicMock is truthy and iterates empty, so a
missing dependency becomes a silently wrong result instead of an error.

Deleting the name is not it either, which is what #15563 is about. ``services``
is itself a ``MagicMock(unsafe=True)`` for most of the suite and fabricates any
attribute on demand, so a deleted ``services.x`` reached through the parent —
``patch("services.x.y")``, ``getattr(services, "x")`` — comes back as an
auto-created mock: absence is indistinguishable from the stub #14307 removed.
Where the parent has been swapped for a real-path package
(``tests/services/conftest.py``), the same deletion degrades into::

    AttributeError: module 'services' has no attribute 'hf_token_validator'.
    Did you mean: 'hf_token_validator_test'?

which names the stub package and points the reader at the co-located test file
instead of at the dependency that is actually missing. Two independent
investigations read that hint and reached the wrong cause.

The placeholder below is the third option: a genuine module object that raises
``ImportError`` naming both the module and the cause on any attribute access,
so ``from services.x import y``, ``patch("services.x.y")`` and
``getattr(services, "x").y`` all report the missing dependency. Dunder names
fall through to ``AttributeError`` so introspection (``inspect``, pytest
collection, ``getattr(mod, "__file__", None)``) behaves normally — which is
also what keeps ``tests/test_real_service_modules_14307.py`` able to tell a
placeholder apart from the real module.

The contract is asserted in ``tests/test_realload_unavailable_contract_15563.py``.
"""

from __future__ import annotations

from types import ModuleType


def unavailable_module(module_name: str, cause: BaseException) -> ModuleType:
    """Return a module object whose every attribute access raises ``ImportError``.

    The message names *module_name* and *cause* together, and ``cause`` is
    chained, so the traceback carries the original failure verbatim.
    """
    message = (
        f"{module_name} is listed for real-loading but could not be imported in this "
        f"environment: {type(cause).__name__}: {cause}. Install the dependency it names, "
        "or do not reach for this module from a test that runs here."
    )

    module = ModuleType(module_name)
    module.__doc__ = message
    module.__spec__ = None  # type: ignore[assignment]
    module.__package__ = module_name.rpartition(".")[0]

    def __getattr__(attribute: str) -> object:
        # Dunders stay AttributeError: introspection must not explode on a
        # placeholder, and `getattr(mod, "__file__", None)` has to answer None
        # so the #14307 guard can still see this is not the real module.
        if attribute.startswith("__") and attribute.endswith("__"):
            raise AttributeError(attribute)
        raise ImportError(message, name=module_name) from cause

    module.__getattr__ = __getattr__  # type: ignore[attr-defined]  -- PEP 562
    return module
