# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Converge co_worker_type onto the AssigneeType vocabulary (#13970).

``co_worker_type`` and ``assignee_type`` describe the same axis — is this actor
an agent or a person — but disagreed on the person side: ``"human"`` versus
``"user"``. The fork produced a live bug (#13954), and the axis is becoming
three-valued now that contacts exist (#13969), so it had to be settled rather
than renamed around.

``AssigneeType`` won: a *contact* is also a human, so ``"human"`` stops
discriminating the moment the third person kind exists, while ``"user"`` keeps
naming exactly one thing — a ``users`` row.

Data-only and idempotent: rewrites stored ``'human'`` to ``'user'``. Re-running
matches nothing and is a no-op. The downgrade restores ``'human'`` so the
revision is reversible, though the application no longer writes it.

Revision ID: 20260815_075
Revises: 20260812_073
"""

from typing import Sequence, Union

from alembic import op

from migrations.guards import has_table

revision: str = "20260815_075"
down_revision: Union[str, None] = "20260812_073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "llc_work_items"


def upgrade() -> None:
    if not has_table(_TABLE):
        return
    op.execute(f"UPDATE {_TABLE} SET co_worker_type = 'user' WHERE co_worker_type = 'human'")


def downgrade() -> None:
    if not has_table(_TABLE):
        return
    op.execute(f"UPDATE {_TABLE} SET co_worker_type = 'human' WHERE co_worker_type = 'user'")
