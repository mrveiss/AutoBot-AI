# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request body of the one share route, ``/api/knowledge/collaboration/facts/{id}/share`` (#18795).

Carries the limits of the retired ``ShareFactRequest``: at most 50 ids per list, each 1-100
characters, and at least one id across ``user_ids`` and ``group_ids``. Re-exported from
``api.schemas_knowledge``, which is where callers import it.
"""

from typing import Annotated, List

from pydantic import BaseModel, Field, StringConstraints, model_validator

MAX_SHARE_IDS = 50
ShareId = Annotated[str, StringConstraints(min_length=1, max_length=100)]


class ShareKnowledgeRequest(BaseModel):
    """Request to share knowledge with users or groups."""

    user_ids: List[ShareId] | None = Field(default=None, max_length=MAX_SHARE_IDS, description="User IDs to share with")
    group_ids: List[ShareId] | None = Field(
        default=None, max_length=MAX_SHARE_IDS, description="Group IDs to share with"
    )

    @model_validator(mode="after")
    def require_one_id(self):
        """At least one id across user_ids and group_ids."""
        if not (self.user_ids or self.group_ids):
            raise ValueError("At least one user_id or group_id is required")
        return self
