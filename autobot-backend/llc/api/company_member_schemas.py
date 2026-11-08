# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response shape of ``GET /companies/{company_id}/members`` (#21096).

The caller's standing (:func:`llc.services.member_standing.viewer_standing`) rides once on the envelope,
not on each row, so a company with no member rows still carries the server's verdict.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CompanyMemberRow(BaseModel):
    """One person in the members list."""

    id: str
    company_id: str
    user_id: str
    role: str
    created_at: Optional[str] = None
    display_name: str
    is_active: bool


class CompanyMembersResponse(BaseModel):
    """The members and the caller's own standing, which does not depend on there being any."""

    members: List[CompanyMemberRow]
    viewer_role: Optional[str] = None
    viewer_can_manage: bool
    viewer_grantable_roles: List[str]
