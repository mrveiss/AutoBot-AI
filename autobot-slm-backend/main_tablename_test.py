# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit test for SLM tablename collision check (#2226, #2413, #10862).

Tests :func:`autobot_shared.tablename_validator.check_tablename_collisions` directly.
The logic was extracted from ``main._check_tablename_collisions`` into autobot_shared
(#2413) so tests can import and exercise the real function without pulling in the
full SLM application stack (FastAPI routers, SQLAlchemy models, all services, etc.).

As of #10862 the function RAISES :exc:`TableNameCollisionError` for any collision
not present in ``INTENTIONALLY_SHARED_TABLENAMES``.  Allowlisted collisions (currently
only ``roles``) continue to produce a WARNING log but do not raise.
"""

import logging
from unittest.mock import MagicMock

import pytest

from autobot_shared.tablename_validator import (
    INTENTIONALLY_SHARED_TABLENAMES,
    TableNameCollisionError,
    check_tablename_collisions,
)


class TestCheckTablenameCollisions:
    """Tests for tablename collision detection logic (#2226, #10862)."""

    # ------------------------------------------------------------------
    # Core raise-vs-warn contract (added/updated for #10862)
    # ------------------------------------------------------------------

    def test_unallowlisted_collision_raises(self):
        """Non-allowlisted collision raises TableNameCollisionError (#10862)."""
        slm_meta = MagicMock(tables={"nodes": None, "shared_danger": None})
        um_meta = MagicMock(tables={"users": None, "shared_danger": None})

        with pytest.raises(TableNameCollisionError, match="shared_danger"):
            check_tablename_collisions(slm_meta, um_meta)

    def test_unallowlisted_collision_message_contains_guidance(self):
        """Error message references the allowlist and the fix path (#10862)."""
        slm_meta = MagicMock(tables={"bad_table": None})
        um_meta = MagicMock(tables={"bad_table": None})

        with pytest.raises(TableNameCollisionError, match="INTENTIONALLY_SHARED_TABLENAMES"):
            check_tablename_collisions(slm_meta, um_meta)

    def test_allowlisted_collision_does_not_raise(self):
        """A collision whose name is in the allowlist does NOT raise (#10862).

        ``roles`` is the one intentionally-shared tablename (SLM admin roles in the
        slm DB, UM roles in the slm_users DB).  The checker must not block startup
        for this known overlap.
        """
        # Verify our test is actually exercising a known-allowlisted name
        assert "roles" in INTENTIONALLY_SHARED_TABLENAMES

        slm_meta = MagicMock(tables={"roles": None, "nodes": None})
        um_meta = MagicMock(tables={"roles": None, "users": None})

        # Must not raise — allowlisted collision is fine (just warns)
        check_tablename_collisions(slm_meta, um_meta)

    def test_allowlisted_collision_logs_warning(self, caplog):
        """Allowlisted collision logs a WARNING (tracked, not silently ignored) (#10862)."""
        slm_meta = MagicMock(tables={"roles": None})
        um_meta = MagicMock(tables={"roles": None})

        with caplog.at_level(logging.WARNING):
            check_tablename_collisions(slm_meta, um_meta)

        assert any(
            "roles" in r.message and r.levelno >= logging.WARNING
            for r in caplog.records
        ), f"Expected WARNING mentioning 'roles', got: {[r.message for r in caplog.records]}"

    def test_mixed_allowlisted_and_unallowlisted_raises_for_unallowlisted(self):
        """If both allowlisted and unallowlisted collisions are present, the function
        still raises — unallowlisted wins (#10862)."""
        slm_meta = MagicMock(tables={"roles": None, "danger_zone": None})
        um_meta = MagicMock(tables={"roles": None, "danger_zone": None})

        with pytest.raises(TableNameCollisionError, match="danger_zone"):
            check_tablename_collisions(slm_meta, um_meta)

    # ------------------------------------------------------------------
    # Clean-path assertions (unchanged semantics)
    # ------------------------------------------------------------------

    def test_no_collision_logs_info(self, caplog):
        """Disjoint tablenames produce an INFO log entry with table counts."""
        slm_meta = MagicMock(tables={"nodes": None, "deployments": None})
        um_meta = MagicMock(tables={"users": None, "roles": None})

        with caplog.at_level(logging.INFO):
            check_tablename_collisions(slm_meta, um_meta)

        assert any(
            "0 shared" in r.message for r in caplog.records
        ), f"Expected '0 shared' in log, got: {[r.message for r in caplog.records]}"

    def test_empty_tables_no_collision(self, caplog):
        """Two empty metadata objects produce no collision."""
        slm_meta = MagicMock(tables={})
        um_meta = MagicMock(tables={})

        with caplog.at_level(logging.INFO):
            check_tablename_collisions(slm_meta, um_meta)

        assert any("0 shared" in r.message for r in caplog.records)

    # ------------------------------------------------------------------
    # Legacy tests updated for new raise-on-collision contract (#10862)
    # ------------------------------------------------------------------

    def test_unallowlisted_collision_mentions_table_name_in_error(self):
        """Error from an unallowlisted collision names the offending table (#10862)."""
        slm_meta = MagicMock(tables={"audit_logs": None, "nodes": None})
        um_meta = MagicMock(tables={"audit_logs": None, "users": None})

        # audit_logs is NOT in the allowlist (it was fixed in #10764 by renaming
        # the SLM node table to slm_node_audit_logs).
        with pytest.raises(TableNameCollisionError, match="audit_logs"):
            check_tablename_collisions(slm_meta, um_meta)

    def test_multiple_unallowlisted_collisions_sorted_in_error(self):
        """Multiple unallowlisted collisions are listed (sorted) in the error (#10862)."""
        slm_meta = MagicMock(tables={"alpha_table": None, "zeta_table": None, "nodes": None})
        um_meta = MagicMock(tables={"alpha_table": None, "zeta_table": None, "users": None})

        with pytest.raises(TableNameCollisionError) as exc_info:
            check_tablename_collisions(slm_meta, um_meta)

        msg = str(exc_info.value)
        assert "alpha_table" in msg
        assert "zeta_table" in msg
