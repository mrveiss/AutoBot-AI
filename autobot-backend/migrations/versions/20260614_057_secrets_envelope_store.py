# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unified envelope secrets store: secrets envelope columns + secret_grants.

Revision ID: 20260614_057
Revises: 20260612_056
Create Date: 2026-06-14

Umbrella #10088 / Task 2.1. Additive only — adds the envelope columns to
``secrets`` and the per-grantee ``secret_grants`` child table, and relaxes the
legacy ``encrypted_value`` to nullable (a row is envelope-backed iff
``sealed_value IS NOT NULL``). Touches no runtime read/write path; the live
``secrets.json`` GUI store is unaffected.

Guarded with ``migrations.guards`` so it is safe on databases where these were
already created via ``create_all`` (#10027 pattern).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.guards import has_column, has_table

revision: str = "20260614_057"
down_revision: Union[str, None] = "20260612_056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- envelope columns on secrets ---
    if not has_column("secrets", "owner_vault"):
        op.add_column(
            "secrets",
            sa.Column(
                "owner_vault",
                sa.String(512),
                nullable=True,
                comment="VaultRef.to_str() of the owning vault (envelope store). NULL for legacy rows.",
            ),
        )
        op.create_index("ix_secrets_owner_vault", "secrets", ["owner_vault"])

    if not has_column("secrets", "sealed_value"):
        op.add_column(
            "secrets",
            sa.Column(
                "sealed_value",
                postgresql.JSONB,
                nullable=True,
                comment="SealedSecret.to_dict() — envelope-sealed value (#10088); NULL for legacy rows.",
            ),
        )

    if not has_column("secrets", "version"):
        op.add_column(
            "secrets",
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="Envelope DEK/rotation generation (#10088).",
            ),
        )

    # Legacy Fernet blob is no longer required (envelope rows have none).
    op.alter_column("secrets", "encrypted_value", existing_type=sa.Text(), nullable=True)

    # --- secret_grants child table (one wrapped DEK per grantee vault) ---
    if not has_table("secret_grants"):
        op.create_table(
            "secret_grants",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "secret_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("secrets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "grantee",
                sa.String(512),
                nullable=False,
                comment="VaultRef.to_str() of the grantee vault; matches WrappedDek.grantee",
            ),
            sa.Column(
                "wrapped_dek",
                postgresql.JSONB,
                nullable=False,
                comment="WrappedDek.to_dict() — the secret's DEK wrapped under this grantee's vault KEK",
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Acting principal (user_id) who created this grant",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("secret_id", "grantee", name="uq_secret_grants_secret_grantee"),
        )
        op.create_index("ix_secret_grants_secret_id", "secret_grants", ["secret_id"])
        op.create_index("ix_secret_grants_grantee", "secret_grants", ["grantee"])


def downgrade() -> None:
    if has_table("secret_grants"):
        op.drop_index("ix_secret_grants_grantee", table_name="secret_grants")
        op.drop_index("ix_secret_grants_secret_id", table_name="secret_grants")
        op.drop_table("secret_grants")

    if has_column("secrets", "version"):
        op.drop_column("secrets", "version")
    if has_column("secrets", "sealed_value"):
        op.drop_column("secrets", "sealed_value")
    if has_column("secrets", "owner_vault"):
        op.drop_index("ix_secrets_owner_vault", table_name="secrets")
        op.drop_column("secrets", "owner_vault")

    # Leave ``encrypted_value`` nullable: the pre-057 NOT NULL cannot be safely
    # restored once envelope rows (with NULL here) exist.
