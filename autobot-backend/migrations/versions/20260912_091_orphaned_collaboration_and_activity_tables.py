# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create 6 tables missing from the live DB (#16464).

Same class of bug as #10750 A2 (see its own migration,
``20260630_065_llc_missing_feature_tables.py``): these tables are declared in
ORM models (and used by live backend code) but were never reachable via the
canonical Alembic chain — they only existed in the orphaned
``database/migrations/`` chain, which ``migrations/alembic.ini`` does not
point at (``script_location = migrations``, ``version_locations =
migrations/versions``) and which ``migrations/schema_bootstrap.py`` confirms
has no silent ``create_all()`` fallback against a real database either.

  session_collaborations — multi-user session collaboration + permissions
                            (api/collaboration.py's entire REST API depends
                            on this table: invite/remove/participants/
                            share-secret, #16429/#16443/#16455/#16462)
  desktop_activities      — GUI automation activity log (api/vnc_proxy.py
                            writes to this on every desktop-automation
                            action via integrations/desktop_tracking.py --
                            actively broken today, not just unreachable)
  terminal_activities     — shell command activity log
  file_activities         — file operation activity log
  browser_activities      — browser automation activity log
  secret_usage            — secret access audit trail

**Higher-impact than collaboration alone (found during review):** all five
activity/secret_usage tables carry ``ForeignKey("users.id", ondelete=
"CASCADE")``. A missing CASCADE target makes the cascade itself fail --
hard-deleting a user, or an organization whose members cascade-delete,
raised (500) on any live install with a row is has to cascade through,
because the CASCADE constraint referenced a table Postgres doesn't have.
Not just unreachable code: this broke a core admin operation.

The last three of those five activity tables (terminal/file/browser) and
secret_usage have no live backend *caller* today (their writer modules --
integrations/terminal_tracking.py, integrations/file_tracking.py,
integrations/browser_tracking.py, knowledge/activity_types.py -- are
themselves unwired, zero callers) but the CASCADE-target problem above
applies regardless of whether anything currently writes to them. Ported
anyway, per standing rule: unwired code is unfinished work, not something a
migration gets to silently drop. A follow-up to wire or retire them is
tracked separately (#16464's own acceptance criteria).

NOT included: database/migrations/001_create_conversation_files.py lives in
the same orphaned directory but isn't the same bug -- it manages its own
dedicated SQLite file (conversation_files.db) via a self-contained migration
runner invoked live from conversation_file_manager.py, entirely independent
of this Postgres/Alembic-managed database. Checked and excluded.

Source of truth for columns/types/FKs/indexes:
  - models/session_collaboration.py :: SessionCollaboration
  - models/activities.py :: TerminalActivityModel, FileActivityModel,
    BrowserActivityModel, DesktopActivityModel, SecretUsageModel

``models/activities.py``'s JSONB metadata column is named ``extra_data``, not
``metadata`` as the orphaned database/migrations/003_create_activities_tables.py
DDL still says -- ``metadata`` collides with SQLAlchemy declarative's own
reserved ``Base.metadata`` attribute, so the ORM model (the actual source of
truth) could never have used that name. This migration follows the model.

``user_management.models.base.Base`` adds implicit ``created_at``/
``updated_at`` (``DateTime(timezone=True)``, ``server_default=func.now()``,
``updated_at`` also ``onupdate=func.now()``) to every ORM model; included
here to keep the ORM fully satisfied, matching #10750 A2's own approach.

NO DATA LOSS: every operation below is CREATE TABLE / CREATE INDEX. Nothing
existing is altered or dropped, so there is no data to lose -- stated
explicitly per the destructive-migration convention even though this
migration has no destructive operation for that guard to flag.

Idempotent: every ``op.create_table`` is guarded by ``has_table``, so this
migration is a no-op against an install where a table already exists (e.g.
a prior manual fix, or a `create_all()` opt-in).

Deliberately fully inlined, no shared per-table helper, matching #10750 A2's
own style: repo_tests/orphaned_database_migrations_test.py (#16464) reads
``op.create_table("literal_name", ...)`` calls by AST, and a table name
passed through a helper's parameter is invisible to a literal-only scanner --
the same "variable, not literal" caveat the destructive-migration marker
guard's own docs state for its column check. Duplication here is the guard's
own price of admission, paid deliberately.

Revision ID: 20260912_091
Revises: 20260907_090
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from migrations.guards import has_table

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "20260912_091"
down_revision: Union[str, None] = "20260907_090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. session_collaborations
    #    Source: models/session_collaboration.py :: SessionCollaboration
    #    Columns: session_id (PK), owner_id, collaborators, invitations,
    #             collaboration_metadata, created_at, updated_at (from Base)
    #    FK: owner_id -> users.id CASCADE
    #    Index: ix_session_collaborations_owner_id
    # ------------------------------------------------------------------
    if not has_table("session_collaborations"):
        op.create_table(
            "session_collaborations",
            sa.Column(
                "session_id",
                sa.String(128),
                primary_key=True,
                nullable=False,
                comment="Chat session identifier",
            ),
            sa.Column(
                "owner_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                comment="User ID who owns the session",
            ),
            sa.Column(
                "collaborators",
                JSONB,
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
                comment="Map of user_id to permission_level (owner/editor/viewer)",
            ),
            sa.Column(
                "invitations",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
                comment="Pending collaboration invitations",
            ),
            sa.Column(
                "collaboration_metadata",
                JSONB,
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
                comment="Additional collaboration metadata",
            ),
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
        op.create_index("ix_session_collaborations_owner_id", "session_collaborations", ["owner_id"])

    # ------------------------------------------------------------------
    # 2. terminal_activities
    #    Source: models/activities.py :: TerminalActivityModel
    # ------------------------------------------------------------------
    if not has_table("terminal_activities"):
        op.create_table(
            "terminal_activities",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("command", sa.Text, nullable=False),
            sa.Column("working_directory", sa.String(1024), nullable=True),
            sa.Column("exit_code", sa.Integer, nullable=True),
            sa.Column("output", sa.Text, nullable=True),
            sa.Column(
                "secrets_used",
                ARRAY(UUID(as_uuid=True)),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("extra_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_terminal_activities_user_id", "terminal_activities", ["user_id"])
        op.create_index("ix_terminal_activities_session_id", "terminal_activities", ["session_id"])
        op.create_index("ix_terminal_activities_timestamp", "terminal_activities", ["timestamp"])

    # ------------------------------------------------------------------
    # 3. file_activities
    #    Source: models/activities.py :: FileActivityModel
    # ------------------------------------------------------------------
    if not has_table("file_activities"):
        op.create_table(
            "file_activities",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("operation", sa.String(50), nullable=False),
            sa.Column("path", sa.String(2048), nullable=False),
            sa.Column("new_path", sa.String(2048), nullable=True),
            sa.Column("file_type", sa.String(100), nullable=True),
            sa.Column("size_bytes", sa.Integer, nullable=True),
            sa.Column("extra_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_file_activities_user_id", "file_activities", ["user_id"])
        op.create_index("ix_file_activities_session_id", "file_activities", ["session_id"])
        op.create_index("ix_file_activities_operation", "file_activities", ["operation"])
        op.create_index("ix_file_activities_timestamp", "file_activities", ["timestamp"])

    # ------------------------------------------------------------------
    # 4. browser_activities
    #    Source: models/activities.py :: BrowserActivityModel
    # ------------------------------------------------------------------
    if not has_table("browser_activities"):
        op.create_table(
            "browser_activities",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("selector", sa.String(512), nullable=True),
            sa.Column("input_value", sa.Text, nullable=True),
            sa.Column(
                "secrets_used",
                ARRAY(UUID(as_uuid=True)),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("extra_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_browser_activities_user_id", "browser_activities", ["user_id"])
        op.create_index("ix_browser_activities_session_id", "browser_activities", ["session_id"])
        op.create_index("ix_browser_activities_action", "browser_activities", ["action"])
        op.create_index("ix_browser_activities_timestamp", "browser_activities", ["timestamp"])

    # ------------------------------------------------------------------
    # 5. desktop_activities
    #    Source: models/activities.py :: DesktopActivityModel
    #    Live: api/vnc_proxy.py -> integrations/desktop_tracking.py writes
    #    here on every desktop-automation action.
    # ------------------------------------------------------------------
    if not has_table("desktop_activities"):
        op.create_table(
            "desktop_activities",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("coordinates", ARRAY(sa.Integer, dimensions=1), nullable=True),
            sa.Column("window_title", sa.String(512), nullable=True),
            sa.Column("input_text", sa.Text, nullable=True),
            sa.Column("screenshot_path", sa.String(1024), nullable=True),
            sa.Column("extra_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_desktop_activities_user_id", "desktop_activities", ["user_id"])
        op.create_index("ix_desktop_activities_session_id", "desktop_activities", ["session_id"])
        op.create_index("ix_desktop_activities_action", "desktop_activities", ["action"])
        op.create_index("ix_desktop_activities_timestamp", "desktop_activities", ["timestamp"])

    # ------------------------------------------------------------------
    # 6. secret_usage
    #    Source: models/activities.py :: SecretUsageModel
    # ------------------------------------------------------------------
    if not has_table("secret_usage"):
        op.create_table(
            "secret_usage",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("secret_id", UUID(as_uuid=True), nullable=False),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("activity_type", sa.String(50), nullable=False),
            sa.Column("activity_id", UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", sa.String(128), nullable=True),
            sa.Column("access_granted", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("denial_reason", sa.String(512), nullable=True),
            sa.Column("extra_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
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
        op.create_index("ix_secret_usage_secret_id", "secret_usage", ["secret_id"])
        op.create_index("ix_secret_usage_user_id", "secret_usage", ["user_id"])
        op.create_index("ix_secret_usage_activity_type", "secret_usage", ["activity_type"])
        op.create_index("ix_secret_usage_activity_id", "secret_usage", ["activity_id"])
        op.create_index("ix_secret_usage_session_id", "secret_usage", ["session_id"])
        op.create_index("ix_secret_usage_timestamp", "secret_usage", ["timestamp"])


# ---------------------------------------------------------------------------
# downgrade — forward-only, consistent with 063/064/065
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Forward-only: dropping these re-breaks api/collaboration.py entirely,
    # desktop-automation activity logging (live today), and reintroduces the
    # CASCADE-target gap that 500s a hard user/org delete.
    pass
