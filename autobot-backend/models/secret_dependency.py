# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What depends on a secret — the dependency half of the auditable secrets graph.

Task 8.2 of umbrella #10088. ``secret_grants`` answers *who can access* a secret;
this answers *what depends on* it: a service / agent / workflow that consumes the
secret at run time. One row per (secret, dependent), so a secret's blast radius —
the rotation/revocation impact list — is a single indexed lookup.

``dependent_kind`` is one of :data:`DEPENDENT_KINDS`; ``dependent_id`` is the
consumer's identifier in that namespace (agent type, workflow id, service name).
``company_id`` is the optional org coordinate that lets the org-tree rollup
(Task 8.4) aggregate dependents per node.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from user_management.models.base import Base

#: Consumer namespaces a dependency may belong to (validated by the service layer).
DEPENDENT_KINDS = ("service", "agent", "workflow")


class SecretDependency(Base):
    """One consumer (service/agent/workflow) that depends on a secret (N:1 with ``secrets``)."""

    __tablename__ = "secret_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    secret_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dependent_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="One of DEPENDENT_KINDS: service / agent / workflow",
    )

    dependent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The consumer's identifier in its namespace (agent type, workflow id, service name)",
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
        comment="Optional org coordinate (LLC company) for org-tree dependency rollup",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Acting principal (user_id) that registered this dependency",
    )

    # created_at / updated_at are provided by Base.

    __table_args__ = (
        UniqueConstraint("secret_id", "dependent_kind", "dependent_id", name="uq_secret_dependencies_secret_dependent"),
    )

    def __repr__(self) -> str:
        return f"<SecretDependency(secret_id={self.secret_id}, {self.dependent_kind}:{self.dependent_id})>"
