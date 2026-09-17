# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workspace an agent runs in, with an owner and an expiry (#16818).

Company OS has always *used* workspaces -- the adapters shell out to a git worktree --
and never owned one. There was no record, no owner, no expiry, so disposal was a shell
script inferring intent from a coordination ledger outside the domain entirely.

What that costs, observed on 2026-09-16: the worktree ceiling refused a new workspace and
blocked a release-pipeline fix. The reaper found four workspaces whose branches were fully
merged and correctly refused all four, because three were claimed by a session that no
longer existed and the claim had no expiry. Merged work held slots that nothing could
release, and the eventual workaround was to stop using workspaces altogether.

The missing primitive is not a bigger ceiling. It is an owner and a deadline: a lease that
can be reclaimed on its own terms when the thing that took it is gone.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCWorkspaceLease(Base):
    """One agent workspace, leased to a run rather than owned by a session.

    ``expires_at`` is what makes a workspace reclaimable without its claimant present --
    the case that deadlocked the fleet. ``released_at`` records a clean handback, so a
    reclaimed lease and a returned one are never confused: one is the system recovering,
    the other is the system working.
    """

    __tablename__ = "llc_workspace_leases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    #: Filesystem path of the workspace. Unique: two live leases on one directory is the
    #: collision the ledger exists to prevent, so the database refuses it outright.
    path: Mapped[str] = mapped_column(sa.Text(), nullable=False, unique=True)
    #: Who holds it. A session name, an agent id -- whatever took it, recorded so a
    #: reclaim can say whose lease it was rather than only that one expired.
    owner: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    #: What it was taken for. A workspace with no purpose is the debris this prevents.
    purpose: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    #: The run that took it, when there is one. SET NULL rather than CASCADE: losing the
    #: run must not silently delete the lease, because an orphaned lease is exactly what
    #: needs reclaiming and a deleted row cannot be reclaimed.
    heartbeat_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, index=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    #: Why it ended. Free text so a reclaim states its reason -- "run stalled", "branch
    #: merged", "handed back" -- rather than leaving a reader to infer it from timestamps.
    release_reason: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)

    def is_live(self, now: Optional[datetime] = None) -> bool:
        """Held and not yet expired. A released lease is never live, whatever its expiry."""
        if self.released_at is not None:
            return False
        return self.expires_at > (now or datetime.now(tz=self.expires_at.tzinfo))


__all__ = ["LLCWorkspaceLease"]
