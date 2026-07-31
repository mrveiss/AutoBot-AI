# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical user_management core shared by both backends (#12647).

`user_management` is forked across `autobot-backend` and `autobot-slm-backend`,
with 19 shared-but-divergent `.py` source files. This package is the
consolidation target: files land here once their drift is either non-existent
or reconciled, so each move carries no semantic loss.

Movers so far:
- `base_service` (#12972) — byte-identical, no backend-specific imports.
- `schemas.user` (#12647) — identical apart from Pydantic v1/v2 config style;
  no SQLAlchemy dependency, so it does not need the declarative-base decision
  gating the model files.
- `models.base` (#12647) — the declarative base itself, resolving the
  backend/SLM design fork per the owner's 2026-07-31 decision: a new
  canonical base preserving both sides' properties (AsyncAttrs +
  eager_defaults from backend; postgresql.UUID typing from SLM), not an
  adoption of either fork.

Each fork keeps a re-export shim so existing importers are untouched — the
fork is removed, not the callers.
"""

from autobot_shared.user_management.base_service import (  # noqa: F401
    BaseService,
    TenantContext,
)
from autobot_shared.user_management.models.base import (  # noqa: F401
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from autobot_shared.user_management.schemas.user import (  # noqa: F401
    PasswordChange,
    RoleResponse,
    UserCreate,
    UserListResponse,
    UserLogin,
    UserResponse,
    UserUpdate,
)

__all__ = [
    "BaseService",
    "TenantContext",
    "Base",
    "TimestampMixin",
    "TenantMixin",
    "SoftDeleteMixin",
    "RoleResponse",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserListResponse",
    "UserLogin",
    "PasswordChange",
]
