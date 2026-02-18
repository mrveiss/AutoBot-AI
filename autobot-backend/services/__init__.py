# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend Services Module

This module contains all service layer components for the AutoBot backend,
including AI Stack integration, database connections, and external service clients.

Issue #640: Added NPU worker client for compute offload.
"""

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
