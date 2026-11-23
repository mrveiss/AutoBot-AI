# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models of the assign-company route (#21997)."""

import uuid

from pydantic import BaseModel


class SessionCompanyAssign(BaseModel):
    """Body of ``POST /chat/sessions/{session_id}/company``."""

    company_id: uuid.UUID


class SessionCompanyAssignData(BaseModel):
    """data payload of ``POST /chat/sessions/{session_id}/company``."""

    session_id: str
    company_id: str
