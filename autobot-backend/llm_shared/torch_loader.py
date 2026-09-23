# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared thread-safe lazy torch loader — Issue #12714 (round-3 of #12645).

A lazy ``import torch`` singleton was reimplemented across 9 modules
(``ai_hardware_accelerator``, the 4 ``llm_shared/optimization`` kernels,
``multimodal_processor`` + its ``vision``/``voice`` processors, and
``services/incremental_trainer``). Only one — ``optimization/flash_attention``
— used double-checked locking; the other 8 raced two threads past the
``if _torch is None`` check and could both attempt the import concurrently.

This module extracts that thread-safe pattern once. Torch is a heavy optional
dependency (NPU/GPU subsystem is feature-flagged, and many hosts — including
the startup-import-smoke CI job — run without it installed), so ``torch`` is
imported lazily inside :func:`lazy_torch`, never at module import time.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

_torch: Any = None
_torch_error: Optional[Exception] = None
_torch_lock = threading.Lock()


def lazy_torch(required: bool = True, error_message: Optional[str] = None) -> Any:
    """Return the torch module, importing it on first call (thread-safe).

    The result (module or import failure) is cached process-wide after the
    first attempt, so repeated calls are cheap regardless of which caller
    made the first one.

    Args:
        required: if True (default), a missing/broken torch install raises
            ``ImportError`` (or the originally raised exception, re-raised).
            If False, returns ``None`` instead.
        error_message: overrides the raised message when ``required=True``
            and torch is unavailable due to ``ImportError`` (matches each
            call site's original wording). Ignored when torch is available,
            or when the underlying failure was a ``RuntimeError`` (torch
            present but failed to initialize) — that is always re-raised
            unchanged, matching every original per-site implementation.

    Returns:
        The imported ``torch`` module, or ``None`` when ``required=False``
        and torch could not be imported.
    """
    global _torch, _torch_error  # noqa: PLW0603
    if _torch is None and _torch_error is None:
        with _torch_lock:
            if _torch is None and _torch_error is None:
                try:
                    import torch as _t  # noqa: PLC0415
                except (ImportError, RuntimeError) as exc:
                    _torch_error = exc
                else:
                    _torch = _t
    if _torch is None and required:
        if error_message and isinstance(_torch_error, ImportError):
            raise ImportError(error_message) from _torch_error
        raise _torch_error  # noqa: B904 - re-raising the cached original
    return _torch
