# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Config Revision Model (#1404)

SQLAlchemy model for configuration audit trail with versioning and rollback.
Stores before/after snapshots for every configuration change.
"""

import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Uuid

from user_management.models.base import Base


class ConfigRevision(Base):
    """One recorded configuration change with before/after snapshots (#1404).

    Secret values are redacted before storage to prevent credential leakage.
    """

    __tablename__ = "config_revisions"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # What kind of entity changed: "agent", "system", "llm", etc.
    entity_type = Column(String(100), nullable=False, index=True)
    # Identifier of the specific entity instance.
    entity_id = Column(String(255), nullable=False, index=True)
    # Full configuration snapshot before the change (secrets redacted).
    before_config = Column(JSONB, nullable=True)
    # Full configuration snapshot after the change (secrets redacted).
    after_config = Column(JSONB, nullable=False)
    # List of top-level keys that changed between before and after.
    changed_keys = Column(JSONB, nullable=False, default=list)
    # Origin of the change: "api", "system", "rollback", etc.
    source = Column(String(50), nullable=False, index=True)
    # Username or service identity that triggered the change.
    created_by = Column(String(255), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<ConfigRevision id={self.id} " f"entity={self.entity_type}/{self.entity_id} " f"by={self.created_by}>"
