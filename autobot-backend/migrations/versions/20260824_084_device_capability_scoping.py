# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-credential capability scoping for paired devices (#14964).

Adds the three columns ``desktop_mobile_devices`` needs before any enforcement
point can ask *"is this credential allowed this capability"*:

* ``permissions``  — JSON array of capability names this credential holds.
* ``is_approved``  — the credential has been approved for control use.
* ``revoked_at``   — soft revocation; a set value denies without deleting the
  row, so the pairing history and the audit trail survive the revocation.

THE BACKFILL DEFAULT IS **DENY**
--------------------------------
Every pre-existing row lands on ``permissions = '[]'``, ``is_approved = false``,
``revoked_at = NULL``. Two of those three independently deny every capability,
so a credential issued before this migration existed cannot exercise anything.

The alternative — backfilling a grant to preserve some notional prior
behaviour — would silently convert every already-paired device into a
full-control credential. There is no prior behaviour to preserve: no
enforcement point consulted these columns before they existed, so denying costs
nothing that was working, while granting would hand out control nobody asked
for. The same reasoning fixes ``server_default`` at the denied value rather
than only backfilling: a future writer that inserts a row without naming these
columns gets a denied credential, not a privileged one.

``NO DATA LOSS``: three additive columns; nothing existing is altered,
rewritten or dropped. Guarded with ``has_column`` throughout (the 20260812_073
idiom) so a database already carrying this shape does not hard-fail.

``downgrade`` is a working reverse: it drops exactly the three columns
``upgrade`` created and nothing else, so every column that existed before this
revision still exists after it. What a downgrade *does* discard is the grants
recorded in those columns after the upgrade — unavoidable, since the columns
are the only place they live — and the discard is in the safe direction: a
re-upgrade lands back on the denied default rather than restoring a grant
nobody re-authorised.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_084"
down_revision: Union[str, None] = "20260823_083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Table and column names are written as string literals at every ``op.*`` call
# site rather than passed as constants: ``migrations/baseline.py`` AST-extracts
# each revision's artifacts from literal arguments, and a constant makes the
# revision invisible to the probe ladder (enforced by
# tests/migrations/test_probe_ladder_selfcheck.py). The constants below are
# used only by the guard helpers, which are not part of that surface.
_TABLE = "desktop_mobile_devices"

# The denied grant set, as stored. Kept as a literal here rather than imported
# from ``autobot_shared.auth.device_capabilities.NO_CAPABILITIES_JSON``: a
# migration must keep describing the schema it wrote even after application
# code moves on, and the migration gate installs no autobot packages at all.
_DENY_ALL_PERMISSIONS = "[]"


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        return

    # NOT NULL with a denied server_default: existing rows are backfilled by
    # the default itself, in the same statement, with no window in which a row
    # carries NULL and a reader has to decide what NULL means.
    added_permissions = not _has_column(inspector, _TABLE, "permissions")
    if added_permissions:
        op.add_column(
            "desktop_mobile_devices",
            sa.Column(
                "permissions",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
    if not _has_column(inspector, _TABLE, "is_approved"):
        op.add_column(
            "desktop_mobile_devices",
            sa.Column(
                "is_approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if not _has_column(inspector, _TABLE, "revoked_at"):
        op.add_column(
            "desktop_mobile_devices",
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Only verify rows this revision actually backfilled. A database that
    # already carried the columns from an out-of-band path owns its own values,
    # and re-asserting over them would abort an otherwise idempotent upgrade.
    if added_permissions:
        _assert_backfilled_denied(bind)


def _assert_backfilled_denied(bind: sa.engine.Connection) -> None:
    """Refuse to leave a row this migration touched in anything but the denied state.

    The whole risk of #14964 is a row that ends up granted by accident, and a
    server_default is a promise the database keeps rather than one this file
    verifies. So verify it: count the rows that are not denied and fail the
    migration if there are any, rather than discovering later that a
    pre-existing row carried a value from an out-of-band path.
    """
    granted = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM desktop_mobile_devices "
            "WHERE permissions IS NULL OR permissions <> :denied OR is_approved <> :denied_flag"
        ),
        {"denied": _DENY_ALL_PERMISSIONS, "denied_flag": False},
    ).scalar()
    if granted:
        raise RuntimeError(
            f"20260824_084 refusing to complete: {granted} desktop_mobile_devices row(s) "
            "are not in the denied state after backfill. Every pre-existing paired device "
            "must be denied every capability; investigate before re-running."
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _TABLE):
        return

    if _has_column(inspector, _TABLE, "revoked_at"):
        op.drop_column("desktop_mobile_devices", "revoked_at")
    if _has_column(inspector, _TABLE, "is_approved"):
        op.drop_column("desktop_mobile_devices", "is_approved")
    if _has_column(inspector, _TABLE, "permissions"):
        op.drop_column("desktop_mobile_devices", "permissions")
