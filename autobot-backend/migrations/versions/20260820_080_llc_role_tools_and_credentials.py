# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_role_tools and llc_role_credentials (#14221 step 4).

Tools and credential *references* hang off the role, so a change of holder moves
nothing: the next occupant reaches the same tools and secrets because the
attachments were never the previous occupant's.

``llc_role_credentials`` stores ``secret_id`` only — never a value. The
plaintext stays behind ``SecretService``, which owns decryption, revocation and
the audit trail.

Note the deliberate type asymmetry: ``company_id`` here is ``UUID`` (matching
``roles.org_id`` / ``organizations.id``), while ``llc_secrets.company_id`` is
``VARCHAR(255)`` — the split tracked in #14312. No foreign key to ``llc_secrets``
for that reason; the reference is validated in the service, where the one
conversion lives and is named.

Plain ``op.create_table`` — the tolerant ``IF NOT EXISTS`` form belongs to drift
reconciliations for tables already changed out-of-band, not to tables born here.

Revision ID: 20260820_080
Revises: 20260819_079
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260820_080"
down_revision: Union[str, None] = "20260819_079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOOL_INDEXES = ("company_id", "role_id", "tool_name")
_CREDENTIAL_INDEXES = ("company_id", "role_id", "secret_id")


def _timestamps() -> list:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "llc_role_tools",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("role_id", "tool_name", name="uq_llc_role_tools_role_tool"),
    )
    for column in _TOOL_INDEXES:
        op.create_index(f"ix_llc_role_tools_{column}", "llc_role_tools", [column])

    op.create_table(
        "llc_role_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        # No FK to llc_secrets: its company_id is VARCHAR while this is UUID
        # (#14312). Validated in RoleCredentialService instead.
        sa.Column("secret_id", UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("role_id", "secret_id", name="uq_llc_role_credentials_role_secret"),
    )
    for column in _CREDENTIAL_INDEXES:
        op.create_index(f"ix_llc_role_credentials_{column}", "llc_role_credentials", [column])


def downgrade() -> None:
    for column in _CREDENTIAL_INDEXES:
        op.drop_index(f"ix_llc_role_credentials_{column}", table_name="llc_role_credentials")
    op.drop_table("llc_role_credentials")
    for column in _TOOL_INDEXES:
        op.drop_index(f"ix_llc_role_tools_{column}", table_name="llc_role_tools")
    op.drop_table("llc_role_tools")
