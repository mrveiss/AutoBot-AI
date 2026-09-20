# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add view tracking and a login requirement to chat shared links (#16861).

GH#8996 shipped shareable chat links but never landed the two fields its own
"What Users Want" section named: a view count / last-accessed timestamp, and
restricting a link to authenticated users only. A draft of this exact migration
survived on a rescued stash (``rescued/stash-2026-06-05-1557e2b21``) with
``down_revision = "20260531_050"`` -- stale, since ``20260531_050`` already has
a different direct successor (``20260604_036_budget_token_mode.py``) on this
chain. Rebased onto the current head instead of reusing that ``down_revision``.

``NO DATA LOSS``: adds three columns to ``chat_shared_links`` with defaults
(``view_count`` 0, ``require_login`` false, ``last_accessed_at`` NULL) so every
existing row backfills without a data migration. ``downgrade`` drops exactly
those three columns.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column

revision: str = "20260919_095"
down_revision: Union[str, None] = "20260918_094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "chat_shared_links"


def upgrade() -> None:
    if not has_column(_TABLE, "view_count"):
        op.add_column(
            "chat_shared_links",
            sa.Column(
                "view_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="Number of times this link has been accessed",
            ),
        )
    if not has_column(_TABLE, "last_accessed_at"):
        op.add_column(
            "chat_shared_links",
            sa.Column(
                "last_accessed_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Timestamp of the last access; NULL if never accessed",
            ),
        )
    if not has_column(_TABLE, "require_login"):
        op.add_column(
            "chat_shared_links",
            sa.Column(
                "require_login",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="If True, only authenticated users can access (no public access)",
            ),
        )


def downgrade() -> None:
    if has_column(_TABLE, "require_login"):
        op.drop_column(_TABLE, "require_login")
    if has_column(_TABLE, "last_accessed_at"):
        op.drop_column(_TABLE, "last_accessed_at")
    if has_column(_TABLE, "view_count"):
        op.drop_column(_TABLE, "view_count")
