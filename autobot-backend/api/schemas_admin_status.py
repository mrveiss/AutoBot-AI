# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for the platform-admin status route (#20670)."""

import uuid

from pydantic import BaseModel


class AdminStatusRequest(BaseModel):
    """The admin status to set."""

    is_platform_admin: bool


class AdminStatusResponse(BaseModel):
    """The admin status now in force, and whether this request changed it."""

    user_id: uuid.UUID
    is_platform_admin: bool
    changed: bool
