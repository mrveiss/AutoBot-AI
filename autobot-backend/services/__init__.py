# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backend Services Module

This module contains all service layer components for the AutoBot backend,
including AI Stack integration, database connections, and external service clients.

Issue #640: Added NPU worker client for compute offload.

Issue #12830: re-exports are resolved lazily (PEP 562). Importing them eagerly
made `import services.<anything>` drag in `ai_stack_client` -> `aiohttp` and
`npu_client` -> its Redis chain, forcing an HTTP transport dependency on every
importer whether or not it touches HTTP. Since this package sits under
`secure_command_executor` / `auth_middleware`, that reached almost the whole
backend. Same defect class as #12814, at a more central location.

The public surface is unchanged: every name in `__all__` still resolves on
attribute access, just on first use rather than at import time.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only for type checkers
    from .ai_stack_client import (
        AIStackClient,
        AIStackError,
        close_ai_stack_client,
        get_ai_stack_client,
    )
    from .npu_client import (
        EmbeddingResult,
        NPUClient,
        NPUDeviceInfo,
        cleanup_npu_client,
        generate_embedding_with_fallback,
        generate_embeddings_batch_with_fallback,
        get_npu_client,
    )

# Public name -> submodule that defines it.
_LAZY_EXPORTS = {
    "AIStackClient": "ai_stack_client",
    "AIStackError": "ai_stack_client",
    "get_ai_stack_client": "ai_stack_client",
    "close_ai_stack_client": "ai_stack_client",
    "NPUClient": "npu_client",
    "NPUDeviceInfo": "npu_client",
    "EmbeddingResult": "npu_client",
    "get_npu_client": "npu_client",
    "cleanup_npu_client": "npu_client",
    "generate_embedding_with_fallback": "npu_client",
    "generate_embeddings_batch_with_fallback": "npu_client",
}


def __getattr__(name: str):
    """Resolve a re-export on first access (PEP 562, #12830)."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value  # cache so later lookups skip __getattr__
    return value


def __dir__():
    """Keep tab-completion and dir() showing the full public surface."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    # AI Stack
    "AIStackClient",
    "AIStackError",
    "get_ai_stack_client",
    "close_ai_stack_client",
    # NPU Worker (Issue #640)
    "NPUClient",
    "NPUDeviceInfo",
    "EmbeddingResult",
    "get_npu_client",
    "cleanup_npu_client",
    "generate_embedding_with_fallback",
    "generate_embeddings_batch_with_fallback",
]
