"""Create llc_boards and llc_board_columns tables.

Revision ID: 20260523_032
Revises: 20260523_031
Create Date: 2026-05-23 00:00:00.000000

GH#8221: Kanban and Sprint board infrastructure.
``llc_boards`` stores one board per Kanban/Sprint scope.
``llc_board_columns`` stores the ordered columns for each board.

``boardtype`` enum is created here with checkfirst=True so re-running the
migration on an existing DB is idempotent.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision: str = "20260523_032"
down_revision: Union[str, None] = "20260523_031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# postgresql.ENUM with create_type=False: created explicitly in upgrade() with
# checkfirst=True. Generic sa.Enum silently IGNORES create_type, so
# op.create_table re-emitted CREATE TYPE and aborted on fresh databases (#9759).
_boardtype = ENUM("kanban", "sprint", name="boardtype", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    _boardtype.create(bind, checkfirst=True)

    op.create_table(
        "llc_boards",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("sprint_id", UUID(as_uuid=True), nullable=True),
        sa.Column("type", _boardtype, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_boards_company_id", "llc_boards", ["company_id"])
    op.create_index("ix_llc_boards_project_id", "llc_boards", ["project_id"])
    op.create_index("ix_llc_boards_sprint_id", "llc_boards", ["sprint_id"])
    op.create_index("ix_llc_boards_type", "llc_boards", ["type"])
    op.create_unique_constraint(
        "uq_llc_boards_company_project_type",
        "llc_boards",
        ["company_id", "project_id", "type"],
    )
    op.create_unique_constraint(
        "uq_llc_boards_company_sprint_type",
        "llc_boards",
        ["company_id", "sprint_id", "type"],
    )

    op.create_table(
        "llc_board_columns",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "board_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("status_filter", JSONB, nullable=False, server_default="[]"),
        sa.Column("wip_limit", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_board_columns_board_id", "llc_board_columns", ["board_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_board_columns_board_id", table_name="llc_board_columns")
    op.drop_table("llc_board_columns")
    op.drop_constraint("uq_llc_boards_company_sprint_type", "llc_boards", type_="unique")
    op.drop_constraint("uq_llc_boards_company_project_type", "llc_boards", type_="unique")
    op.drop_index("ix_llc_boards_type", table_name="llc_boards")
    op.drop_index("ix_llc_boards_sprint_id", table_name="llc_boards")
    op.drop_index("ix_llc_boards_project_id", table_name="llc_boards")
    op.drop_index("ix_llc_boards_company_id", table_name="llc_boards")
    op.drop_table("llc_boards")
    bind = op.get_bind()
    _boardtype.drop(bind, checkfirst=True)
