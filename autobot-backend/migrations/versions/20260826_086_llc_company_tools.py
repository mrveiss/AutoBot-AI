# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-company facts about a registered tool: URL and logo (#14852).

The tool registry owns a tool's identity — name, description, and the ``tags``
it groups under. This table does not repeat any of it. It carries only what is
*per company* and therefore cannot live in a process-wide registry: the
company's own account URL for the tool, and the logo it recognises the tool by.
It is also where #14847's cost and renewal will hang, for the same reason: a
subscription price belongs to a company's use of a tool, not to the tool.

``NO DATA LOSS``: this migration creates one new table and touches nothing that
exists. In particular it does **not** rewrite ``llc_role_tools``. The issue
(#14852) called for reconciling case-variant duplicates there; there are none
to reconcile, because ``RoleToolService._require_registered_tool`` has
validated every attachment against the registry since the table was created in
the same commit (eaeb09e569, #14357). A reconciliation pass here would be dead
code producing an always-empty report.

The row is an overlay and its absence is normal: reads left-join it, so a tool
nobody has recorded a URL for still appears with its registry metadata.

Guarded with ``has_table`` (the 20260812_073 idiom) so a database already
carrying this shape does not hard-fail.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_086"
down_revision: Union[str, None] = "20260825_085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Table names are string literals at every ``op.*`` call site, never these
# constants: ``migrations/baseline.py`` AST-extracts each revision's artifacts,
# and that extraction is only sound while the names are literal. A constant
# makes the revision invisible to the probe ladder, which then widens its
# adoption bracket. Enforced by tests/migrations/test_probe_ladder_selfcheck.py.
_TOOL_TABLE = "llc_company_tools"
_TOOL_UNIQUE = "uq_llc_company_tools_company_tool"

#: Mirrors ``llc_role_tools.tool_name`` — the same registry key.
_TOOL_NAME_LENGTH = 255

#: Past the ~2000-character ceiling browsers and proxies impose in practice.
_URL_LENGTH = 2048


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, _TOOL_TABLE):
        op.create_table(
            "llc_company_tools",
            sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", sa.UUID(as_uuid=True), nullable=False),
            # A registry key, not free text. No foreign key exists to point it
            # at: the authority for "is this a real tool" is the in-process
            # registry, so the service validates on write instead.
            sa.Column("tool_name", sa.String(_TOOL_NAME_LENGTH), nullable=False),
            # Both nullable. A company may know the URL and not the logo, or
            # neither; the row exists as soon as one fact is recorded.
            sa.Column("url", sa.String(_URL_LENGTH), nullable=True),
            sa.Column("logo_url", sa.String(_URL_LENGTH), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            # One overlay per tool per company. Without it a second row would
            # shadow the first and which won would depend on row order.
            sa.UniqueConstraint("company_id", "tool_name", name=_TOOL_UNIQUE),
        )
        op.create_index("ix_llc_company_tools_company_id", "llc_company_tools", ["company_id"])
        op.create_index("ix_llc_company_tools_tool_name", "llc_company_tools", ["tool_name"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, _TOOL_TABLE):
        op.drop_index("ix_llc_company_tools_tool_name", table_name="llc_company_tools")
        op.drop_index("ix_llc_company_tools_company_id", table_name="llc_company_tools")
        op.drop_table("llc_company_tools")
