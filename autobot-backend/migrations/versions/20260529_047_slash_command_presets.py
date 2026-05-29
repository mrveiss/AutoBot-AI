"""Create slash_command_presets table for storing reusable slash command templates (GH#8595).

Table: slash_command_presets
- id (UUID, PK)
- org_id (UUID, nullable, indexed) — for org-wide presets
- user_id (String, nullable, indexed) — for personal presets
- command (String, unique slug) — lowercase alphanumeric + underscores
- description (Text) — description of the preset
- prompt_template (Text) — the template to use
- created_at (DateTime with timezone)
- updated_at (DateTime with timezone)

Scoping: personal presets (user_id set, org_id NULL) vs org presets (org_id set, user_id NULL)
Uniqueness: (org_id, user_id, command) tuple must be unique per scope

Revision ID: 20260529_047
Revises: 20260528_046
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_047"
down_revision: Union[str, None] = "20260528_046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "slash_command_presets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True, index=True),
        sa.Column("user_id", sa.String(255), nullable=True, index=True),
        sa.Column("command", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "user_id", "command", name="uq_scope_command"),
    )


def downgrade() -> None:
    op.drop_table("slash_command_presets")
