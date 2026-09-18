# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for POST /admin/resource-grants/repair (``api/admin_resource_grants.py``).

Moved here unchanged from the router, where they were local definitions: the
no-local-schemas hook (#6056) rejects a router file that defines its own
``BaseModel``, and every existing domain schemas module this could join is frozen
at its size ceiling, so it is a companion ``schemas_<domain>_<topic>.py`` (#16178).
"""

from pydantic import BaseModel, Field


class RepairGrantRequest(BaseModel):
    resource_type: str = Field(..., min_length=1, max_length=32)
    resource_id: str = Field(..., min_length=1, max_length=255)
    grantee_type: str = Field(..., pattern="^(user|group)$")
    grantee_id: str = Field(..., min_length=1, max_length=255)
    permission: str = Field(default="use", pattern="^(view|use|manage)$")


class RepairGrantResponse(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    grantee_type: str
    grantee_id: str
    permission: str
