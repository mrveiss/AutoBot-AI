# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for rolling back to an earlier commit (#20214)."""

from typing import List

from pydantic import BaseModel, Field


class RollbackRequest(BaseModel):
    """The commit the operator picked from the list; validated again server-side."""

    commit: str = Field(..., max_length=200, description="Full commit id from the candidates list")


class RollbackCommit(BaseModel):
    """One commit the operator may roll back to."""

    commit: str
    short: str
    date: str
    subject: str
    is_deployed: bool = False


class RollbackCandidates(BaseModel):
    """The picker's contents: ancestors of the branch head, newest first."""

    branch: str
    deployed_commit: str | None = None
    commits: List[RollbackCommit]


class RollbackDatabaseCheck(BaseModel):
    """Whether a database migration is in the way, for one database."""

    database: str
    status: str  # clear | blocked | unknown
    in_the_way: List[str] = []
    message: str = ""


class RollbackPreview(BaseModel):
    """What the confirmation step shows before anything runs."""

    commit: RollbackCommit
    allowed: bool
    refusal: str | None = None
    checks: List[RollbackDatabaseCheck]
