# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One row per post-sync action a code sync executed (#17455).

Lives beside `models/database.py` rather than in it: that file is pinned at its
file-size ratchet ceiling, so a new concept cannot become a new class there.
Registered on the same `Base`, so `Base.metadata.create_all` creates it the way
it creates every other table; the migration covers databases created earlier.

`command` and `output_tail` are stored already redacted (see
`services/post_sync_recorder.py`) -- the table must never become a second place
a credential from a remote command's output is kept.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from models.database import Base


class PostSyncActionRun(Base):
    """What one post-sync command or restart did: what ran, when, exit status, output tail."""

    __tablename__ = "post_sync_action_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)  # groups every action of one sync run
    node_id = Column(String(64), nullable=False)
    role_name = Column(String(50), nullable=False)
    category = Column(String(20), nullable=False)  # post_sync | restart
    label = Column(String(255), nullable=False)
    command = Column(Text, nullable=True)
    units = Column(Text, nullable=True)  # space-separated systemd units, restarts only
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=False)
    exit_code = Column(Integer, nullable=True)  # NULL: no exit status (timeout, spawn error)
    success = Column(Boolean, nullable=True)  # NULL: issued, outcome unknown (the self-killing slm-backend restart)
    output_tail = Column(Text, nullable=False, default="")
    error = Column(Text, nullable=True)
