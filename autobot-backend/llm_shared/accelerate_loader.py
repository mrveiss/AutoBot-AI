# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared thread-safe lazy accelerate loader (#13049 C4).

``_import_accelerate()`` was defined twice in ``llm_shared/optimization/`` --
``meta_eviction.py`` and ``model_inspector.py`` -- same package, same optional
dependency, and already drifted: one caught ``(ImportError, RuntimeError)`` and
re-raised both as ``ImportError``, the other caught ``ImportError`` alone. This
is the same class of fork #12714 closed for the nine ``_get_torch()`` copies;
the accelerate loader was missed by that round.

Each call site keeps its own wording through ``error_message`` -- the message a
reader gets still names what they were trying to do -- while the caching,
locking and raise policy are defined once in :mod:`llm_shared.lazy_import`.
"""

from __future__ import annotations

from typing import Any, Optional

from .lazy_import import LazyModule

_ACCELERATE = LazyModule("accelerate")


def lazy_accelerate(required: bool = True, error_message: Optional[str] = None) -> Any:
    """Return the accelerate module, importing it on first call (thread-safe).

    Args:
        required: if True (default), a missing accelerate raises ``ImportError``
            (or the original exception, re-raised). If False, returns ``None``.
        error_message: overrides the message when accelerate is genuinely
            ABSENT, so each call site can say what it needed accelerate for.
            Ignored when the failure was a ``RuntimeError`` -- accelerate is
            installed, and "pip install accelerate" would be wrong advice.

    Returns:
        The imported ``accelerate`` module, or ``None`` when ``required=False``
        and it could not be imported.
    """
    return _ACCELERATE.load(required=required, error_message=error_message)
