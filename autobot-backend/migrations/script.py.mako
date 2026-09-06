# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

NO DATA LOSS: <what this touches, and why nothing is lost>

Required by tools/lint/check_destructive_migration_marker.py when this migration
drops a column, table or constraint (#15776). Delete this line only if the
migration is purely additive -- and say so above if it is not obvious.

A drop is only safe once NO deployed release still writes the thing being
dropped: expand (add + dual-write) in release N, contract (drop) in N+1. See
docs/developer/DESTRUCTIVE_MIGRATIONS.md, including the chunked backfill
template -- an unbounded UPDATE over a large table is how a migration stops a
rolling update mid-flight.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
