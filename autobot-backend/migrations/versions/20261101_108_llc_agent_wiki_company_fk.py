# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Foreign key from the agent wiki to its company (#20156).

Revision ID: 20261101_108
Revises: 20261031_107
Create Date: 2026-11-01 00:00:01.000000

``NO DATA LOSS``: no row is deleted or rewritten. The constraint is added ``NOT VALID``: Postgres
then checks every new or updated row against ``organizations`` and leaves the rows already stored
alone, so an install holding orphans (wiki rows of a company that was hard-deleted) still updates.
The orphans are counted and logged at WARNING, never removed.

Validating the old rows is a separate, human-approved step: once the orphans are reviewed and
removed or reassigned through the approval gates (#17038), run
``ALTER TABLE llc_agent_wiki_entries VALIDATE CONSTRAINT fk_llc_agent_wiki_entries_company_id``.

``ON DELETE CASCADE`` matches ``llc_activity_log`` (the other llc table that names a company) and
every other child of ``organizations``. A soft delete (``deleted_at``) never reaches it; only an
explicit hard delete of the company removes its wiki rows, which is what leaves no orphans.

Downgrade drops only the constraint.

"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

logger = logging.getLogger(__name__)

revision: str = "20261101_108"
down_revision: Union[str, None] = "20261031_107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "llc_agent_wiki_entries"
_FK = "fk_llc_agent_wiki_entries_company_id"
_ORPHANS = (
    "SELECT count(*) FROM llc_agent_wiki_entries w "
    "WHERE NOT EXISTS (SELECT 1 FROM organizations o WHERE o.id = w.company_id)"
)


def _has_fk() -> bool:
    return any(fk["name"] == _FK for fk in sa.inspect(op.get_bind()).get_foreign_keys(_TABLE))


def upgrade() -> None:
    if not has_table(_TABLE) or _has_fk():
        return
    orphans = op.get_bind().execute(sa.text(_ORPHANS)).scalar()
    if orphans:
        logger.warning(
            "#20156: %d row(s) in %s name a company that no longer exists; kept, not deleted. "
            "The constraint is NOT VALID (new rows only) until they are cleaned up with approval.",
            orphans,
            _TABLE,
        )
    op.execute(
        "ALTER TABLE llc_agent_wiki_entries ADD CONSTRAINT fk_llc_agent_wiki_entries_company_id "
        "FOREIGN KEY (company_id) REFERENCES organizations (id) ON DELETE CASCADE NOT VALID"
    )


def downgrade() -> None:
    if has_table(_TABLE) and _has_fk():
        op.drop_constraint(_FK, _TABLE, type_="foreignkey")
