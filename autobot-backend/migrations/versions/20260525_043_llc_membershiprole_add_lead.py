"""Add LEAD value to membershiprole PG enum (GH#8583 follow-up).

Commit 332ca3b5a added MembershipRole.LEAD to the Python enum but omitted
the corresponding ALTER TYPE for the PostgreSQL enum type created in
migration 20260523_031.

Revision ID: 20260525_043
Revises: 20260525_042
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260525_043"
down_revision: Union[str, None] = "20260525_042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE membershiprole ADD VALUE IF NOT EXISTS 'lead'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; a manual pg_enum
    # row deletion would be required and is intentionally left undocumented.
    pass
