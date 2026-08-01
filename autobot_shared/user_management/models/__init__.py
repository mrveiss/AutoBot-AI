# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical user_management declarative base (#12647).

Home for the new declarative base that reconciles the backend/SLM
``models/base.py`` fork per the owner's 2026-07-31 decision on #12645/#12647:
design a new canonical base that deliberately preserves both sides'
properties, rather than adopting either fork wholesale. See ``base.py`` for
the property-by-property rationale.
"""

from autobot_shared.user_management.models.base import (  # noqa: F401
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "TenantMixin",
    "SoftDeleteMixin",
]
