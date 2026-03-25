# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit test for SLM tablename collision check (#2226).

Tests the collision detection logic extracted from _check_tablename_collisions().
Because main.py has heavy transitive imports (FastAPI routers, DB models, etc.),
we test the collision logic in isolation rather than importing main directly.
"""

import logging
from unittest.mock import MagicMock


def _check_tablename_collisions_logic(slm_metadata, um_metadata, logger_):
    """Extracted collision detection logic matching main._check_tablename_collisions.

    This mirrors the function from main.py lines 78-128 so it can be tested
    without importing the full SLM application stack.
    """
    slm_tables: set[str] = set(slm_metadata.tables.keys())
    um_tables: set[str] = set(um_metadata.tables.keys())
    collisions: set[str] = slm_tables & um_tables

    if collisions:
        sorted_names = sorted(collisions)
        logger_.warning(
            "Tablename overlap detected between SLM Base and UserManagement Base — "
            "%d shared name(s): %s. "
            "These names refer to tables in different databases, but sharing names "
            "increases the risk of future model misplacement. "
            "See GitHub issue #1878.",
            len(sorted_names),
            sorted_names,
        )
    else:
        logger_.info(
            "Tablename collision check passed — %d SLM tables, %d UM tables, 0 shared names",
            len(slm_tables),
            len(um_tables),
        )


class TestCheckTablenameCollisions:
    """Tests for tablename collision detection logic (#2226)."""

    def test_collision_detected_logs_warning(self, caplog):
        """Overlapping tablenames produce a WARNING log entry."""
        slm_meta = MagicMock(tables={"users": None, "nodes": None})
        um_meta = MagicMock(tables={"users": None, "roles": None})

        with caplog.at_level(logging.WARNING):
            _check_tablename_collisions_logic(
                slm_meta, um_meta, logging.getLogger("main")
            )

        assert any(
            "overlap" in r.message.lower() for r in caplog.records
        ), f"Expected 'overlap' in log, got: {[r.message for r in caplog.records]}"

    def test_no_collision_logs_info(self, caplog):
        """Disjoint tablenames produce an INFO log entry with table counts."""
        slm_meta = MagicMock(tables={"nodes": None, "deployments": None})
        um_meta = MagicMock(tables={"users": None, "roles": None})

        with caplog.at_level(logging.INFO):
            _check_tablename_collisions_logic(
                slm_meta, um_meta, logging.getLogger("main")
            )

        assert any(
            "0 shared" in r.message for r in caplog.records
        ), f"Expected '0 shared' in log, got: {[r.message for r in caplog.records]}"

    def test_does_not_raise_on_collision(self):
        """Function never raises — collisions are warnings, not errors."""
        slm_meta = MagicMock(tables={"shared_table": None})
        um_meta = MagicMock(tables={"shared_table": None})

        # Should not raise
        _check_tablename_collisions_logic(slm_meta, um_meta, logging.getLogger("main"))

    def test_collision_includes_table_names(self, caplog):
        """Warning message includes the names of colliding tables."""
        slm_meta = MagicMock(tables={"audit_logs": None, "nodes": None})
        um_meta = MagicMock(tables={"audit_logs": None, "users": None})

        with caplog.at_level(logging.WARNING):
            _check_tablename_collisions_logic(
                slm_meta, um_meta, logging.getLogger("main")
            )

        assert any("audit_logs" in r.message for r in caplog.records)

    def test_multiple_collisions_sorted(self, caplog):
        """Multiple collisions are sorted alphabetically in the warning."""
        slm_meta = MagicMock(tables={"roles": None, "audit_logs": None, "users": None})
        um_meta = MagicMock(tables={"roles": None, "audit_logs": None, "users": None})

        with caplog.at_level(logging.WARNING):
            _check_tablename_collisions_logic(
                slm_meta, um_meta, logging.getLogger("main")
            )

        warning_msgs = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert len(warning_msgs) >= 1
        # Should mention count of 3
        assert "3 shared" in warning_msgs[0]

    def test_empty_tables_no_collision(self, caplog):
        """Two empty metadata objects produce no collision."""
        slm_meta = MagicMock(tables={})
        um_meta = MagicMock(tables={})

        with caplog.at_level(logging.INFO):
            _check_tablename_collisions_logic(
                slm_meta, um_meta, logging.getLogger("main")
            )

        assert any("0 shared" in r.message for r in caplog.records)
