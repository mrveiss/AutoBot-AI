# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AIDocument data model for persistent, editable AI output documents (#3245).

An AIDocument is a KB-grounded AI response promoted to a named, editable
document so users can iteratively refine it in-place.  Documents are stored
under the ``main`` Redis database (non-volatile user data) with a key prefix
of ``autobot:ai_document:{document_id}``.  An index set at
``autobot:ai_documents:index`` tracks all live document IDs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


class AIDocument(BaseModel):
    """Persistent editable document produced from a KB-grounded AI response.

    Fields mirror the schema described in issue #3245 plus a ``user_id``
    owner field required for per-user access control.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="")
    source_facts: List[str] = Field(
        default_factory=list,
        description="KB fact IDs that grounded the original AI response",
    )
    source_session_id: str | None = Field(
        default=None,
        description="Chat session ID where this document was created",
    )
    source_message_id: str | None = Field(
        default=None,
        description="Chat message ID from which the document was created",
    )
    user_id: str = Field(..., description="Owning user's ID from the JWT")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    # ------------------------------------------------------------------ #
    # Redis serialisation helpers
    # ------------------------------------------------------------------ #

    def redis_key(self) -> str:
        """Redis hash key for this document."""
        return f"autobot:ai_document:{self.id}"

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp in-place."""
        self.updated_at = _utcnow_iso()
