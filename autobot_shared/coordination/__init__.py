# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-worker coordination primitives — Issues #6630, #15947, #15948."""

from .claim_waitlist import Waiter, arbitrate
from .shared_runtime_bag import ChangeEvent, SharedRuntimeBag
from .work_claims import (
    Claim,
    ClaimConflict,
    ClaimConflictError,
    ClaimMode,
    ClaimUnavailable,
    HolderError,
    Scope,
    ScopeError,
    list_claims,
    release,
    renew,
    try_acquire,
    work_claim,
)

__all__ = [
    "SharedRuntimeBag",
    "ChangeEvent",
    "Waiter",
    "arbitrate",
    "Claim",
    "ClaimConflict",
    "ClaimConflictError",
    "ClaimMode",
    "ClaimUnavailable",
    "HolderError",
    "Scope",
    "ScopeError",
    "list_claims",
    "release",
    "renew",
    "try_acquire",
    "work_claim",
]
