# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15462 — the SLM self-sync-from-code-source path must write
``.deployed_commit`` so a deploy through it is attributable, matching the
marker ``update-all-nodes.yml`` writes (#12223, #12202).

Before this fix, ``_sync_slm_from_code_source`` never wrote the marker, so
``_get_slm_deployed_commit()`` always returned ``None`` after a deploy
through this path — the exact live symptom the issue reports.

``write_slm_deployed_commit_marker`` lived in ``api/code_sync.py`` until the
#15462 review, which moved it (with the rest of the build/publish logic) into
``services/slm_frontend_build.py`` to keep the router module under its
grandfathered line-count ceiling (#14236).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio  # noqa: E402

from services.slm_frontend_build import write_slm_deployed_commit_marker  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_marker_is_written_under_the_ssot_deployed_root(tmp_path) -> None:
    """Uses ``get_release_component_dir`` (SSOT — never a literal path)."""
    deployed_dir = tmp_path / "autobot-slm-backend"
    deployed_dir.mkdir()

    with patch("services.slm_frontend_build.get_release_component_dir", return_value=str(deployed_dir)) as resolver:
        _run(write_slm_deployed_commit_marker("abc123def456"))

    resolver.assert_called_once_with("autobot-slm-backend")
    marker = deployed_dir / ".deployed_commit"
    assert marker.read_text(encoding="utf-8") == "abc123def456"


def test_marker_write_failure_is_logged_not_raised(tmp_path, caplog) -> None:
    import logging

    # A deployed dir that does not exist -> the write fails with
    # FileNotFoundError, which must be caught and logged, never propagated
    # (this runs right before a service-restarting phase).
    caplog.set_level(logging.WARNING, logger="services.slm_frontend_build")

    with patch("services.slm_frontend_build.get_release_component_dir", return_value=str(tmp_path / "does-not-exist")):
        _run(write_slm_deployed_commit_marker("abc123"))

    assert any("deployed_commit" in rec.message for rec in caplog.records)
