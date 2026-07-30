# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file was identical in both backends apart from Pydantic v1/v2 config
style (`class Config` vs `model_config = ConfigDict(...)`), so it carries no
SQLAlchemy dependency and does not need the declarative-base decision that
gates the model files. Kept as a shim rather than deleted so existing
importers keep working unchanged; the fork is what goes, not the callers.
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
