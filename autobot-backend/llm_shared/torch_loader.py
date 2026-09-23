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

from typing import Any, Optional

from .lazy_import import LazyModule

#: #13049 C4: the caching and double-checked locking that used to live here now
#: live in ``lazy_import.LazyModule``, so the accelerate loader could reuse them
#: instead of becoming a third copy. Behaviour and signature are unchanged --
#: including that a ``RuntimeError`` (torch present but failed to initialise) is
#: re-raised unchanged while ``error_message`` applies only to a genuine
#: ``ImportError``. That rule originated here; it is now stated once.
_TORCH = LazyModule("torch")


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
    return _TORCH.load(required=required, error_message=error_message)
