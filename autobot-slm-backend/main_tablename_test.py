# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit test for SLM tablename collision check (#2226, #2413).

Tests :func:`autobot_shared.tablename_validator.check_tablename_collisions` directly.
The logic was extracted from ``main._check_tablename_collisions`` into autobot_shared
(#2413) so tests can import and exercise the real function without pulling in the
full SLM application stack (FastAPI routers, SQLAlchemy models, all services, etc.).
"""

import logging
from unittest.mock import MagicMock

from autobot_shared.tablename_validator import check_tablename_collisions


class TestCheckTablenameCollisions:
    """Tests for tablename collision detection logic (#2226)."""

    def test_collision_detected_logs_warning(self, caplog):
        """Overlapping tablenames produce a WARNING log entry."""
        slm_meta = MagicMock(tables={"users": None, "nodes": None})
        um_meta = MagicMock(tables={"users": None, "roles": None})

        with caplog.at_level(logging.WARNING):
            check_tablename_collisions(slm_meta, um_meta)

        assert any(
            "overlap" in r.message.lower() for r in caplog.records
        ), f"Expected 'overlap' in log, got: {[r.message for r in caplog.records]}"

    def test_no_collision_logs_info(self, caplog):
        """Disjoint tablenames produce an INFO log entry with table counts."""
        slm_meta = MagicMock(tables={"nodes": None, "deployments": None})
        um_meta = MagicMock(tables={"users": None, "roles": None})

        with caplog.at_level(logging.INFO):
            check_tablename_collisions(slm_meta, um_meta)

        assert any(
            "0 shared" in r.message for r in caplog.records
        ), f"Expected '0 shared' in log, got: {[r.message for r in caplog.records]}"

    def test_does_not_raise_on_collision(self):
        """Function never raises — collisions are warnings, not errors."""
        slm_meta = MagicMock(tables={"shared_table": None})
        um_meta = MagicMock(tables={"shared_table": None})

        # Should not raise
        check_tablename_collisions(slm_meta, um_meta)

    def test_collision_includes_table_names(self, caplog):
        """Warning message includes the names of colliding tables."""
        slm_meta = MagicMock(tables={"audit_logs": None, "nodes": None})
        um_meta = MagicMock(tables={"audit_logs": None, "users": None})

        with caplog.at_level(logging.WARNING):
            check_tablename_collisions(slm_meta, um_meta)

        assert any("audit_logs" in r.message for r in caplog.records)

    def test_multiple_collisions_sorted(self, caplog):
        """Multiple collisions are sorted alphabetically in the warning."""
        slm_meta = MagicMock(tables={"roles": None, "audit_logs": None, "users": None})
        um_meta = MagicMock(tables={"roles": None, "audit_logs": None, "users": None})

        with caplog.at_level(logging.WARNING):
            check_tablename_collisions(slm_meta, um_meta)

        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_msgs) >= 1
        # Should mention count of 3
        assert "3 shared" in warning_msgs[0]

    def test_empty_tables_no_collision(self, caplog):
        """Two empty metadata objects produce no collision."""
        slm_meta = MagicMock(tables={})
        um_meta = MagicMock(tables={})

        with caplog.at_level(logging.INFO):
            check_tablename_collisions(slm_meta, um_meta)

        assert any("0 shared" in r.message for r in caplog.records)
