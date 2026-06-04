# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Cross-worker coordination primitives — Issue #6630."""

from .shared_runtime_bag import ChangeEvent, SharedRuntimeBag

__all__ = ["SharedRuntimeBag", "ChangeEvent"]
