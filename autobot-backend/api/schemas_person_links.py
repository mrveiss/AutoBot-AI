# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for GET /admin/person-links/push-failures (#10200)."""

from datetime import datetime
from typing import List

from pydantic import BaseModel


class PersonPushFailure(BaseModel):
    """A linked person whose copy in the SLM could not be updated."""

    username: str
    failed_since: datetime
    error: str | None


class PersonPushFailuresResponse(BaseModel):
    failures: List[PersonPushFailure]
