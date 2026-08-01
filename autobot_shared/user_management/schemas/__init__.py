# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical user_management Pydantic schemas shared by both backends (#12647).

Second move after `base_service` (#12972): `schemas/user.py` was identical in
both backends except for Pydantic v1/v2 config style (`class Config` vs
`model_config = ConfigDict(...)`) — no SQLAlchemy dependency, so it does not
need the declarative-base decision that gates the model files.
"""

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
    "RoleResponse",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserListResponse",
    "UserLogin",
    "PasswordChange",
]
